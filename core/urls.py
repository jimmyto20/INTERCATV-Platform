from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from whatsapp_webhook.views import twilio_webhook
from UsuarioApp import views
# Puedes quitar 'cambiar_estado_orden' de aquí si ya no la usas en otro lado
from UsuarioApp.views import PortalTecnicoView 
from ordenes.views import CambiarEstadoOrdenView


urlpatterns = [
    path("admin/", admin.site.urls),
    
    # Agregamos esta línea nueva para tu API:
    path("api/v1/", include("core.api_urls")), 
    
    path('usuarios/', views.UserListView.as_view(), name='User'),
    path('registro/', views.UserCreateView.as_view(), name='Register'),
    path('portal-tecnico/', PortalTecnicoView.as_view(), name='portal_tecnico'),
    
    # --- CORRECCIÓN CRÍTICA AQUÍ ---
    # He eliminado la línea antigua: path('orden/<int:pk>/cambiar-estado/', cambiar_estado_orden...)
    # Ahora SOLO existe esta ruta, que apunta a tu nueva vista con la lógica de liberar técnicos:
    path('orden/<int:pk>/cambiar-estado/', CambiarEstadoOrdenView.as_view(), name='cambiar-estado-orden'),
    
    # Tus rutas existentes siguen igual:
    path("accounts/", include("allauth.urls")),
    path("", include("homeApp.urls")),
    path("", include("UsuarioApp.urls")),
    path("webhook/twilio/", twilio_webhook, name="twilio_webhook"),
    path('usuarios/editar/<int:pk>/', views.UserEditView.as_view(), name='user_edit'),
    path('usuarios/eliminar/<int:pk>/', views.UserDeleteView.as_view(), name='user_delete'),


    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)