from rest_framework import serializers
from users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "is_active",
            "date_joined",
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["phone"]
