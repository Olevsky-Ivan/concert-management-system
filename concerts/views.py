from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from concerts.models import Artist, Category, Concert, Hall, Review, Venue, Zone, Seat
from concerts.permissions import IsAdminOrReadOnly, IsAdminUser

from concerts.serializers import (
    ArtistSerializer,
    CategorySerializer,
    ConcertReadSerializer,
    ConcertWriteSerializer,
    ReviewSerializer,
    ZoneDetailSerializer,
    ZoneWriteSerializer,
    HallSerializer,
    VenueSerializer,
    SeatSerializer,
)


class SeatViewSet(viewsets.ModelViewSet):
    serializer_class = SeatSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        zone_pk = self.kwargs.get("zone_pk")
        return Seat.objects.filter(zone_id=zone_pk)

    def perform_create(self, serializer):
        zone_pk = self.kwargs.get("zone_pk")
        serializer.save(zone_id=zone_pk)


class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]


class HallViewSet(viewsets.ModelViewSet):
    queryset = Hall.objects.select_related("venue")
    serializer_class = HallSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]


class ConcertViewSet(viewsets.ModelViewSet):
    queryset = Concert.objects.select_related(
        "hall__venue", "created_by"
    ).prefetch_related("artists", "categories")
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ConcertWriteSerializer
        return ConcertReadSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ArtistViewSet(viewsets.ModelViewSet):
    queryset = Artist.objects.all()
    serializer_class = ArtistSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("hall").prefetch_related("seats")
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ZoneWriteSerializer
        return ZoneDetailSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Review.objects.select_related("user", "concert")

        concert_pk = self.kwargs.get("concert_pk")

        if concert_pk:
            return qs.filter(concert_id=concert_pk)

        return qs.none()

    def perform_create(self, serializer):
        concert_pk = self.kwargs.get("concert_pk")
        serializer.save(user=self.request.user, concert_id=concert_pk)
