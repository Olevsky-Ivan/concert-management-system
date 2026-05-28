from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class Concert(models.Model):
    title = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    place = models.CharField(max_length=255)
    date = models.DateTimeField()

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    artists = models.ManyToManyField("Artist", related_name="concerts", blank=True)

    categories = models.ManyToManyField("Category", related_name="concerts", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Zone(models.Model):
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE, related_name="zones")

    name = models.CharField(max_length=100)

    price = models.DecimalField(max_digits=10, decimal_places=2)

    capacity = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def available_seats(self):
        reserved = self.reservations.filter(
            is_active=True, expires_at__gt=timezone.now()
        ).count()

        sold = self.tickets.filter(status__in=["reserved", "paid"]).count()

        return self.capacity - reserved - sold

    def __str__(self):
        return f"{self.concert.title} - {self.name}"


class Artist(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    concert = models.ForeignKey(Concert, on_delete=models.CASCADE)

    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "concert"], name="unique_user_concert_review"
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.concert.title}"
