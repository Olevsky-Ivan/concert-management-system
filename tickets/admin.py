from django.contrib import admin
from .models import Reservation, Order, Ticket


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "concert",
        "zone",
        "seat",
        "price",
        "is_active",
        "expires_at",
    )
    list_filter = ("is_active", "zone")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total_price", "created_at")
    list_filter = ("status",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "concert", "zone", "price", "status", "purchased_at")
    list_filter = ("status", "zone")
