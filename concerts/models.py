from django.conf import settings
from django.db import models



class Concert(models.Model):
    title = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    place = models.CharField(max_length=255)
    date = models.DateTimeField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    artists = models.ManyToManyField(
        "Artist",
        related_name="concerts",
        blank=True
    )

    categories = models.ManyToManyField(
        "Category",
        related_name="concerts",
        blank=True
    )


class Zone(models.Model):
    concert = models.ForeignKey(
        Concert,
        on_delete=models.CASCADE,
        related_name="zones"
    )

    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()


class Artist(models.Model):
    name = models.CharField(max_length=100)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE)

    rating = models.IntegerField()
    comment = models.TextField(blank=True)