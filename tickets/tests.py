from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from datetime import timedelta

from concerts.models import Venue, Hall, Zone, Seat, Concert
from tickets.models import Reservation, Order, Ticket, RESERVATION_LIFETIME_MINUTES

User = get_user_model()


def make_user(email="user@test.com", role="customer", password="pass1234"):
    return User.objects.create_user(email=email, password=password, role=role)


def make_admin(email="admin@test.com"):
    return User.objects.create_user(email=email, password="pass1234", role="admin")


def make_concert(hall, created_by, future=True):
    date = (
        timezone.now() + timedelta(days=7)
        if future
        else timezone.now() - timedelta(days=1)
    )
    return Concert.objects.create(
        hall=hall, title="Test Concert", date=date, created_by=created_by
    )


def make_infrastructure():
    admin = make_admin()
    venue = Venue.objects.create(name="Arena", city="Kyiv", address="str 1")
    hall = Hall.objects.create(venue=venue, name="Main Hall")
    zone_seated = Zone.objects.create(
        hall=hall, name="VIP", price=Decimal("500.00"), capacity=10, has_seats=True
    )
    zone_standing = Zone.objects.create(
        hall=hall, name="Standing", price=Decimal("200.00"), capacity=5, has_seats=False
    )
    seat = Seat.objects.create(zone=zone_seated, row="A", number=1)
    concert = make_concert(hall, admin)
    return {
        "admin": admin,
        "hall": hall,
        "zone_seated": zone_seated,
        "zone_standing": zone_standing,
        "seat": seat,
        "concert": concert,
    }


def make_reservation(user, concert, zone, seat=None, active=True, expired=False):
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
        is_active=active,
    )


class ReservationModelTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()

    def test_is_expired_false_for_active(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )
        self.assertFalse(r.is_expired)

    def test_is_expired_true_for_past(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"], expired=True
        )
        self.assertTrue(r.is_expired)

    def test_expire_sets_inactive(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )
        r.expire()
        r.refresh_from_db()
        self.assertFalse(r.is_active)

    def test_unique_active_reservation_per_seat(self):
        from django.db import IntegrityError

        make_reservation(
            self.user, self.data["concert"], self.data["zone_seated"], self.data["seat"]
        )
        with self.assertRaises(IntegrityError):
            make_reservation(
                make_user("other@test.com"),
                self.data["concert"],
                self.data["zone_seated"],
                self.data["seat"],
            )


class OrderModelTest(TestCase):

    def setUp(self):
        self.user = make_user()

    def _make_order(self, status_val):
        return Order.objects.create(
            user=self.user, total_price=Decimal("100.00"), status=status_val
        )

    def test_is_payable_only_when_pending(self):
        order = self._make_order(Order.Status.PENDING)
        self.assertTrue(order.is_payable)
        order.status = Order.Status.PAID
        self.assertFalse(order.is_payable)

    def test_is_canceled_property(self):
        order = self._make_order(Order.Status.CANCELED)
        self.assertTrue(order.is_canceled)

    def test_is_expired_property(self):
        order = self._make_order(Order.Status.EXPIRED)
        self.assertTrue(order.is_expired)


class TicketModelTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()

    def _make_ticket(self, ticket_status=Ticket.Status.ACTIVE, past=False):
        concert = make_concert(self.data["hall"], self.data["admin"], future=not past)
        order = Order.objects.create(
            user=self.user, total_price=Decimal("500.00"), status=Order.Status.PAID
        )
        return Ticket.objects.create(
            user=self.user,
            order=order,
            concert=concert,
            zone=self.data["zone_seated"],
            price=Decimal("500.00"),
            status=ticket_status,
        )

    def test_is_cancelable_active_future(self):
        self.assertTrue(self._make_ticket().is_cancelable)

    def test_is_cancelable_false_for_past_concert(self):
        self.assertFalse(self._make_ticket(past=True).is_cancelable)

    def test_is_cancelable_false_when_canceled(self):
        self.assertFalse(
            self._make_ticket(ticket_status=Ticket.Status.CANCELED).is_cancelable
        )

    def test_is_canceled_property(self):
        self.assertTrue(
            self._make_ticket(ticket_status=Ticket.Status.CANCELED).is_canceled
        )

    def test_is_used_property(self):
        self.assertTrue(self._make_ticket(ticket_status=Ticket.Status.USED).is_used)


class ZoneAvailabilityTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()

    def test_seated_zone_counts_active_reservations(self):
        zone = self.data["zone_seated"]
        concert = self.data["concert"]
        make_reservation(self.user, concert, zone, self.data["seat"])
        self.assertEqual(zone.available_seats_count_for_concert(concert.pk), 0)

    def test_standing_zone_counts_active_reservations(self):
        zone = self.data["zone_standing"]
        concert = self.data["concert"]
        make_reservation(self.user, concert, zone)
        make_reservation(make_user("u2@test.com"), concert, zone)
        self.assertEqual(zone.available_seats_count_for_concert(concert.pk), 3)

    def test_expired_reservation_frees_seat(self):
        zone = self.data["zone_seated"]
        concert = self.data["concert"]
        make_reservation(self.user, concert, zone, self.data["seat"], expired=True)
        self.assertEqual(zone.available_seats_count_for_concert(concert.pk), 1)


class ReservationAPITest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_seated_reservation(self):
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": self.data["concert"].pk,
                "zone": self.data["zone_seated"].pk,
                "seat": self.data["seat"].pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_create_standing_reservation(self):
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": self.data["concert"].pk,
                "zone": self.data["zone_standing"].pk,
                "seat": None,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_duplicate_seat_reservation_rejected(self):
        make_reservation(
            self.user, self.data["concert"], self.data["zone_seated"], self.data["seat"]
        )
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": self.data["concert"].pk,
                "zone": self.data["zone_seated"].pk,
                "seat": self.data["seat"].pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seat", res.data)

    def test_past_concert_reservation_rejected(self):
        past_concert = make_concert(self.data["hall"], self.data["admin"], future=False)
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": past_concert.pk,
                "zone": self.data["zone_standing"].pk,
                "seat": None,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("concert", res.data)

    def test_zone_not_in_concert_hall_rejected(self):
        other_venue = Venue.objects.create(name="Other", city="Lviv", address="str 2")
        other_hall = Hall.objects.create(venue=other_venue, name="Hall 2")
        other_zone = Zone.objects.create(
            hall=other_hall,
            name="Zone",
            price=Decimal("100.00"),
            capacity=10,
            has_seats=False,
        )
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": self.data["concert"].pk,
                "zone": other_zone.pk,
                "seat": None,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("zone", res.data)

    def test_seated_zone_requires_seat(self):
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": self.data["concert"].pk,
                "zone": self.data["zone_seated"].pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seat", res.data)

    def test_standing_zone_full_rejected(self):
        zone = self.data["zone_standing"]
        concert = self.data["concert"]
        for i in range(5):
            make_reservation(make_user(f"fill{i}@test.com"), concert, zone)
        res = self.client.post(
            "/api/tickets/reservations/",
            {
                "concert": concert.pk,
                "zone": zone.pk,
                "seat": None,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_own_reservation(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )
        res = self.client.delete(f"/api/tickets/reservations/{r.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        r.refresh_from_db()
        self.assertFalse(r.is_active)

    def test_cannot_cancel_others_reservation(self):
        other = make_user("other@test.com")
        r = make_reservation(other, self.data["concert"], self.data["zone_standing"])
        res = self.client.delete(f"/api/tickets/reservations/{r.pk}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cart_excludes_expired_reservations(self):
        make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"], expired=True
        )
        res = self.client.get("/api/tickets/reservations/cart/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["item_count"], 0)

    def test_cart_shows_active_reservations(self):
        make_reservation(self.user, self.data["concert"], self.data["zone_standing"])
        res = self.client.get("/api/tickets/reservations/cart/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["item_count"], 1)

    def test_unauthenticated_rejected(self):
        res = APIClient().post("/api/tickets/reservations/", {})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class CheckoutAPITest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_active_reservation(self):
        return make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )

    @patch("tickets.services.stripe.checkout.Session.create")
    def test_checkout_creates_pending_order(self, mock_stripe):
        mock_stripe.return_value = MagicMock(
            id="sess_123", url="https://stripe.com/pay"
        )
        r = self._make_active_reservation()
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "pending")
        self.assertIn("payment_url", res.data)
        self.assertEqual(
            Order.objects.get(pk=res.data["id"]).status, Order.Status.PENDING
        )

    @patch("tickets.services.stripe.checkout.Session.create")
    def test_checkout_links_reservations_to_order(self, mock_stripe):
        mock_stripe.return_value = MagicMock(
            id="sess_123", url="https://stripe.com/pay"
        )
        r = self._make_active_reservation()
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        r.refresh_from_db()
        self.assertIsNotNone(r.order)

    def test_checkout_expired_reservation_rejected(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"], expired=True
        )
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_others_reservation_rejected(self):
        other = make_user("other@test.com")
        r = make_reservation(other, self.data["concert"], self.data["zone_standing"])
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_empty_ids_rejected(self):
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": []}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("tickets.services.stripe.checkout.Session.create")
    def test_checkout_already_ordered_reservation_rejected(self, mock_stripe):
        mock_stripe.return_value = MagicMock(
            id="sess_123", url="https://stripe.com/pay"
        )
        r = self._make_active_reservation()
        self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        res = self.client.post(
            "/api/tickets/orders/checkout/", {"reservation_ids": [r.pk]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class OrderCancelAPITest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_pending_order_with_reservation(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )
        order = Order.objects.create(
            user=self.user, total_price=r.price, status=Order.Status.PENDING
        )
        r.order = order
        r.save(update_fields=["order"])
        return order, r

    def test_cancel_pending_order(self):
        order, r = self._make_pending_order_with_reservation()
        res = self.client.post(f"/api/tickets/orders/{order.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)
        r.refresh_from_db()
        self.assertFalse(r.is_active)

    def test_cancel_already_canceled_order(self):
        order, _ = self._make_pending_order_with_reservation()
        order.status = Order.Status.CANCELED
        order.save()
        res = self.client.post(f"/api/tickets/orders/{order.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_expired_order_rejected(self):
        order, _ = self._make_pending_order_with_reservation()
        order.status = Order.Status.EXPIRED
        order.save()
        res = self.client.post(f"/api/tickets/orders/{order.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_others_order(self):
        other = make_user("other@test.com")
        order = Order.objects.create(
            user=other, total_price=Decimal("100.00"), status=Order.Status.PENDING
        )
        res = self.client.post(f"/api/tickets/orders/{order.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class TicketCancelAPITest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_ticket(self, ticket_status=Ticket.Status.ACTIVE, past=False):
        concert = make_concert(self.data["hall"], self.data["admin"], future=not past)
        order = Order.objects.create(
            user=self.user, total_price=Decimal("200.00"), status=Order.Status.PAID
        )
        return Ticket.objects.create(
            user=self.user,
            order=order,
            concert=concert,
            zone=self.data["zone_standing"],
            price=Decimal("200.00"),
            status=ticket_status,
        )

    def test_cancel_active_ticket(self):
        ticket = self._make_ticket()
        res = self.client.post(f"/api/tickets/tickets/{ticket.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.CANCELED)

    def test_cancel_already_canceled_ticket(self):
        ticket = self._make_ticket(ticket_status=Ticket.Status.CANCELED)
        res = self.client.post(f"/api/tickets/tickets/{ticket.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_used_ticket_rejected(self):
        ticket = self._make_ticket(ticket_status=Ticket.Status.USED)
        res = self.client.post(f"/api/tickets/tickets/{ticket.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_others_ticket(self):
        other = make_user("other@test.com")
        order = Order.objects.create(
            user=other, total_price=Decimal("200.00"), status=Order.Status.PAID
        )
        ticket = Ticket.objects.create(
            user=other,
            order=order,
            concert=self.data["concert"],
            zone=self.data["zone_standing"],
            price=Decimal("200.00"),
            status=Ticket.Status.ACTIVE,
        )
        res = self.client.post(f"/api/tickets/tickets/{ticket.pk}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class StripeWebhookTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()
        self.client = APIClient()

    def _make_pending_order(self):
        r = make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"]
        )
        order = Order.objects.create(
            user=self.user, total_price=r.price, status=Order.Status.PENDING
        )
        r.order = order
        r.is_active = True
        r.save(update_fields=["order", "is_active"])
        return order, r

    def _post_webhook(self, event_type, order_id):
        with patch("tickets.views.stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = {
                "type": event_type,
                "data": {"object": {"metadata": {"order_id": str(order_id)}}},
            }
            return self.client.post(
                "/api/webhooks/stripe/",
                data=b"payload",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=123,v1=abc",
            )

    def test_checkout_completed_marks_order_paid(self):
        order, _ = self._make_pending_order()
        self.assertEqual(
            self._post_webhook("checkout.session.completed", order.pk).status_code, 200
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIsNotNone(order.paid_at)

    def test_checkout_completed_creates_tickets(self):
        order, _ = self._make_pending_order()
        self._post_webhook("checkout.session.completed", order.pk)
        self.assertEqual(Ticket.objects.filter(order=order).count(), 1)

    def test_checkout_completed_deactivates_reservations(self):
        order, r = self._make_pending_order()
        self._post_webhook("checkout.session.completed", order.pk)
        r.refresh_from_db()
        self.assertFalse(r.is_active)

    def test_checkout_expired_marks_order_expired(self):
        order, r = self._make_pending_order()
        self.assertEqual(
            self._post_webhook("checkout.session.expired", order.pk).status_code, 200
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        r.refresh_from_db()
        self.assertFalse(r.is_active)

    def test_invalid_signature_returns_400(self):
        with patch("tickets.views.stripe.Webhook.construct_event") as mock_event:
            import stripe

            mock_event.side_effect = stripe.error.SignatureVerificationError(
                "Invalid", "sig"
            )
            res = self.client.post(
                "/api/webhooks/stripe/",
                data=b"payload",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="bad",
            )
        self.assertEqual(res.status_code, 400)

    def test_missing_order_id_handled_gracefully(self):
        with patch("tickets.views.stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = {
                "type": "checkout.session.completed",
                "data": {"object": {"metadata": {}}},
            }
            res = self.client.post(
                "/api/webhooks/stripe/",
                data=b"payload",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=123,v1=abc",
            )
        self.assertEqual(res.status_code, 200)


class CeleryTasksTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.user = make_user()

    def test_expire_stale_reservations_deactivates_expired(self):
        from tickets.tasks import expire_stale_reservations

        make_reservation(
            self.user, self.data["concert"], self.data["zone_standing"], expired=True
        )
        self.assertEqual(expire_stale_reservations(), "Expired 1 reservations")
        self.assertEqual(Reservation.objects.filter(is_active=True).count(), 0)

    def test_expire_stale_reservations_keeps_active(self):
        from tickets.tasks import expire_stale_reservations

        make_reservation(self.user, self.data["concert"], self.data["zone_standing"])
        self.assertEqual(expire_stale_reservations(), "Expired 0 reservations")

    def test_expire_stale_orders_deactivates_old_pending(self):
        from tickets.tasks import expire_stale_orders

        order = Order.objects.create(
            user=self.user, total_price=Decimal("100.00"), status=Order.Status.PENDING
        )
        order.created_at = timezone.now() - timedelta(minutes=31)
        order.save(update_fields=["created_at"])
        self.assertEqual(expire_stale_orders(), "Expired 1 orders")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)

    def test_expire_stale_orders_keeps_recent_pending(self):
        from tickets.tasks import expire_stale_orders

        Order.objects.create(
            user=self.user, total_price=Decimal("100.00"), status=Order.Status.PENDING
        )
        self.assertEqual(expire_stale_orders(), "Expired 0 orders")

    def test_expire_stale_orders_skips_paid(self):
        from tickets.tasks import expire_stale_orders

        order = Order.objects.create(
            user=self.user, total_price=Decimal("100.00"), status=Order.Status.PAID
        )
        order.created_at = timezone.now() - timedelta(minutes=60)
        order.save(update_fields=["created_at"])
        self.assertEqual(expire_stale_orders(), "Expired 0 orders")


class AdminAccessTest(TestCase):

    def setUp(self):
        self.data = make_infrastructure()
        self.admin = self.data["admin"]
        self.user = make_user()
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_admin_sees_all_reservations(self):
        make_reservation(self.user, self.data["concert"], self.data["zone_standing"])
        res = self.admin_client.get("/api/tickets/reservations/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(res.data["count"], 0)

    def test_admin_sees_all_orders(self):
        Order.objects.create(
            user=self.user, total_price=Decimal("100.00"), status=Order.Status.PENDING
        )
        res = self.admin_client.get("/api/tickets/orders/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(res.data["count"], 0)
