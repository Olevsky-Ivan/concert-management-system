from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from tickets.models import Ticket
from tickets.serializers import TicketSerializer
from rest_framework import mixins, viewsets


class TicketView(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):

    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer

    @action(methods=["POST"], detail=False)
    def buy(self, request):
        user = request.user

        concert_id = request.data.get("concert_id")
        zone_id = request.data.get("zone_id")

        if not concert_id or not zone_id:
            return Response(
                {"detail": "concert_id and zone_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket = Ticket.objects.create(
            user=user, concert_id=concert_id, zone_id=zone_id, status="paid"
        )

        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request):
        ticket = self.get_object()

        if ticket.user != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        ticket.status = "canceled"
        ticket.save()
        return Response({"status": "canceled"})
