from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

import csv
import io
from django.http import HttpResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

# Imports para manejo de fechas y estadísticas
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMonth
from django.utils import timezone
import datetime
from django.conf import settings
import os

# --- IMPORTS DE TUS MODELOS ---
from .models import Cliente, OrdenTrabajo

# Intentamos importar Tecnico. Si está en otra app 'tecnicos', se ajusta aquí.
try:
    from tecnicos.models import Tecnico
except ImportError:
    # Fallback por si Tecnico está en la misma carpeta o models global
    from .models import Tecnico

from .serializers import ClienteSerializer, OrdenTrabajoSerializer


# =====================================================
# Helper para leer técnicos (soporta multi-selección)
# =====================================================

def get_tecnico_ids_from_request(request):
    """
    Lee técnicos desde la querystring y devuelve SOLO IDs válidos (enteros).
    Soporta:
      - ?tecnicos=1&tecnicos=2&tecnicos=3
      - ?tecnico=1  (modo antiguo, compatibilidad)
    Ignora valores como 'todos', 'all', 'on', '', etc.
    """
    tecnicos_ids = request.query_params.getlist('tecnicos')

    # compatibilidad con ?tecnico=...
    single_tecnico = request.query_params.get('tecnico')
    if not tecnicos_ids and single_tecnico:
        tecnicos_ids = [single_tecnico]

    clean_ids = []
    for t in tecnicos_ids:
        if not t:
            continue

        t_str = str(t).strip().lower()
        if t_str in ('todos', 'all', 'on', '(seleccionar todo)'):
            # lo ignoramos, no es un ID
            continue

        # nos quedamos sólo con valores que se puedan convertir a int
        try:
            clean_ids.append(int(t))
        except (TypeError, ValueError):
            continue

    return clean_ids


# ==========================================
# 1. VIEWSETS PRINCIPALES (CRUD)
# ==========================================

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

    # Esta función maneja actualizaciones desde el ADMIN o API REST estándar
    def perform_update(self, serializer):
        orden = serializer.instance

        # Datos nuevos que vienen en la petición
        nuevo_estado = self.request.data.get('estado')
        nuevo_tecnico_id = self.request.data.get('tecnico')

        # Si se asigna un nuevo técnico, lo marcamos como OCUPADO
        if nuevo_tecnico_id:
            try:
                tecnico = Tecnico.objects.get(id=nuevo_tecnico_id)
                tecnico.disponible = False
                tecnico.save()
            except Tecnico.DoesNotExist:
                pass

        # Si la orden se TERMINA, liberamos al técnico actual
        if nuevo_estado == 'TERMINADO' and orden.tecnico:
            try:
                tecnico_actual = orden.tecnico
                tecnico_actual.disponible = True
                tecnico_actual.save()
            except Tecnico.DoesNotExist:
                pass

        serializer.save()


# ==========================================
# 2. DASHBOARD Y ESTADÍSTICAS (CON GRÁFICOS + SLA)
# ==========================================

class DashboardStatsView(APIView):
    """
    Devuelve KPIs, gráficas de tendencia, gráfica por técnico,
    ranking, alertas y detalle para modales.
    """
    permission_classes = [IsAuthenticated]

    SLA_HOURS = 48
    SOBRECARGA_UMBRAL = 5  # órdenes activas por técnico para marcar sobrecarga

    def get(self, request, format=None):
        hoy = timezone.now().date()

        # ----- Parámetros de filtro -----
        periodo = request.query_params.get('periodo', 'mes')  # hoy, semana, mes, anio, personalizado
        tecnicos_ids = get_tecnico_ids_from_request(request)
        inicio_str = request.query_params.get('inicio', None)
        fin_str = request.query_params.get('fin', None)

        # ----- Rango de fechas -----
        if periodo == 'hoy':
            desde = hoy
            hasta = hoy
        elif periodo == 'semana':
            desde = hoy - datetime.timedelta(days=6)
            hasta = hoy
        elif periodo == 'anio':
            desde = hoy - datetime.timedelta(days=365)
            hasta = hoy
        elif periodo == 'personalizado' and inicio_str and fin_str:
            try:
                desde = datetime.datetime.strptime(inicio_str, "%Y-%m-%d").date()
                hasta = datetime.datetime.strptime(fin_str, "%Y-%m-%d").date()
            except ValueError:
                desde = hoy - datetime.timedelta(days=29)
                hasta = hoy
        else:  # mes (por defecto)
            desde = hoy - datetime.timedelta(days=29)
            hasta = hoy

        # ----- Query base -----
        qs = OrdenTrabajo.objects.filter(
            fecha_creacion__date__gte=desde,
            fecha_creacion__date__lte=hasta
        )

        # filtro múltiple por técnicos (ya limpio)
        if tecnicos_ids:
            qs = qs.filter(tecnico_id__in=tecnicos_ids)

        # =========================
        # 1) KPIs PRINCIPALES
        # =========================
        pendientes_qs = qs.filter(
            estado__in=['Pendiente de Asignación', 'PENDIENTE']
        )

        en_proceso_qs = qs.filter(
            estado__in=[
                'Técnico en Camino',
                'En Proceso',
                'ASIGNADA',
                'EN_CAMINO',
                'EN_PROCESO',
            ]
        )

        terminadas_qs = qs.filter(
            estado__in=['Trabajo Terminado', 'TERMINADO']
        )

        pendientes = pendientes_qs.count()
        en_proceso = en_proceso_qs.count()
        terminadas = terminadas_qs.count()
        total_periodo = qs.count()

        productividad_tecnica = round(terminadas * 100 / total_periodo, 1) if total_periodo > 0 else 0.0

        porcentaje_pendientes = round(pendientes * 100 / total_periodo, 1) if total_periodo > 0 else 0.0
        porcentaje_en_proceso = round(en_proceso * 100 / total_periodo, 1) if total_periodo > 0 else 0.0
        porcentaje_terminadas = round(terminadas * 100 / total_periodo, 1) if total_periodo > 0 else 0.0

        # =========================
        # 2) SLA Y TIEMPO PROMEDIO
        # =========================
        avg_hours = 0.0
        sla_porcentaje = 0.0
        sla_fuera = 0

        if terminadas > 0:
            duraciones_horas = []
            sla_ok_count = 0

            for ot in terminadas_qs:
                fecha_inicio = ot.fecha_creacion
                fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion

                delta = fecha_cierre - fecha_inicio
                horas = delta.total_seconds() / 3600.0
                duraciones_horas.append(horas)

                if horas <= self.SLA_HOURS:
                    sla_ok_count += 1

            if duraciones_horas:
                avg_hours = sum(duraciones_horas) / len(duraciones_horas)

            sla_porcentaje = round(sla_ok_count * 100 / terminadas, 1)
            sla_fuera = terminadas - sla_ok_count

        # =========================
        # 3) GRÁFICO DE TENDENCIA
        # =========================
        por_dia = (
            qs.annotate(fecha=TruncDate('fecha_creacion'))
              .values('fecha')
              .annotate(cantidad=Count('id'))
              .order_by('fecha')
        )
        mapa_dias = {item['fecha']: item['cantidad'] for item in por_dia}

        fechas_grafico = []
        datos_reales = []
        dia = desde
        while dia <= hasta:
            fechas_grafico.append(dia.strftime('%d-%m'))
            datos_reales.append(mapa_dias.get(dia, 0))
            dia += datetime.timedelta(days=1)

        datos_prediccion = [None] * len(fechas_grafico)

        # =========================
        # 4) GRÁFICO POR TÉCNICO
        # =========================
        por_tecnico = (
            qs.values('tecnico__nombre')
              .annotate(cantidad=Count('id'))
              .order_by('-cantidad')
        )

        categorias_tecnicos = [
            (item['tecnico__nombre'] or 'Sin técnico') for item in por_tecnico
        ]
        valores_tecnicos = [item['cantidad'] for item in por_tecnico]

        # =========================
        # 5) GRÁFICO DE ESTADOS (PIE)
        # =========================
        grafico_estados = {
            "labels": ['Pendientes', 'En ejecución', 'Terminadas'],
            "valores": [pendientes, en_proceso, terminadas],
        }

        # =========================
        # 6) HISTORIAL ÚLTIMAS ÓRDENES
        # =========================
        historial = []
        for ot in terminadas_qs.order_by('-fecha_creacion')[:10]:
            fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
            historial.append({
                "id": ot.id,
                "tecnico": str(getattr(ot, "tecnico", "")),
                "cliente": str(getattr(ot, "cliente", "")),
                "fecha_cierre": fecha_cierre.strftime("%d-%m-%Y %H:%M") if fecha_cierre else "",
            })

        # =========================
        # 7) RANKING TÉCNICOS (solo terminadas)
        # =========================
        ranking_tecnicos = []
        ranking_base = (
            terminadas_qs
            .values('tecnico_id', 'tecnico__nombre')
            .annotate(terminadas=Count('id'))
            .order_by('-terminadas')
        )

        for item in ranking_base:
            tec_id = item['tecnico_id']
            nombre = item['tecnico__nombre'] or 'Sin técnico'
            tec_qs = terminadas_qs.filter(tecnico_id=tec_id)

            total_tec = tec_qs.count()
            if total_tec == 0:
                continue

            duraciones = []
            sla_ok_tec = 0
            for ot in tec_qs:
                fecha_inicio = ot.fecha_creacion
                fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
                delta = fecha_cierre - fecha_inicio
                horas = delta.total_seconds() / 3600.0
                duraciones.append(horas)
                if horas <= self.SLA_HOURS:
                    sla_ok_tec += 1

            avg_tec = sum(duraciones) / len(duraciones) if duraciones else 0.0
            sla_tec = round(sla_ok_tec * 100 / total_tec, 1)

            ranking_tecnicos.append({
                "id": tec_id,
                "nombre": nombre,
                "terminadas": total_tec,
                "tiempo_promedio_cierre_horas": avg_tec,
                "sla_porcentaje": sla_tec,
            })

        # =========================
        # 8) ALERTAS OPERACIONALES
        # =========================
        alertas = []
        alertas_detalle = {
            "pendientes_vencidas": 0,
            "tecnicos_sobrecarga": [],
            "umbral_sobrecarga": self.SOBRECARGA_UMBRAL,
        }

        # pendientes vencidas
        limite_vencida = timezone.now() - datetime.timedelta(hours=self.SLA_HOURS)
        pendientes_vencidas_qs = pendientes_qs.filter(fecha_creacion__lte=limite_vencida)
        num_vencidas = pendientes_vencidas_qs.count()
        alertas_detalle["pendientes_vencidas"] = num_vencidas

        if num_vencidas > 0:
            alertas.append(
                f"Hay {num_vencidas} órdenes pendientes hace más de {self.SLA_HOURS} horas."
            )

        # técnicos con sobrecarga (órdenes activas)
        activos_qs = en_proceso_qs
        por_tecnico_activos = (
            activos_qs
            .values('tecnico__id', 'tecnico__nombre')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')
        )

        tecnicos_sobrecarga = []
        for item in por_tecnico_activos:
            if item['cantidad'] >= self.SOBRECARGA_UMBRAL:
                tecnicos_sobrecarga.append({
                    "id": item['tecnico__id'],
                    "nombre": item['tecnico__nombre'] or 'Sin técnico',
                    "cantidad": item['cantidad'],
                })

        alertas_detalle["tecnicos_sobrecarga"] = tecnicos_sobrecarga

        if tecnicos_sobrecarga:
            nombres = ", ".join(t["nombre"] for t in tecnicos_sobrecarga)
            alertas.append(
                f"Técnicos con alta carga de trabajo (≥{self.SOBRECARGA_UMBRAL} órdenes activas): {nombres}."
            )

        # =========================
        # 9) DETALLE PARA MODALES
        # =========================
        def serialize_ot(ot, usar_cierre=False):
            if usar_cierre:
                fecha = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
            else:
                fecha = ot.fecha_creacion
            return {
                "id": ot.id,
                "tecnico": str(getattr(ot, "tecnico", "")),
                "cliente": str(getattr(ot, "cliente", "")),
                "fecha": fecha.strftime("%d-%m-%Y %H:%M") if fecha else "",
                "estado": ot.estado,
            }

        detalle_pendientes = [
            serialize_ot(ot) for ot in pendientes_qs.order_by('-fecha_creacion')[:200]
        ]
        detalle_en_ejecucion = [
            serialize_ot(ot) for ot in en_proceso_qs.order_by('-fecha_creacion')[:200]
        ]
        detalle_terminadas = [
            serialize_ot(ot, usar_cierre=True) for ot in terminadas_qs.order_by('-fecha_creacion')[:200]
        ]

        # ----- Lista de técnicos para filtros -----
        lista_tecnicos = list(Tecnico.objects.all().values('id', 'nombre'))

        data = {
            # KPIs "planos"
            "total_ordenes": total_periodo,
            "kpis_pendientes": pendientes,
            "kpis_en_proceso": en_proceso,
            "kpis_terminadas": terminadas,
            "productividad_tecnica": productividad_tecnica,

            # Porcentajes
            "porcentaje_pendientes": porcentaje_pendientes,
            "porcentaje_en_proceso": porcentaje_en_proceso,
            "porcentaje_terminadas": porcentaje_terminadas,

            # NUEVOS KPIs
            "kpi_tiempo_promedio_cierre_horas": round(avg_hours, 1),
            "kpi_sla_porcentaje": sla_porcentaje,
            "kpi_sla_fuera": sla_fuera,

            # Historial tabla
            "historial": historial,

            # Gráficos
            "grafico_tendencia": {
                "fechas": fechas_grafico,
                "real": datos_reales,
                "prediccion": datos_prediccion,
            },
            "grafico_tecnicos": {
                "categorias": categorias_tecnicos,
                "valores": valores_tecnicos,
            },
            "grafico_estados": grafico_estados,

            # Ranking y alertas
            "ranking_tecnicos": ranking_tecnicos,
            "alertas": alertas,
            "alertas_detalle": alertas_detalle,

            # Detalles para modales
            "detalle_pendientes": detalle_pendientes,
            "detalle_en_ejecucion": detalle_en_ejecucion,
            "detalle_terminadas": detalle_terminadas,

            # Filtros (técnicos)
            "filtros_disponibles": lista_tecnicos,

            # Respaldo agrupado
            "kpis": {
                "total": total_periodo,
                "pendientes": pendientes,
                "en_proceso": en_proceso,
                "terminadas": terminadas,
                "productividad_tecnica": productividad_tecnica,
                "tiempo_promedio_cierre_horas": round(avg_hours, 1),
                "sla_porcentaje": sla_porcentaje,
                "sla_fuera": sla_fuera,
                "porcentaje_pendientes": porcentaje_pendientes,
                "porcentaje_en_proceso": porcentaje_en_proceso,
                "porcentaje_terminadas": porcentaje_terminadas,
            },
        }

        return Response(data, status=200)


class DashboardHistorialCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        hoy = timezone.now().date()

        periodo = request.query_params.get('periodo', 'mes')
        tecnicos_ids = get_tecnico_ids_from_request(request)
        inicio_str = request.query_params.get('inicio', None)
        fin_str = request.query_params.get('fin', None)

        # --- mismo cálculo de rango de fechas que DashboardStatsView ---
        if periodo == 'hoy':
            desde = hoy
            hasta = hoy
        elif periodo == 'semana':
            desde = hoy - datetime.timedelta(days=6)
            hasta = hoy
        elif periodo == 'anio':
            desde = hoy - datetime.timedelta(days=365)
            hasta = hoy
        elif periodo == 'personalizado' and inicio_str and fin_str:
            try:
                desde = datetime.datetime.strptime(inicio_str, "%Y-%m-%d").date()
                hasta = datetime.datetime.strptime(fin_str, "%Y-%m-%d").date()
            except ValueError:
                desde = hoy - datetime.timedelta(days=29)
                hasta = hoy
        else:  # mes por defecto
            desde = hoy - datetime.timedelta(days=29)
            hasta = hoy

        qs = OrdenTrabajo.objects.filter(
            fecha_creacion__date__gte=desde,
            fecha_creacion__date__lte=hasta
        )

        if tecnicos_ids:
            qs = qs.filter(tecnico_id__in=tecnicos_ids)

        terminadas_qs = qs.filter(
            estado__in=['Trabajo Terminado', 'TERMINADO']
        ).order_by('-fecha_creacion')

        # --- construir CSV ---
        filename = f"historial_ordenes_{desde.strftime('%Y%m%d')}_{hasta.strftime('%Y%m%d')}.csv"

        # importante: charset y BOM para Excel
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')  # BOM UTF-8

        # separador con punto y coma para Excel en español
        writer = csv.writer(response, delimiter=';')

        writer.writerow([
            'ID',
            'Técnico',
            'Cliente',
            'Estado',
            'Fecha creación',
            'Fecha cierre',
        ])

        for ot in terminadas_qs:
            fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
            writer.writerow([
                ot.id,
                str(getattr(ot, 'tecnico', '') or ''),
                str(getattr(ot, 'cliente', '') or ''),
                ot.get_estado_display() if hasattr(ot, 'get_estado_display') else ot.estado,
                ot.fecha_creacion.strftime("%Y-%m-%d %H:%M") if ot.fecha_creacion else '',
                fecha_cierre.strftime("%Y-%m-%d %H:%M") if fecha_cierre else '',
            ])

        return response


class DashboardPDFView(APIView):
    """
    Genera un informe gerencial en PDF con:
    - KPIs del período
    - Ranking de técnicos
    - Gráfico de órdenes por técnico (barras)
    - Historial de órdenes cerradas
    - Alertas operacionales
    """
    permission_classes = [IsAuthenticated]

    def _rango_fechas(self, periodo, hoy, inicio_str, fin_str):
        """Mismo cálculo de rango de fechas que el DashboardStatsView."""
        if periodo == 'hoy':
            desde = hoy
            hasta = hoy
        elif periodo == 'semana':
            desde = hoy - datetime.timedelta(days=6)
            hasta = hoy
        elif periodo == 'anio':
            desde = hoy - datetime.timedelta(days=365)
            hasta = hoy
        elif periodo == 'personalizado' and inicio_str and fin_str:
            try:
                desde = datetime.datetime.strptime(inicio_str, "%Y-%m-%d").date()
                hasta = datetime.datetime.strptime(fin_str, "%Y-%m-%d").date()
            except ValueError:
                desde = hoy - datetime.timedelta(days=29)
                hasta = hoy
        else:  # mes por defecto
            desde = hoy - datetime.timedelta(days=29)
            hasta = hoy

        return desde, hasta

    def get(self, request, format=None):
        hoy = timezone.now().date()

        periodo = request.query_params.get('periodo', 'mes')
        tecnicos_ids = get_tecnico_ids_from_request(request)
        inicio_str = request.query_params.get('inicio', None)
        fin_str = request.query_params.get('fin', None)

        # -------- RANGO DE FECHAS (igual al dashboard) --------
        desde, hasta = self._rango_fechas(periodo, hoy, inicio_str, fin_str)

        # -------- QUERY BASE --------
        qs = OrdenTrabajo.objects.filter(
            fecha_creacion__date__gte=desde,
            fecha_creacion__date__lte=hasta
        )

        if tecnicos_ids:
            qs = qs.filter(tecnico_id__in=tecnicos_ids)

        # -------- KPIs PRINCIPALES --------
        pendientes_qs = qs.filter(
            estado__in=['Pendiente de Asignación', 'PENDIENTE']
        )
        en_proceso_qs = qs.filter(
            estado__in=[
                'Técnico en Camino',
                'En Proceso',
                'ASIGNADA',
                'EN_CAMINO',
                'EN_PROCESO',
            ]
        )
        terminadas_qs = qs.filter(
            estado__in=['Trabajo Terminado', 'TERMINADO']
        )

        pendientes = pendientes_qs.count()
        en_proceso = en_proceso_qs.count()
        terminadas = terminadas_qs.count()
        total_periodo = qs.count()

        productividad_tecnica = round(terminadas * 100 / total_periodo, 1) if total_periodo > 0 else 0.0

        porcentaje_pendientes = round(pendientes * 100 / total_periodo, 1) if total_periodo > 0 else 0.0
        porcentaje_en_proceso = round(en_proceso * 100 / total_periodo, 1) if total_periodo > 0 else 0.0
        porcentaje_terminadas = round(terminadas * 100 / total_periodo, 1) if total_periodo > 0 else 0.0

        # -------- SLA Y TIEMPO PROMEDIO --------
        SLA_HOURS = 48
        avg_hours = 0.0
        sla_porcentaje = 0.0
        sla_fuera = 0

        if terminadas > 0:
            duraciones_horas = []
            sla_ok_count = 0

            for ot in terminadas_qs:
                fecha_inicio = ot.fecha_creacion
                fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion

                delta = fecha_cierre - fecha_inicio
                horas = delta.total_seconds() / 3600.0
                duraciones_horas.append(horas)

                if horas <= SLA_HOURS:
                    sla_ok_count += 1

            if duraciones_horas:
                avg_hours = sum(duraciones_horas) / len(duraciones_horas)

            sla_porcentaje = round(sla_ok_count * 100 / terminadas, 1)
            sla_fuera = terminadas - sla_ok_count

        # -------- GRÁFICO ÓRDENES POR TÉCNICO --------
        por_tecnico = (
            qs.values('tecnico__nombre')
              .annotate(cantidad=Count('id'))
              .order_by('-cantidad')
        )
        categorias_tecnicos = [(item['tecnico__nombre'] or 'Sin técnico') for item in por_tecnico]
        valores_tecnicos = [item['cantidad'] for item in por_tecnico]

        # -------- RANKING TÉCNICOS (solo terminadas) --------
        ranking_tecnicos = []
        ranking_base = (
            terminadas_qs
            .values('tecnico_id', 'tecnico__nombre')
            .annotate(terminadas=Count('id'))
            .order_by('-terminadas')
        )

        for item in ranking_base:
            tec_id = item['tecnico_id']
            nombre = item['tecnico__nombre'] or 'Sin técnico'
            tec_qs = terminadas_qs.filter(tecnico_id=tec_id)

            total_tec = tec_qs.count()
            if total_tec == 0:
                continue

            duraciones = []
            sla_ok_tec = 0
            for ot in tec_qs:
                fecha_inicio = ot.fecha_creacion
                fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
                delta = fecha_cierre - fecha_inicio
                horas = delta.total_seconds() / 3600.0
                duraciones.append(horas)
                if horas <= SLA_HOURS:
                    sla_ok_tec += 1

            avg_tec = sum(duraciones) / len(duraciones) if duraciones else 0.0
            sla_tec = round(sla_ok_tec * 100 / total_tec, 1)

            ranking_tecnicos.append({
                "id": tec_id,
                "nombre": nombre,
                "terminadas": total_tec,
                "tiempo_promedio_cierre_horas": avg_tec,
                "sla_porcentaje": sla_tec,
            })

        # -------- HISTORIAL ÚLTIMAS ÓRDENES --------
        historial = []
        for ot in terminadas_qs.order_by('-fecha_creacion')[:30]:
            fecha_cierre = getattr(ot, 'fecha_cierre', None) or ot.fecha_creacion
            historial.append([
                ot.id,
                str(getattr(ot, "tecnico", "")),
                str(getattr(ot, "cliente", "")),
                fecha_cierre.strftime("%d-%m-%Y %H:%M") if fecha_cierre else "",
            ])

        # -------- ALERTAS OPERACIONALES (resumen) --------
        alertas = []

        limite_vencida = timezone.now() - datetime.timedelta(hours=SLA_HOURS)
        pendientes_vencidas_qs = pendientes_qs.filter(fecha_creacion__lte=limite_vencida)
        num_vencidas = pendientes_vencidas_qs.count()
        if num_vencidas > 0:
            alertas.append(
                f"Hay {num_vencidas} órdenes pendientes hace más de {SLA_HOURS} horas."
            )

        SOBRECARGA_UMBRAL = 5
        activos_qs = en_proceso_qs
        por_tecnico_activos = (
            activos_qs
            .values('tecnico__nombre')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')
        )
        tecnicos_sobrecarga = [
            f"{item['tecnico__nombre'] or 'Sin técnico'} ({item['cantidad']} órdenes)"
            for item in por_tecnico_activos
            if item['cantidad'] >= SOBRECARGA_UMBRAL
        ]
        if tecnicos_sobrecarga:
            alertas.append(
                "Técnicos con alta carga de trabajo (≥5 órdenes activas): "
                + ", ".join(tecnicos_sobrecarga)
            )

        # =====================================================
        #            CONSTRUCCIÓN DEL PDF (ReportLab)
        # =====================================================
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        story = []


        # --- Logo empresa (opcional) ---
        # Ajusta la ruta al logo según dónde lo tengas en tu proyecto.
        # Ejemplo: /static/img/logo_intercatv.jpg
        logo_path = os.path.join(
            settings.BASE_DIR,
            "static",
            "img",
            "logo_intercatv.jpg",   # 👈 cambia el nombre si es distinto
        )

        if os.path.exists(logo_path):
            # Tamaño aprox. 3x3 cm (ajusta si lo ves muy grande/pequeño)
            logo = Image(logo_path, width=3 * cm, height=3 * cm)
            logo.hAlign = 'LEFT'
            story.append(logo)
            story.append(Spacer(1, 0.3 * cm))

        # --- Portada / título ---
        titulo = "Informe Gerencial de Órdenes"
        story.append(Paragraph(titulo, styles['Title']))
        story.append(Spacer(1, 0.4 * cm))

        subtitulo = f"Período: {desde.strftime('%d-%m-%Y')} a {hasta.strftime('%d-%m-%Y')}"
        story.append(Paragraph(subtitulo, styles['Normal']))

        # Nueva línea: fecha y hora de generación del informe
        generado = f"Generado el {timezone.now().strftime('%d-%m-%Y %H:%M')}"
        story.append(Paragraph(generado, styles['Normal']))

        story.append(Spacer(1, 0.5 * cm))

        # Texto según técnicos filtrados
        if tecnicos_ids:
            nombres = list(
                Tecnico.objects.filter(pk__in=tecnicos_ids)
                .values_list('nombre', flat=True)
            )
            if nombres:
                if len(nombres) == 1:
                    story.append(Paragraph(f"Técnico filtrado: {nombres[0]}", styles['Normal']))
                else:
                    story.append(Paragraph("Técnicos filtrados: " + ", ".join(nombres), styles['Normal']))
            else:
                story.append(Paragraph("Técnicos filtrados: (no encontrados)", styles['Normal']))

        story.append(Spacer(1, 0.5 * cm))

        # --- KPIs principales ---
        story.append(Paragraph("KPIs principales", styles['Heading2']))
        story.append(Spacer(1, 0.2 * cm))

        tabla_kpis_data = [
            ["KPI", "Valor"],
            ["Total de órdenes", str(total_periodo)],
            ["Pendientes", f"{pendientes} ({porcentaje_pendientes}%)"],
            ["En ejecución", f"{en_proceso} ({porcentaje_en_proceso}%)"],
            ["Terminadas", f"{terminadas} ({porcentaje_terminadas}%)"],
            ["Productividad técnica", f"{productividad_tecnica}%"],
            ["Tiempo prom. cierre", f"{avg_hours:.1f} h"],
            ["SLA OK", f"{sla_porcentaje}%"],
            ["Fuera de SLA", str(sla_fuera)],
        ]
        tabla_kpis = Table(tabla_kpis_data, hAlign='LEFT')
        tabla_kpis.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ]))
        story.append(tabla_kpis)
        story.append(Spacer(1, 0.5 * cm))

        # --- Gráfico: Órdenes por técnico ---
        if categorias_tecnicos:
            story.append(Paragraph("Órdenes por técnico", styles['Heading2']))
            story.append(Spacer(1, 0.2 * cm))

            drawing = Drawing(16 * cm, 8 * cm)
            bc = VerticalBarChart()
            bc.x = 1 * cm
            bc.y = 1 * cm
            bc.height = 6 * cm
            bc.width = 14 * cm
            bc.data = [valores_tecnicos]
            bc.categoryAxis.categoryNames = categorias_tecnicos
            bc.categoryAxis.labels.angle = 45
            bc.categoryAxis.labels.dy = -10
            bc.barSpacing = 0.5
            bc.valueAxis.valueMin = 0
            drawing.add(bc)
            story.append(drawing)
            story.append(Spacer(1, 0.5 * cm))

        # --- Ranking de técnicos ---
        story.append(Paragraph("Ranking de técnicos (solo órdenes terminadas)", styles['Heading2']))
        story.append(Spacer(1, 0.2 * cm))

        ranking_data = [["Técnico", "Terminadas", "% SLA OK", "T. prom. (h)"]]
        for r in ranking_tecnicos:
            ranking_data.append([
                r["nombre"],
                str(r["terminadas"]),
                f"{r['sla_porcentaje']}%",
                f"{r['tiempo_promedio_cierre_horas']:.1f}",
            ])

        tabla_ranking = Table(ranking_data, hAlign='LEFT')
        tabla_ranking.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(tabla_ranking)
        story.append(PageBreak())

        # --- Historial de órdenes cerradas ---
        story.append(Paragraph("Últimas órdenes cerradas", styles['Heading2']))
        story.append(Spacer(1, 0.2 * cm))

        historial_data = [["ID", "Técnico", "Cliente", "Fecha cierre"]] + historial
        tabla_historial = Table(
            historial_data,
            repeatRows=1,
            hAlign='LEFT',
            colWidths=[2 * cm, 5 * cm, 6 * cm, 3 * cm]
        )
        tabla_historial.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        story.append(tabla_historial)
        story.append(Spacer(1, 0.5 * cm))

        # --- Alertas operacionales ---
        story.append(Paragraph("Alertas operacionales", styles['Heading2']))
        story.append(Spacer(1, 0.2 * cm))

        if alertas:
            for a in alertas:
                story.append(Paragraph(f"• {a}", styles['Normal']))
        else:
            story.append(Paragraph("No se detectaron alertas en este período.", styles['Normal']))

        # --- Construir PDF ---
        doc.build(story)

        pdf_value = buffer.getvalue()
        buffer.close()

        filename = f"informe_dashboard_{desde.strftime('%Y%m%d')}_{hasta.strftime('%Y%m%d')}.pdf"
        response = HttpResponse(pdf_value, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ==========================================
# 3. VISTA ESPECIAL PARA LIBERAR TÉCNICOS
# ==========================================

class CambiarEstadoOrdenView(APIView):
    """
    Vista personalizada para manejar el cambio de estado desde el botón del frontend.
    Se encarga explícitamente de liberar o ocupar técnicos.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        # 1. Buscamos la orden por ID
        orden = get_object_or_404(OrdenTrabajo, pk=pk)

        # 2. Obtenemos el estado que envía el JavaScript
        nuevo_estado = request.data.get('estado')

        if not nuevo_estado:
            return Response({"error": "Falta el estado"}, status=400)

        # 3. Lógica para LIBERAR AL TÉCNICO si se termina el trabajo
        if nuevo_estado == 'TERMINADO':
            orden.estado = 'TERMINADO'

            if orden.tecnico:
                tecnico = orden.tecnico
                tecnico.disponible = True
                tecnico.save()

        # Lógica inversa: Si reactivamos una orden, ocupamos al técnico
        elif nuevo_estado in ['ASIGNADA', 'EN_CAMINO', 'EN_PROCESO']:
            orden.estado = nuevo_estado
            if orden.tecnico:
                tecnico = orden.tecnico
                tecnico.disponible = False
                tecnico.save()
        else:
            # Cualquier otro estado (ej: PENDIENTE)
            orden.estado = nuevo_estado

        orden.save()

        return Response({
            "status": "ok",
            "mensaje": f"Orden actualizada a {orden.get_estado_display()}",
            "tecnico_liberado": orden.tecnico.disponible if orden.tecnico else None
        })
