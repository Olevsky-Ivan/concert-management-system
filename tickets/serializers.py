from django.utils import timezone
from rest_framework import serializers

from concerts.models import Concert, Seat, Zone
from tickets.models import RESERVATION_LIFETIME_MINUTES, Order, Reservation, Ticket
from decimal import Decimal


class ReservationSerializer(serializers.ModelSerializer):
    """
    Handles reservation creation and validation:
    - checks concert/zone consistency
    - validates seat availability
    - sets price and expiration time
    """
    user_email = serializers.ReadOnlyField(source="user.email")
    concert_title = serializers.ReadOnlyField(source="concert.title")
    zone_name = serializers.ReadOnlyField(source="zone.name")
    seat_label = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    concert = serializers.PrimaryKeyRelatedField(queryset=Concert.objects.all())
    zone = serializers.PrimaryKeyRelatedField(queryset=Zone.objects.all())
    seat = serializers.PrimaryKeyRelatedField(
        queryset=Seat.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Reservation
        fields = [
            "id",
            "user",
            "user_email",
            "concert",
            "concert_title",
            "zone",
            "zone_name",
            "seat",
            "seat_label",
            "price",
            "order",
            "expires_at",
            "is_active",
            "is_expired",
            "created_at",
        ]
        read_only_fields = [
            "user",
            "price",
            "order",
            "expires_at",
            "is_active",
            "is_expired",
            "created_at",
        ]

    def get_seat_label(self, obj):
        if obj.seat:
            return f"Row {obj.seat.row}, Seat {obj.seat.number}"
        return None

    def validate(self, attrs):
        concert = attrs["concert"]
        zone = attrs["zone"]
        seat = attrs.get("seat")

        if zone.hall_id != concert.hall_id:
            raise serializers.ValidationError(
                {"zone": "This zone does not belong to the concert's hall."}
            )

        if concert.is_past:
            raise serializers.ValidationError(
                {"concert": "Cannot reserve a seat for a past concert."}
            )

        # Expire stale reservations before checking availability
        Reservation.objects.filter(
            concert=concert,
            zone=zone,
            is_active=True,
            expires_at__lte=timezone.now(),
        ).update(is_active=False)

        if zone.has_seats:
            if seat is None:
                raise serializers.ValidationError(
                    {"seat": "A specific seat is required for this zone."}
                )
            if seat.zone_id != zone.pk:
                raise serializers.ValidationError(
                    {"seat": "This seat does not belong to the selected zone."}
                )
            if seat.is_taken_for_concert(concert.pk):
                raise serializers.ValidationError(
                    {"seat": "This seat is already taken."}
                )
        else:
            if zone.available_seats_count_for_concert(concert.pk) <= 0:
                raise serializers.ValidationError(
                    {"zone": "No available spots in this zone."}
                )

        return attrs

    # Sets price, expiration time and activates reservation before saving
    def create(self, validated_data):
        validated_data["price"] = validated_data["zone"].price
        validated_data["expires_at"] = timezone.now() + timezone.timedelta(
            minutes=RESERVATION_LIFETIME_MINUTES
        )
        validated_data["is_active"] = True
        return super().create(validated_data)


# Serializes reservation as an order item with readable concert/zone/seat info
class OrderItemSerializer(serializers.Serializer):
    reservation_id = serializers.IntegerField(source="id")
    concert = serializers.CharField(source="concert.title")
    zone = serializers.CharField(source="zone.name")
    seat = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)

    def get_seat(self, obj):
        if obj.seat:
            return f"Row {obj.seat.row}, Seat {obj.seat.number}"
        return "Standing"


# Returns order details with related reservations (items) and generated tickets
class OrderReadSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")
    items = serializers.SerializerMethodField()
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "user_email",
            "status",
            "total_price",
            "items",
            "tickets",
            "created_at",
            "paid_at",
        ]
        read_only_fields = fields

    def get_items(self, order):
        reservations = order.reservations.filter(is_active=True).select_related(
            "concert", "zone", "seat"
        )
        return OrderItemSerializer(reservations, many=True).data

    def get_tickets(self, order):
        return TicketSerializer(
            order.tickets.select_related("concert", "zone", "seat"), many=True
        ).data


# Provides aggregated cart summary including total price, items, and expiration info
class CartSummarySerializer(serializers.Serializer):
    items = OrderItemSerializer(many=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    expires_at = serializers.DateTimeField()  # earliest expiry in the cart
    item_count = serializers.IntegerField()


# Validates reservation ownership and status, then converts them into a paid order with tickets
class CheckoutSerializer(serializers.Serializer):
    reservation_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1
    )
    
    # Ensures reservations belong to user, are active, not expired, and not already ordered
    def validate_reservation_ids(self, ids):
        user = self.context["request"].user
        reservations = Reservation.objects.filter(
            id__in=ids,
            user=user,
            is_active=True,
            order__isnull=True,
        ).select_related("concert", "zone", "seat")

        if reservations.count() != len(set(ids)):
            raise serializers.ValidationError(
                "Some reservations are invalid, already ordered, or don't belong to you."
            )

        now = timezone.now()
        expired = [r for r in reservations if r.expires_at <= now]
        if expired:
            for r in expired:
                r.expire()
            raise serializers.ValidationError(
                "Some reservations have expired. Please re-add them to your cart."
            )

        self._reservations = list(reservations)
        return ids

    # Creates order, marks reservations inactive, and generates tickets in bulk
    def create_order(self):
        user = self.context["request"].user
        reservations = self._reservations

        total = sum(r.price for r in reservations)

        order = Order.objects.create(
            user=user,
            total_price=total,
            status=Order.Status.PAID,
            paid_at=timezone.now(),
        )

        tickets = []
        for reservation in reservations:
            reservation.order = order
            reservation.is_active = False
            reservation.save(update_fields=["order", "is_active"])

            tickets.append(Ticket(
                user=user,
                order=order,
                concert=reservation.concert,
                zone=reservation.zone,
                seat=reservation.seat,
                price=reservation.price,
                status=Ticket.Status.ACTIVE,
            ))

        Ticket.objects.bulk_create(tickets)
        return order


class TicketSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")
    concert_title = serializers.ReadOnlyField(source="concert.title")
    zone_name = serializers.ReadOnlyField(source="zone.name")
    seat_label = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "user",
            "user_email",
            "order",
            "concert",
            "concert_title",
            "zone",
            "zone_name",
            "seat",
            "seat_label",
            "price",
            "status",
            "purchased_at",
        ]
        read_only_fields = fields

    def get_seat_label(self, obj):
        if obj.seat:
            return f"Row {obj.seat.row}, Seat {obj.seat.number}"
        return "Standing"