from django.urls import path, include
from rest_framework.routers import DefaultRouter

from concerts.views import (
    ArtistViewSet,
    CategoryViewSet,
    ConcertViewSet,
    ReviewViewSet,
    ZoneViewSet,
    HallViewSet,
    VenueViewSet,
    SeatViewSet,
)

seat_list = SeatViewSet.as_view({"get": "list", "post": "create"})
seat_detail = SeatViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

router = DefaultRouter()

router.register("venues", VenueViewSet, basename="venue")
router.register("halls", HallViewSet, basename="hall")
router.register("concerts", ConcertViewSet, basename="concert")
router.register("artists", ArtistViewSet, basename="artist")
router.register("categories", CategoryViewSet, basename="category")
router.register("zones", ZoneViewSet, basename="zone")

review_list = ReviewViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

review_detail = ReviewViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "concerts/<int:concert_pk>/reviews/",
        review_list,
    ),
    path(
        "concerts/<int:concert_pk>/reviews/<int:pk>/",
        review_detail,
    ),
    path("zones/<int:zone_pk>/seats/", seat_list, name="zone-seat-list"),
    path("zones/<int:zone_pk>/seats/<int:pk>/", seat_detail, name="zone-seat-detail"),
]
