from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Venue(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Hall(models.Model):
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name="halls",
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.venue.name} - {self.name}"


class Artist(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Concert(models.Model):
    hall = models.ForeignKey(
        Hall,
        on_delete=models.CASCADE,
        related_name="concerts",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    artists = models.ManyToManyField(Artist, related_name="concerts", blank=True)
    categories = models.ManyToManyField(Category, related_name="concerts", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def is_past(self):
        return self.date < timezone.now()


class Zone(models.Model):
    hall = models.ForeignKey(
        Hall,
        on_delete=models.CASCADE,
        related_name="zones",
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()
    has_seats = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.hall.name} - {self.name}"

    def taken_seats_for_concert(self, concert_id):
        from tickets.models import Ticket, Reservation

        paid_seat_ids = set(
            Ticket.objects.filter(
                concert_id=concert_id,
                zone=self,
                status__in=[Ticket.Status.ACTIVE],
                seat__isnull=False,
            ).values_list("seat_id", flat=True)
        )

        reserved_seat_ids = set(
            Reservation.objects.filter(
                concert_id=concert_id,
                zone=self,
                is_active=True,
                expires_at__gt=timezone.now(),
                seat__isnull=False,
            ).values_list("seat_id", flat=True)
        )

        return paid_seat_ids | reserved_seat_ids

    def available_seats_count_for_concert(self, concert_id):
        if self.has_seats:
            return self.seats.count() - len(self.taken_seats_for_concert(concert_id))

        from tickets.models import Ticket, Reservation

        paid_count = Ticket.objects.filter(
            concert_id=concert_id,
            zone=self,
            status__in=[Ticket.Status.PAID, Ticket.Status.RESERVED],
        ).count()

        reserved_count = Reservation.objects.filter(
            concert_id=concert_id,
            zone=self,
            is_active=True,
            expires_at__gt=timezone.now(),
        ).count()

        return self.capacity - paid_count - reserved_count


class Seat(models.Model):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="seats")
    row = models.CharField(max_length=10)
    number = models.PositiveIntegerField()

    class Meta:
        unique_together = ("zone", "row", "number")

    def __str__(self):
        return f"Row {self.row}, Seat {self.number}"

    def is_taken_for_concert(self, concert_id):
        return self.pk in self.zone.taken_seats_for_concert(concert_id)


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    concert = models.ForeignKey(
        Concert,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "concert"],
                name="unique_user_concert_review",
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.concert.title}"
