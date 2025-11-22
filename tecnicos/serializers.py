from rest_framework import serializers
from .models import Tecnico

class TecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tecnico
        fields = '__all__' # Envía todos los campos al frontend