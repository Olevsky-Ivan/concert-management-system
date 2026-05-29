from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from concerts.models import Artist, Category, Concert, Review, Zone
from concerts.serializers import (
    ArtistSerializer,
    CategorySerializer,
    ConcertReadSerializer,
    ConcertWriteSerializer,
    ReviewSerializer,
    ZoneDetailSerializer,
    ZoneWriteSerializer,
)


class ConcertViewSet(viewsets.ModelViewSet):
    queryset = Concert.objects.select_related(
        "hall__venue", "created_by"
    ).prefetch_related("artists", "categories")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ConcertWriteSerializer
        return ConcertReadSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ArtistViewSet(viewsets.ModelViewSet):
    queryset = Artist.objects.all()
    serializer_class = ArtistSerializer
    permission_classes = [IsAuthenticated]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("hall").prefetch_related("seats")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ZoneWriteSerializer
        return ZoneDetailSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related("user", "concert")
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        concert_id = self.request.query_params.get("concert_id")
        if concert_id:
            qs = qs.filter(concert_id=concert_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)