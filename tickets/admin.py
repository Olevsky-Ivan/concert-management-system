from django.contrib import admin
from .models import Ticket, Reservation


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "concert", "zone", "status", "price", "created_at")
    list_filter = ("status", "concert")
    search_fields = ("user__email",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "zone", "created_at", "expires_at")
    list_filter = ("created_at",)
