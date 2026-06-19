from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework.test import APIClient
from rest_framework import status

from concerts.models import Artist, Category, Venue, Hall, Zone, Seat, Concert
from tickets.models import Ticket, Order, Reservation, RESERVATION_LIFETIME_MINUTES


User = get_user_model()


def make_user(email="user@test.com", role="customer"):
    return User.objects.create_user(email=email, password="pass1234", role=role)


def make_admin(email="admin@test.com"):
    return User.objects.create_user(email=email, password="pass1234", role="admin")


def make_structure():
    admin = make_admin()
    venue = Venue.objects.create(name="Arena", city="Kyiv", address="Street 1")
    hall = Hall.objects.create(name="Main Hall", venue=venue)

    zone = Zone.objects.create(
        hall=hall,
        name="A",
        price=Decimal("100.00"),
        capacity=10,
        has_seats=True
    )

    seat = Seat.objects.create(zone=zone, row="A", number=1)

    artist = Artist.objects.create(name="Artist")
    category = Category.objects.create(name="Rock")

    concert = Concert.objects.create(
        title="Concert",
        description="Desc",
        date=timezone.now() + timedelta(days=5),
        hall=hall,
        created_by=admin
    )

    concert.artists.add(artist)
    concert.categories.add(category)

    return {
        "admin": admin,
        "venue": venue,
        "hall": hall,
        "zone": zone,
        "seat": seat,
        "artist": artist,
        "category": category,
        "concert": concert,
    }


def make_concert(hall, admin, past=False):
    date = timezone.now() - timedelta(days=1) if past else timezone.now() + timedelta(days=5)
    return Concert.objects.create(
        title="Test",
        description="Desc",
        date=date,
        hall=hall,
        created_by=admin
    )


def make_reservation(user, concert, zone, seat=None, expired=False):
    expires_at = timezone.now() + timedelta(minutes=RESERVATION_LIFETIME_MINUTES)
    if expired:
        expires_at = timezone.now() - timedelta(minutes=1)

    return Reservation.objects.create(
        user=user,
        concert=concert,
        zone=zone,
        seat=seat,
        price=zone.price,
        expires_at=expires_at,
        is_active=True
    )


class ConcertModelTest(TestCase):
    def setUp(self):
        self.data = make_structure()

    def test_concert_created(self):
        self.assertEqual(Concert.objects.count(), 1)

    def test_zone_relation(self):
        self.assertEqual(self.data["hall"].zones.count(), 1)


class ZoneLogicTest(TestCase):
    def setUp(self):
        self.data = make_structure()
        self.user = make_user()

    def test_available_seats_decreases(self):
        make_reservation(
            self.user,
            self.data["concert"],
            self.data["zone"],
            self.data["seat"]
        )
        self.assertEqual(
            self.data["zone"].available_seats_count_for_concert(self.data["concert"].pk),
            0
        )

    def test_expired_reservation_does_not_count(self):
        make_reservation(
            self.user,
            self.data["concert"],
            self.data["zone"],
            self.data["seat"],
            expired=True
        )
        self.assertEqual(
            self.data["zone"].available_seats_count_for_concert(self.data["concert"].pk),
            1
        )


class ConcertAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.data = make_structure()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_list_concerts(self):
        res = self.client.get("/api/concerts/")
        self.assertEqual(res.status_code, 200)

    def test_retrieve_concert(self):
        res = self.client.get(f"/api/concerts/{self.data['concert'].id}/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("zones", res.data)


class SeatAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.data = make_structure()
        self.admin = self.data["admin"]
        self.client.force_authenticate(user=self.admin)

    def test_create_seat(self):
        res = self.client.post(
            f"/api/zones/{self.data['zone'].id}/seats/",
            {"row": "B", "number": 2},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_duplicate_seat(self):
        res = self.client.post(
            f"/api/zones/{self.data['zone'].id}/seats/",
            {"row": "A", "number": 1},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.data = make_structure()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_review_block_without_ticket(self):
        res = self.client.post(
            f"/api/concerts/{self.data['concert'].id}/reviews/",
            {"rating": 5, "comment": "Good"},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class OrderAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.data = make_structure()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_order_create_flow(self):
        r = make_reservation(
            self.user,
            self.data["concert"],
            self.data["zone"],
            self.data["seat"]
        )

        order = Order.objects.create(
            user=self.user,
            total_price=r.price,
            status=Order.Status.PENDING
        )

        self.assertEqual(order.is_payable, True)


class AuthTest(TestCase):
    def test_unauthenticated_blocked(self):
        client = APIClient()
        res = client.get("/api/concerts/")
        self.assertIn(res.status_code, [401, 403])