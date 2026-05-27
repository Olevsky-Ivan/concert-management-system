from django.db import models
from django.core.validators import MinValueValidator


class Concert(models.Model):
    city = models.CharField(max_length=100)
    place = models.CharField(max_length=200)
    date = models.DateTimeField()

    def __str__(self):
        return f"{self.city} - {self.place}"


class Zone(models.Model):
    concert = models.ForeignKey(
        "Concert",
        on_delete=models.CASCADE,
        related_name="zones",
    )

    name = models.CharField(max_length=50)

    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    total_seats = models.PositiveIntegerField()

    class Meta:
        unique_together = ("concert", "name")

    def __str__(self):
        return f"{self.name} - {self.concert}"
