from celery import shared_task
from django.utils import timezone

from tickets.models import Reservation, Order


@shared_task
def expire_stale_reservations():
    now = timezone.now()
    expired_count = Reservation.objects.filter(
        is_active=True,
        order__isnull=True,
        expires_at__lte=now,
    ).update(is_active=False)

    return f"Expired {expired_count} reservations"


@shared_task
def expire_stale_orders():
    cutoff = timezone.now() - timezone.timedelta(minutes=30)
    orders = Order.objects.filter(
        status=Order.Status.PENDING,
        created_at__lte=cutoff,
    )
    count = orders.count()
    for order in orders:
        order.status = Order.Status.EXPIRED
        order.save(update_fields=["status"])
        order.reservations.update(is_active=False)

    return f"Expired {count} orders"
