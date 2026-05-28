from django.utils import timezone

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from concerts.models import Zone
from tickets.models import Reservation, Ticket
from tickets.serializers import (
    ReservationSerializer,
    TicketSerializer,
)


class TicketViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == "admin":
            return Ticket.objects.all()

        return Ticket.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def buy(self, request):
        if request.user.role != "customer":
            return Response(
                {"detail": "Only customers can buy tickets"},
                status=status.HTTP_403_FORBIDDEN,
            )

        concert_id = request.data.get("concert_id")
        zone_id = request.data.get("zone_id")

        if not concert_id or not zone_id:
            return Response(
                {"detail": "concert_id and zone_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        zone = Zone.objects.filter(id=zone_id, concert_id=concert_id).first()

        if not zone:
            return Response(
                {"detail": "Zone not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if zone.available_seats() <= 0:
            return Response(
                {"detail": "No available seats"}, status=status.HTTP_400_BAD_REQUEST
            )

        ticket = Ticket.objects.create(
            user=request.user,
            concert_id=concert_id,
            zone=zone,
            price=zone.price,
            status=Ticket.Status.PAID,
        )

        serializer = TicketSerializer(ticket)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ticket = self.get_object()

        if ticket.user != request.user:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

        if ticket.status == Ticket.Status.CANCELED:
            return Response(
                {"detail": "Ticket already canceled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = Ticket.Status.CANCELED
        ticket.save()

        serializer = TicketSerializer(ticket)

        return Response(serializer.data)


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == "admin":
            return Reservation.objects.all()

        return Reservation.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        zone = serializer.validated_data["zone"]

        expired_reservations = zone.reservations.filter(
            expires_at__lte=timezone.now(), is_active=True
        )

        expired_reservations.update(is_active=False)

        if zone.available_seats() <= 0:
            raise serializer.ValidationError({"detail": "No available seats"})

        serializer.save(user=self.request.user)
