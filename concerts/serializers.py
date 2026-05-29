from rest_framework import serializers

from concerts.models import (
    Artist,
    Category,
    Concert,
    Hall,
    Review,
    Seat,
    Venue,
    Zone,
)


class ArtistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = ["id", "name"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "name", "city", "address"]


class HallSerializer(serializers.ModelSerializer):
    venue_detail = VenueSerializer(source="venue", read_only=True)

    class Meta:
        model = Hall
        fields = ["id", "name", "venue", "venue_detail"]


class SeatSerializer(serializers.ModelSerializer):
    is_taken = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Seat
        fields = ["id", "row", "number", "is_taken"]


class ZoneListSerializer(serializers.ModelSerializer):
    available_seats = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = [
            "id",
            "name",
            "price",
            "capacity",
            "has_seats",
            "available_seats",
        ]

    # Returns number of available seats in this zone for a given concert (from serializer context)
    def get_available_seats(self, zone):
        concert_id = self.context.get("concert_id")
        if concert_id is None:
            return None
        return zone.available_seats_count_for_concert(concert_id)


class ZoneDetailSerializer(serializers.ModelSerializer):
    seats = serializers.SerializerMethodField()
    available_seats = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = [
            "id",
            "hall",
            "name",
            "price",
            "capacity",
            "has_seats",
            "available_seats",
            "seats",
        ]

    # Builds seat map for the zone and marks seats as taken based on concert_id from request query params
    def _concert_id(self):
        request = self.context.get("request")
        if request:
            return request.query_params.get("concert_id")
        return None

    def get_available_seats(self, zone):
        concert_id = self._concert_id()
        if concert_id is None:
            return None
        return zone.available_seats_count_for_concert(int(concert_id))

    def get_seats(self, zone):
        concert_id = self._concert_id()
        taken_ids = set()
        if concert_id is not None:
            taken_ids = zone.taken_seats_for_concert(int(concert_id))

        seats = zone.seats.all()
        data = []
        for seat in seats:
            data.append(
                {
                    "id": seat.id,
                    "row": seat.row,
                    "number": seat.number,
                    "is_taken": seat.pk in taken_ids,
                }
            )
        return data


class ZoneWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "hall", "name", "price", "capacity", "has_seats"]


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source="user.email")

    class Meta:
        model = Review
        fields = [
            "id",
            "user",
            "user_email",
            "concert",
            "rating",
            "comment",
            "created_at",
        ]
        read_only_fields = ["user", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        concert = attrs.get("concert")
        if concert and not concert.is_past:
            raise serializers.ValidationError(
                "You can only review concerts that have already taken place."
            )
        return attrs


class ConcertReadSerializer(serializers.ModelSerializer):
    hall = HallSerializer(read_only=True)
    artists = ArtistSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    zones = serializers.SerializerMethodField()
    created_by_email = serializers.ReadOnlyField(source="created_by.email")

    class Meta:
        model = Concert
        fields = [
            "id",
            "title",
            "description",
            "date",
            "created_by_email",
            "hall",
            "artists",
            "categories",
            "zones",
            "is_past",
            "created_at",
            "updated_at",
        ]

    def get_zones(self, concert):
        zones = concert.hall.zones.all()
        return ZoneListSerializer(
            zones,
            many=True,
            context={"concert_id": concert.pk},
        ).data


class ConcertWriteSerializer(serializers.ModelSerializer):
    artists = serializers.PrimaryKeyRelatedField(
        queryset=Artist.objects.all(), many=True, required=False
    )
    categories = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), many=True, required=False
    )
    hall = serializers.PrimaryKeyRelatedField(queryset=Hall.objects.all())
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Concert
        fields = [
            "id",
            "title",
            "description",
            "date",
            "hall",
            "artists",
            "categories",
            "created_by",
        ]

    # After write, return the full read representation
    def to_representation(self, instance):
        return ConcertReadSerializer(instance, context=self.context).data
