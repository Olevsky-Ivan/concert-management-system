from django.contrib import admin
from .models import Concert, Zone, Artist, Category, Review


@admin.register(Concert)
class ConcertAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "city", "place", "date", "created_by")
    list_filter = ("city", "date")
    search_fields = ("title", "city", "place")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "concert", "price", "capacity")
    list_filter = ("concert",)


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "concert", "rating")
    list_filter = ("rating",)
