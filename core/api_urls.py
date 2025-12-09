from django.urls import path, include
from rest_framework.routers import DefaultRouter

from tecnicos.views import TecnicoViewSet, MisOrdenesView
from ordenes.views import ClienteViewSet, OrdenTrabajoViewSet, DashboardStatsView, DashboardHistorialCSVView, DashboardPDFView
from homeApp.views import SystemStateView












# El router crea automáticamente las URLs para la API (CRUDs)
router = DefaultRouter()
router.register(r"tecnicos", TecnicoViewSet, basename="tecnicos")
router.register(r"clientes", ClienteViewSet, basename="clientes")
router.register(r"ordenes", OrdenTrabajoViewSet, basename="ordenes")

urlpatterns = [
    # --- RUTAS MANUALES (van ANTES del router) ---

    # Endpoint del dashboard gerencial
    # URL final: /api/v1/dashboard-stats/
    path("dashboard-stats/", DashboardStatsView.as_view(), name="dashboard-stats"),

    # Endpoint para que un técnico vea sus propias órdenes
    # URL final: /api/v1/mis-ordenes/
    path("mis-ordenes/", MisOrdenesView.as_view(), name="mis-ordenes"),

    # Endpoint para consultar / cambiar modo de emergencia
    # URL final: /api/v1/system-state/
    path("system-state/", SystemStateView.as_view(), name="system-state"),

    # NUEVO: exportar historial a CSV
    path("dashboard-historial.csv", DashboardHistorialCSVView.as_view(), name="dashboard-historial-csv"),

    # 👇 NUEVO: Informe PDF completo
    path("dashboard-informe.pdf", DashboardPDFView.as_view(), name="dashboard-informe-pdf"),

    # --- RUTAS AUTOMÁTICAS DRF (al final) ---
    path("", include(router.urls)),
]
