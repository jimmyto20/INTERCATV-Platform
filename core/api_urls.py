from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tecnicos.views import TecnicoViewSet, MisOrdenesView
from ordenes.views import ClienteViewSet, OrdenTrabajoViewSet
from homeApp.views import SystemStateView
from ordenes.views import ClienteViewSet, OrdenTrabajoViewSet, DashboardStatsView

# El router crea automáticamente las URLs para la API
router = DefaultRouter()
router.register(r'tecnicos', TecnicoViewSet)
router.register(r'clientes', ClienteViewSet)
router.register(r'ordenes', OrdenTrabajoViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('mis-ordenes/', MisOrdenesView.as_view(), name='mis-ordenes'),
    path('system-state/', SystemStateView.as_view(), name='system-state'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
]