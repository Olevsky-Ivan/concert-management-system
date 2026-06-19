import os

import stripe
from django.conf import settings
from django.utils import timezone

from tickets.models import Order, Ticket, Reservation

STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL")


def confirm_order_payment(order: Order) -> None:
    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at"])

    reservations = order.reservations.filter(is_active=True).select_related(
        "concert", "zone", "seat"
    )

    tickets = [
        Ticket(
            user=order.user,
            order=order,
            concert=r.concert,
            zone=r.zone,
            seat=r.seat,
            price=r.price,
            status=Ticket.Status.ACTIVE,
        )
        for r in reservations
    ]
    Ticket.objects.bulk_create(tickets)
    reservations.update(is_active=False)


# Returns order with status(PENDING) and session.url
def create_checkout_session(user, reservations):
    total = sum(r.price for r in reservations)

    order = Order.objects.create(
        user=user,
        total_price=total,
        status=Order.Status.PENDING,
    )

    for reservation in reservations:
        reservation.order = order
        reservation.save(update_fields=["order"])

    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "product_data": {"name": f"Order #{order.pk}"},
                    "unit_amount": int(total * 100),
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        metadata={"order_id": order.pk},
        # urls for example
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
    )

    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])

    return order, session.url
