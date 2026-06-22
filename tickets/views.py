import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tickets.models import Order, Reservation, Ticket
from tickets.permissions import IsOwnerOrAdmin
from tickets.serializers import (
    CartSummarySerializer,
    CheckoutSerializer,
    OrderReadSerializer,
    ReservationSerializer,
    TicketSerializer,
)
from tickets.services import confirm_order_payment

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):

    def post(self, request):
        try:
            payload = request.body
            sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

            try:
                event = stripe.Webhook.construct_event(
                    payload,
                    sig_header,
                    settings.STRIPE_WEBHOOK_SECRET,
                )
            except ValueError:
                logger.warning("Invalid Stripe webhook payload")
                return HttpResponse(status=400)
            except stripe.error.SignatureVerificationError:
                logger.warning("Invalid Stripe webhook signature")
                return HttpResponse(status=400)

            logger.info("Stripe event: %s", event["type"])

            session_obj = event["data"]["object"]
            event_type = event["type"]

            session = None

            try:
                if hasattr(session_obj, "to_dict_recursive"):
                    session = session_obj.to_dict_recursive()
                elif hasattr(session_obj, "to_dict"):
                    session = session_obj.to_dict()
                else:
                    session = session_obj
            except Exception:
                logger.exception("Failed to convert Stripe object")
                session = {}

            if event_type == "checkout.session.completed":
                self._handle_checkout_completed(session)

            elif event_type == "checkout.session.expired":
                self._handle_checkout_expired(session)

            elif event_type in ("payment_intent.payment_failed", "charge.failed"):
                self._handle_payment_failed(session)

            return HttpResponse(status=200)

        except Exception:
            logger.exception("Unhandled Stripe webhook error")
            return HttpResponse(status=200)

    def _handle_checkout_completed(self, session):
        try:
            order_id = session["metadata"]["order_id"]
            order = Order.objects.get(pk=order_id, status=Order.Status.PENDING)
            confirm_order_payment(order)
            logger.info("Payment confirmed for order %s", order.pk)
        except KeyError:
            logger.warning("order_id not found in Stripe session metadata")
        except Order.DoesNotExist:
            logger.warning(
                "Order %s not found or not pending",
                session.get("metadata", {}).get("order_id"),
            )

    def _handle_checkout_expired(self, session):
        try:
            order_id = session["metadata"]["order_id"]
            order = Order.objects.get(pk=order_id, status=Order.Status.PENDING)
            order.status = Order.Status.EXPIRED
            order.save(update_fields=["status"])
            order.reservations.update(is_active=False)
            logger.info("Order %s expired — seats released", order.pk)
        except KeyError:
            logger.warning("order_id not found in expired session metadata")
        except Order.DoesNotExist:
            logger.warning("Order not found for expired session")

    def _handle_payment_failed(self, session):
        order_id = session.get("metadata", {}).get("order_id", "unknown")
        logger.warning("Payment failed for order %s", order_id)


class ReservationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = Reservation.objects.select_related(
            "user", "concert", "zone", "seat", "order"
        )
        if self.request.user.role == "admin":
            return qs.all()
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # Cancels reservation (marks as inactive instead of deleting)
    def destroy(self, request, *args, **kwargs):
        reservation = self.get_object()
        self.check_object_permissions(request, reservation)

        if not reservation.is_active:
            return Response(
                {"detail": "Reservation is already inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reservation.expire()
        return Response(
            {"detail": "Removed from cart."},
            status=status.HTTP_200_OK,
        )

    # Returns active reservations as cart summary and expires outdated ones
    @action(detail=False, methods=["get"])
    def cart(self, request):
        now = timezone.now()

        try:
            Reservation.objects.filter(
                user=request.user,
                is_active=True,
                order__isnull=True,
                expires_at__lte=now,
            ).update(is_active=False)
        except Exception:
            logger.exception(
                "Failed to expire stale reservations for user %s", request.user.pk
            )

        items = (
            Reservation.objects.filter(
                user=request.user,
                is_active=True,
                order__isnull=True,
                expires_at__gt=now,
            )
            .select_related("concert", "zone", "seat")
            .order_by("created_at")
        )

        total_price = sum(r.price for r in items)
        earliest_expiry = min((r.expires_at for r in items), default=None)

        data = {
            "items": items,
            "total_price": total_price,
            "expires_at": earliest_expiry,
            "item_count": len(items),
        }

        serializer = CartSummarySerializer(data)
        return Response(serializer.data)


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrderReadSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = Order.objects.prefetch_related(
            "reservations__concert",
            "reservations__zone",
            "reservations__seat",
            "tickets__concert",
            "tickets__zone",
            "tickets__seat",
        )
        if self.request.user.role == "admin":
            return qs.all()
        return qs.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        try:
            with transaction.atomic():
                serializer = CheckoutSerializer(
                    data=request.data, context={"request": request}
                )
                serializer.is_valid(raise_exception=True)
                order = serializer.create_order()

                logger.info("Order %s created for user %s", order.pk, request.user.pk)

                return Response(
                    {
                        **OrderReadSerializer(order, context={"request": request}).data,
                        "payment_url": serializer._payment_url,
                    },
                    status=status.HTTP_201_CREATED,
                )
        except Exception:
            logger.exception("Checkout failed for user %s", request.user.pk)
            raise

    # Cancels order and updates related tickets status accordingly
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            with transaction.atomic():
                order = self.get_object()
                self.check_object_permissions(request, order)

                if order.is_canceled:
                    return Response(
                        {"detail": "Order is already canceled."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if order.is_expired:
                    return Response(
                        {"detail": "Expired orders cannot be canceled."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                order.status = Order.Status.CANCELED
                order.save(update_fields=["status"])
                order.reservations.update(is_active=False)
                order.tickets.filter(status=Ticket.Status.ACTIVE).update(
                    status=Ticket.Status.CANCELED
                )

                logger.info("Order %s canceled by user %s", order.pk, request.user.pk)

                return Response(
                    OrderReadSerializer(order, context={"request": request}).data
                )
        except Exception:
            logger.exception(
                "Failed to cancel order %s for user %s", pk, request.user.pk
            )
            raise


class TicketViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = Ticket.objects.select_related("user", "order", "concert", "zone", "seat")
        if self.request.user.role == "admin":
            return qs.all()
        return qs.filter(user=self.request.user)

    # Cancels ticket if allowed; seat becomes available again automatically
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ticket = self.get_object()
        self.check_object_permissions(request, ticket)

        if ticket.is_canceled:
            return Response(
                {"detail": "Ticket is already canceled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ticket.is_used:
            return Response(
                {"detail": "Cannot cancel a ticket that has already been used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = Ticket.Status.CANCELED
        ticket.save(update_fields=["status"])

        logger.info("Ticket %s canceled by user %s", ticket.pk, request.user.pk)

        # taken_seats_for_concert() already excludes CANCELED tickets.

        return Response(TicketSerializer(ticket).data)
