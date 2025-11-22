from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from UsuarioApp.models import Profile
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from ordenes.models import SystemState



# Create your views here.


class HomeView(LoginRequiredMixin, ListView):
    model = User
    template_name = "pages/index.html"

    def get_queryset(self):
        last_connected_users = User.objects.filter(
            Q(last_login__isnull=False)
        ).order_by("-last_login")[:5]
        return last_connected_users

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Agrega los usuarios activos al contexto
        recent_activity_cutoff = timezone.now() - timezone.timedelta(minutes=2)
        active_users = Profile.objects.filter(
            last_activity__gte=recent_activity_cutoff
        ).values_list("user_FK_id", flat=True)
        context["active_users"] = active_users
        return context

@login_required
def gestor_ordenes_view(request):
    # Por ahora, solo mostramos la plantilla.
    # La plantilla se encargará de llamar a la API para obtener los datos.
    context = {} 
    return render(request, "pages/gestor_ordenes.html", context)
@login_required
def portal_tecnico_view(request):
    """
    Muestra el portal simple (simulador de celular) para que los técnicos
    vean y actualicen sus propias órdenes de trabajo.
    """
    # Esta vista solo carga el HTML. 
    # El JavaScript dentro del HTML se encargará de llamar a la API '/api/v1/mis-ordenes/'
    context = {} 
    return render(request, "pages/portal_tecnico.html", context)


class SystemStateView(APIView):
    """
    API para consultar y activar/desactivar el Modo Emergencia.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        state = SystemState.get_state()
        return Response({
            'is_emergency': state.is_emergency,
            'message': state.emergency_message
        })

    def post(self, request, *args, **kwargs):
        if not request.user.is_staff: # Solo Admins pueden cambiar el estado
            return Response({"error": "No tienes permiso."}, status=403)

        state = SystemState.get_state()
        state.is_emergency = not state.is_emergency # Alternar

        if state.is_emergency:
            state.emergency_message = request.data.get(
                'message', 
                "Estamos experimentando una falla masiva."
            )
        state.save()

        return Response({
            'is_emergency': state.is_emergency,
            'message': state.emergency_message
        })