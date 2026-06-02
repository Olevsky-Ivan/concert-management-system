from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tickets.views import OrderViewSet, ReservationViewSet, TicketViewSet

router = DefaultRouter()

router.register("reservations", ReservationViewSet, basename="reservation")
router.register("orders", OrderViewSet, basename="order")
router.register("tickets", TicketViewSet, basename="ticket")

urlpatterns = [
    path("", include(router.urls)),
]