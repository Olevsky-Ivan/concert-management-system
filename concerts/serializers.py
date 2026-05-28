from rest_framework import serializers
from .models import Concert, Artist, Category, Zone, Review


class ArtistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = ["id", "name"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "name", "price", "capacity", "concert"]


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "user", "concert", "rating", "comment"]


class ConcertSerializer(serializers.ModelSerializer):
    # WRITE (IDs)
    artists = serializers.PrimaryKeyRelatedField(
        queryset=Artist.objects.all(),
        many=True
    )

    categories = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True
    )

    # READ (nested)
    artists_detail = ArtistSerializer(source="artists", many=True, read_only=True)
    categories_detail = CategorySerializer(source="categories", many=True, read_only=True)
    zones = ZoneSerializer(many=True, read_only=True)

    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = Concert
        fields = [
            "id",
            "title",
            "city",
            "place",
            "date",
            "created_by",

            # write
            "artists",
            "categories",

            # read
            "artists_detail",
            "categories_detail",
            "zones",
        ]