from django.urls import include, path
from rest_framework.routers import DefaultRouter

from concerts.views import (
    ArtistViewSet,
    CategoryViewSet,
    ConcertViewSet,
    ReviewViewSet,
    ZoneViewSet,
)

router = DefaultRouter()

router.register("concerts", ConcertViewSet, basename="concert")
router.register("artists", ArtistViewSet, basename="artist")
router.register("categories", CategoryViewSet, basename="category")
router.register("zones", ZoneViewSet, basename="zone")
router.register("reviews", ReviewViewSet, basename="review")

urlpatterns = [
    path("", include(router.urls)),
]