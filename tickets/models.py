from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

RESERVATION_LIFETIME_MINUTES = 15


class Reservation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    concert = models.ForeignKey(
        "concerts.Concert",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    zone = models.ForeignKey(
        "concerts.Zone",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    seat = models.ForeignKey(
        "concerts.Seat",
        on_delete=models.CASCADE,
        related_name="reservations",
        null=True,
        blank=True,
    )
    order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        related_name="reservations",
        null=True,
        blank=True,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["concert", "seat"],
                condition=models.Q(is_active=True, seat__isnull=False),
                name="unique_active_reservation_per_seat",
            )
        ]

    def __str__(self):
        seat_label = (
            f" | Row {self.seat.row} Seat {self.seat.number}" if self.seat else ""
        )
        return (
            f"{self.user.email} – {self.concert.title} / {self.zone.name}{seat_label}"
        )

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def expire(self):
        self.is_active = False
        self.save(update_fields=["is_active"])


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Order #{self.pk} – {self.user.email} – {self.status}"

    @property
    def is_payable(self):
        return self.status == self.Status.PENDING

    def recalculate_total(self):
        self.total_price = self.reservations.filter(is_active=True).aggregate(
            total=models.Sum("price")
        )["total"] or Decimal("0.00")
        self.save(update_fields=["total_price"])


class Ticket(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"
        USED = "used", "Used"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    concert = models.ForeignKey(
        "concerts.Concert",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    zone = models.ForeignKey(
        "concerts.Zone",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    seat = models.ForeignKey(
        "concerts.Seat",
        on_delete=models.SET_NULL,
        related_name="tickets",
        null=True,
        blank=True,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["concert", "seat"],
                condition=models.Q(status="active", seat__isnull=False),
                name="unique_active_ticket_per_seat",
            )
        ]

    def __str__(self):
        return f"Ticket #{self.pk} – {self.user.email} – {self.concert.title}"

    @property
    def is_cancelable(self):
        return self.status == self.Status.ACTIVE and not self.concert.is_past
