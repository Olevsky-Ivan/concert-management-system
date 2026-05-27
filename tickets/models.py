from django.db import models
from concerts.models import Concert, Zone


class Ticket(models.Model):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="tickets",
    )

    zone = models.ForeignKey(
        Zone,
        on_delete=models.CASCADE,
        related_name="tickets",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RESERVED,
    )

    def __str__(self):
        return f"{self.user.email} - {self.zone}"
