from rest_framework import serializers
from .models import Cliente, OrdenTrabajo
from tecnicos.serializers import TecnicoSerializer

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'direccion', 'telefono', 'correo', 'fecha_registro']

class OrdenTrabajoSerializer(serializers.ModelSerializer):
    # Estos campos son de solo lectura y sirven para mostrar detalles completos en el dashboard
    tecnico_detalle = TecnicoSerializer(source='tecnico', read_only=True)
    cliente_detalle = ClienteSerializer(source='cliente', read_only=True)

    class Meta:
        model = OrdenTrabajo
        fields = [
            'id',
            'cliente',          # ID del cliente (para crear/actualizar)
            'cliente_detalle',  # Objeto completo del cliente (para mostrar)
            'tecnico',          # ID del técnico (para asignar)
            'tecnico_detalle',  # Objeto completo del técnico (para mostrar)
            'descripcion',
            'prioridad',
            'estado',
            'ubicacion_servicio',
            'fecha_creacion',
            'fecha_actualizacion',
            'evidencia_url',
            'observaciones',
        ]