from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

# Imports para magia de fechas
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMonth
from django.utils import timezone
import datetime

from .models import Cliente, OrdenTrabajo
from .serializers import ClienteSerializer, OrdenTrabajoSerializer
from tecnicos.models import Tecnico

# --- TUS VIEWSETS (MANTENIDOS) ---
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

        if nuevo_tecnico_id:
            try:
                tecnico = Tecnico.objects.get(id=nuevo_tecnico_id)
                tecnico.disponible = False
                tecnico.save()
            except Tecnico.DoesNotExist: pass 

        if nuevo_estado == 'TERMINADO' and orden.tecnico:
            try:
                tecnico_actual = orden.tecnico
                tecnico_actual.disponible = True
                tecnico_actual.save()
            except Tecnico.DoesNotExist: pass

        serializer.save()

# --- EL CEREBRO ANALÍTICO (NUEVA LÓGICA DE TIEMPO) ---
class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        periodo = request.query_params.get('periodo', 'semana')
        hoy = timezone.now()
        
        # Variables para llenar los gráficos
        fechas_grafico = []
        datos_reales = []
        datos_prediccion = [] # Solo calcularemos predicción para semana/mes

        # 1. CONFIGURAR FILTROS DE TIEMPO
        if periodo == 'hoy':
            # Rango: Desde las 00:00 de hoy hasta ahora
            inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
            filtro_creacion = {'fecha_creacion__gte': inicio}
            filtro_cierre = {'fecha_actualizacion__gte': inicio}
            
            # Agrupar por HORA
            datos_query = OrdenTrabajo.objects.filter(**filtro_creacion)\
                .annotate(tiempo=TruncHour('fecha_creacion'))\
                .values('tiempo').annotate(cantidad=Count('id')).order_by('tiempo')
            
            # Mapear resultados (rellenar horas vacías)
            mapa = {item['tiempo'].hour: item['cantidad'] for item in datos_query}
            # Mostrar las 24 horas (o hasta la hora actual)
            for h in range(24):
                fechas_grafico.append(f"{h:02d}:00")
                datos_reales.append(mapa.get(h, 0))
            
            # Sin predicción para "hoy" (muy volátil)
            datos_prediccion = [None] * 24

        elif periodo == 'anio':
            # Rango: Últimos 12 meses
            inicio = hoy - datetime.timedelta(days=365)
            filtro_creacion = {'fecha_creacion__gte': inicio}
            filtro_cierre = {'fecha_actualizacion__gte': inicio}

            # Agrupar por MES
            datos_query = OrdenTrabajo.objects.filter(**filtro_creacion)\
                .annotate(tiempo=TruncMonth('fecha_creacion'))\
                .values('tiempo').annotate(cantidad=Count('id')).order_by('tiempo')
            
            mapa = {item['tiempo'].strftime("%Y-%m"): item['cantidad'] for item in datos_query}
            
            # Generamos los últimos 12 meses
            fecha_iter = inicio.date().replace(day=1)
            for _ in range(12):
                key = fecha_iter.strftime("%Y-%m")
                label = fecha_iter.strftime("%b") # Ene, Feb...
                fechas_grafico.append(label)
                datos_reales.append(mapa.get(key, 0))
                # Avanzar un mes (truco seguro)
                next_month = fecha_iter.replace(day=28) + datetime.timedelta(days=4)
                fecha_iter = next_month.replace(day=1)
            
            datos_prediccion = [None] * 12

        else:
            # Por defecto: 'semana' (7 días) o 'mes' (30 días)
            dias = 30 if periodo == 'mes' else 7
            inicio = hoy - datetime.timedelta(days=dias-1)
            filtro_creacion = {'fecha_creacion__date__gte': inicio.date()}
            filtro_cierre = {'fecha_actualizacion__date__gte': inicio.date()}

            # Agrupar por DÍA
            datos_query = OrdenTrabajo.objects.filter(**filtro_creacion)\
                .annotate(tiempo=TruncDate('fecha_creacion'))\
                .values('tiempo').annotate(cantidad=Count('id')).order_by('tiempo')
            
            mapa = {item['tiempo']: item['cantidad'] for item in datos_query}
            
            for i in range(dias):
                fecha = (inicio + datetime.timedelta(days=i)).date()
                fechas_grafico.append(fecha.strftime("%d-%m"))
                datos_reales.append(mapa.get(fecha, 0))

            # CALCULAR PREDICCIÓN (Regresión Lineal Simple)
            # Solo vale la pena predecir si tenemos tendencia diaria
            if len(datos_reales) >= 2:
                x = list(range(len(datos_reales)))
                y = datos_reales
                n = len(x)
                sum_x = sum(x); sum_y = sum(y)
                sum_xy = sum(i*j for i, j in zip(x, y))
                sum_xx = sum(i*i for i in x)
                
                try:
                    m = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x**2)
                    b = (sum_y - m * sum_x) / n
                except ZeroDivisionError: m = 0; b = sum_y/n

                # Proyectar 3 días extra
                datos_prediccion = [None] * n # El pasado no se predice en el gráfico
                for i in range(1, 4):
                    val = m * (n + i) + b
                    datos_prediccion.append(max(0, round(val, 1)))
                    fechas_grafico.append(f"+{i}d") # Etiqueta futuro
                
                # Rellenar los datos reales con 'null' para el futuro
                datos_reales = datos_reales + [None]*3

        # 2. CALCULAR KPIs (Filtrados por el período)
        # Pendientes: Siempre mostramos el total actual (backlog), no tiene sentido filtrar por creación
        total_pendientes = OrdenTrabajo.objects.filter(estado='PENDIENTE').count()
        
        # En Proceso: Lo mismo, carga actual
        total_en_proceso = OrdenTrabajo.objects.filter(estado__in=['ASIGNADA', 'EN_CAMINO', 'EN_PROCESO']).count()
        
        # Terminadas: ESTE SÍ se filtra por el período seleccionado
        total_terminadas = OrdenTrabajo.objects.filter(estado='TERMINADO', **filtro_cierre).count()


        # 3. PRODUCTIVIDAD TÉCNICA (En el período seleccionado)
        # Filtro complejo para contar solo las terminadas en el rango de fechas
        # Usamos Q objects para filtrar dentro del Count
        
        # Primero, definimos la condición de fecha de cierre
        if periodo == 'hoy':
            condicion_fecha = Q(ordenes_asignadas__fecha_actualizacion__gte=inicio)
        else:
            condicion_fecha = Q(ordenes_asignadas__fecha_actualizacion__date__gte=inicio.date() if hasattr(inicio, 'date') else inicio)

        productividad = Tecnico.objects.annotate(
            completadas=Count(
                'ordenes_asignadas', 
                filter=Q(ordenes_asignadas__estado='TERMINADO') & condicion_fecha
            )
        ).values('nombre', 'completadas').order_by('-completadas')

        nombres_tecnicos = [t['nombre'] for t in productividad]
        ordenes_completadas = [t['completadas'] for t in productividad]


        # 4. HISTORIAL (En el período seleccionado)
        ultimas = OrdenTrabajo.objects.filter(estado='TERMINADO', **filtro_cierre).order_by('-fecha_actualizacion')[:10]
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
            'grafico_tendencia': {
                'fechas': fechas_grafico,
                'real': datos_reales,
                'prediccion': datos_prediccion
            },
            'grafico_tecnicos': {
                'categorias': nombres_tecnicos,
                'valores': ordenes_completadas
            },
            'historial': historial
        })