from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tickets.models import Ticket, Reservation
from tickets.serializers import TicketSerializer, ReservationSerializer


class TicketViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def buy(self, request):
        if request.user.role != "customer":
            return Response(
                {"detail": "Only customers can buy tickets"},
                status=status.HTTP_403_FORBIDDEN
            )

        concert_id = request.data.get("concert_id")
        zone_id = request.data.get("zone_id")

        if not concert_id or not zone_id:
            return Response(
                {"detail": "concert_id and zone_id required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        ticket = Ticket.objects.create(
            user=request.user,
            concert_id=concert_id,
            zone_id=zone_id,
            status="paid"
        )

        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ticket = self.get_object()

        if ticket.user != request.user:
            return Response(
                {"detail": "Not allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

        ticket.status = "canceled"
        ticket.save()

        return Response(TicketSerializer(ticket).data)


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)