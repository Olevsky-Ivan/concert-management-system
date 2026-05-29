from django.utils import timezone
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tickets.models import Order, Reservation, Ticket
from tickets.serializers import (
    CartSummarySerializer,
    CheckoutSerializer,
    OrderReadSerializer,
    ReservationSerializer,
    TicketSerializer,
)


class ReservationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Reservation.objects.select_related(
            "user", "concert", "zone", "seat", "order"
        )
        if self.request.user.role == "admin":
            return qs.all()
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # Cancels reservation (marks as expired instead of deleting)
    def destroy(self, request, *args, **kwargs):
        reservation = self.get_object()

        if reservation.user != request.user and request.user.role != "admin":
            return Response(
                {"detail": "Not allowed."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        # Expire stale ones silently
        Reservation.objects.filter(
            user=request.user,
            is_active=True,
            order__isnull=True,
            expires_at__lte=now,
        ).update(is_active=False)

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
    permission_classes = [IsAuthenticated]

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

    # Converts validated reservations into a paid order with generated tickets
    @action(detail=False, methods=["post"])
    def checkout(self, request):
        with transaction.atomic():
            serializer = CheckoutSerializer(
                data=request.data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)

            order = serializer.create_order()

            return Response(
                OrderReadSerializer(order, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

    # Cancels order and updates related tickets status accordingly
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            order = self.get_object()

            if order.user != request.user and request.user.role != "admin":
                return Response({"detail": "Not allowed."}, status=403)

            if order.status == Order.Status.CANCELED:
                return Response({"detail": "Order is already canceled."}, status=400)

            if order.status == Order.Status.EXPIRED:
                return Response(
                    {"detail": "Expired orders cannot be canceled."}, status=400
                )

            order.status = Order.Status.CANCELED
            order.save(update_fields=["status"])

            order.tickets.filter(status=Ticket.Status.ACTIVE).update(
                status=Ticket.Status.CANCELED
            )

            return Response(
                OrderReadSerializer(order, context={"request": request}).data
            )


class TicketViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Ticket.objects.select_related("user", "order", "concert", "zone", "seat")
        if self.request.user.role == "admin":
            return qs.all()
        return qs.filter(user=self.request.user)

    # Cancels ticket if allowed; seat becomes available again automatically
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ticket = self.get_object()
        is_admin = request.user.role == "admin"
        is_owner = ticket.user == request.user

        if not is_owner and not is_admin:
            return Response(
                {"detail": "Not allowed."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status == Ticket.Status.CANCELED:
            return Response(
                {"detail": "Ticket is already canceled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ticket.status == Ticket.Status.USED:
            return Response(
                {"detail": "Cannot cancel a ticket that has already been used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_admin and ticket.concert.is_past:
            return Response(
                {"detail": "Cannot cancel a ticket after the concert has taken place."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = Ticket.Status.CANCELED
        ticket.save(update_fields=["status"])

        # taken_seats_for_concert() already excludes CANCELED tickets.

        return Response(TicketSerializer(ticket).data)
