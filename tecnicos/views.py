from django.shortcuts import render

from rest_framework import viewsets
from .models import Tecnico
from .serializers import TecnicoSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ordenes.models import OrdenTrabajo
from ordenes.serializers import OrdenTrabajoSerializer


class TecnicoViewSet(viewsets.ModelViewSet):
    queryset = Tecnico.objects.all()
    serializer_class = TecnicoSerializer
    filterset_fields = ['disponible', 'especialidad']
    filter_backends = [DjangoFilterBackend]
    ordering_fields = ['nombre', 'especialidad']


class MisOrdenesView(APIView):
    """
    Un endpoint de API privado para que un técnico vea
    SOLO sus órdenes asignadas (Asignadas, En Camino, En Proceso).
    """
    permission_classes = [IsAuthenticated] # ¡Solo usuarios logueados!

    def get(self, request, *args, **kwargs):
        try:
            # 1. Encuentra el perfil técnico "linkeado" al usuario logueado
            tecnico = request.user.perfil_tecnico
        except Tecnico.DoesNotExist:
            # Si el usuario no es un técnico (ej. es admin), devuelve lista vacía
            return Response({"error": "No eres un técnico válido"}, status=403)

        # 2. Filtra las órdenes asignadas a ESE técnico
        estados_activos = ['ASIGNADA', 'EN_CAMINO', 'EN_PROCESO']
        ordenes = OrdenTrabajo.objects.filter(
            tecnico=tecnico,
            estado__in=estados_activos
        ).order_by('fecha_actualizacion')
        
        # 3. Serializa y devuelve los datos
        serializer = OrdenTrabajoSerializer(ordenes, many=True)
        return Response(serializer.data)