from django.contrib import admin
from .models import Venue, Hall, Artist, Category, Concert, Zone, Seat, Review


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "address")
    search_fields = ("name", "city")


@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = ("name", "venue")
    list_filter = ("venue",)


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Concert)
class ConcertAdmin(admin.ModelAdmin):
    list_display = ("title", "hall", "date", "created_by")
    list_filter = ("date", "hall", "categories")
    search_fields = ("title", "description")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "hall", "price", "capacity")
    list_filter = ("hall",)


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("zone", "row", "number")
    list_filter = ("zone",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "concert", "rating", "created_at")
    list_filter = ("rating", "concert")
