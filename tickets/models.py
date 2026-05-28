from django.conf import settings
from django.db import models
from concerts.models import Concert, Zone


class Reservation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class Ticket(models.Model):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE)

    price = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RESERVED
    )

    created_at = models.DateTimeField(auto_now_add=True)