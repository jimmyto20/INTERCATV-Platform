from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
import datetime

from .models import Cliente, OrdenTrabajo
from .serializers import ClienteSerializer, OrdenTrabajoSerializer
from tecnicos.models import Tecnico

# --- VIEWSETS EXISTENTES (Para que siga funcionando el gestor) ---
class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    search_fields = ['nombre', 'telefono']
    filter_backends = [SearchFilter]

class OrdenTrabajoViewSet(viewsets.ModelViewSet):
    queryset = OrdenTrabajo.objects.all()
    serializer_class = OrdenTrabajoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['estado', 'prioridad', 'tecnico']
    search_fields = ['cliente__nombre', 'descripcion', 'id']
    ordering_fields = ['fecha_creacion', 'prioridad']
    ordering = ['-fecha_creacion']

    def perform_update(self, serializer):
        orden = serializer.instance 
        nuevo_estado = self.request.data.get('estado')
        nuevo_tecnico_id = self.request.data.get('tecnico')

        # Si asignan técnico, lo marcamos ocupado
        if nuevo_tecnico_id:
            try:
                tecnico = Tecnico.objects.get(id=nuevo_tecnico_id)
                tecnico.disponible = False
                tecnico.save()
            except Tecnico.DoesNotExist:
                pass 

        # Si terminan la orden, liberamos al técnico
        if nuevo_estado == 'TERMINADO' and orden.tecnico:
            try:
                tecnico_actual = orden.tecnico
                tecnico_actual.disponible = True
                tecnico_actual.save()
            except Tecnico.DoesNotExist:
                pass

        serializer.save()

# --- NUEVA VISTA DE ESTADÍSTICAS (EL CEREBRO DEL DASHBOARD) ---
class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        # 1. KPIs Generales
        total_pendientes = OrdenTrabajo.objects.filter(estado='PENDIENTE').count()
        total_en_proceso = OrdenTrabajo.objects.filter(estado__in=['ASIGNADA', 'EN_CAMINO', 'EN_PROCESO']).count()
        total_terminadas = OrdenTrabajo.objects.filter(estado='TERMINADO').count()

        # 2. Productividad por Técnico (Gráfico de Barras)
        productividad = Tecnico.objects.annotate(
            completadas=Count('ordenes_asignadas', filter=Q(ordenes_asignadas__estado='TERMINADO'))
        ).values('nombre', 'completadas').order_by('-completadas')

        nombres_tecnicos = [t['nombre'] for t in productividad]
        ordenes_completadas = [t['completadas'] for t in productividad]

        # 3. Tendencia y Predicción (Gráfico de Línea)
        hoy = timezone.now().date()
        hace_7_dias = hoy - datetime.timedelta(days=6)
        
        # Agrupar órdenes creadas por día
        ordenes_por_dia = OrdenTrabajo.objects.filter(
            fecha_creacion__date__gte=hace_7_dias
        ).annotate(dia=TruncDate('fecha_creacion')).values('dia').annotate(cantidad=Count('id')).order_by('dia')

        # Rellenar días vacíos con 0
        mapa_datos = {item['dia']: item['cantidad'] for item in ordenes_por_dia}
        fechas = []
        datos_reales = []
        
        for i in range(7):
            fecha = hace_7_dias + datetime.timedelta(days=i)
            fechas.append(fecha.strftime("%d-%m"))
            datos_reales.append(mapa_datos.get(fecha, 0))

        # Algoritmo de Regresión Lineal Simple (y = mx + b)
        def predecir_demanda(datos):
            n = len(datos)
            if n < 2 or sum(datos) == 0: return [0] * 7 
            
            x = list(range(n))
            y = datos
            
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(i*j for i, j in zip(x, y))
            sum_xx = sum(i*i for i in x)
            
            try:
                m = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x**2)
                b = (sum_y - m * sum_x) / n
            except ZeroDivisionError:
                m = 0
                b = sum_y / n

            proyeccion = []
            for i in range(n, n + 7):
                val = m * i + b
                proyeccion.append(max(0, round(val, 1)))
            return proyeccion

        datos_prediccion = predecir_demanda(datos_reales)
        fechas_futuras = [(hoy + datetime.timedelta(days=i+1)).strftime("%d-%m") for i in range(7)]

        # 4. Historial Reciente
        ultimas = OrdenTrabajo.objects.filter(estado='TERMINADO').order_by('-fecha_actualizacion')[:5]
        historial = [{
            'id': o.id,
            'tecnico': o.tecnico.nombre if o.tecnico else 'N/A',
            'cliente': o.cliente.nombre,
            'fecha': o.fecha_actualizacion.strftime("%d/%m %H:%M")
        } for o in ultimas]

        return Response({
            'kpis': {
                'pendientes': total_pendientes,
                'en_proceso': total_en_proceso,
                'terminadas': total_terminadas
            },
            'grafico_tecnicos': {
                'categorias': nombres_tecnicos, 
                'valores': ordenes_completadas
            },
            'grafico_tendencia': {
                'fechas': fechas + fechas_futuras,
                'real': datos_reales,
                'prediccion': [None]*7 + datos_prediccion
            },
            'historial': historial
        })