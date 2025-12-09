from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q
from allauth.account.models import EmailAddress
from django.contrib import messages
from core.mixins import PermitsPositionMixin
from django.http import JsonResponse
from django.utils import timezone
import json

# --- IMPORTACIONES DE MODELOS ---
from .models import Profile
from ordenes.models import OrdenTrabajo 
from tecnicos.models import Tecnico  

# --- IMPORTACIONES DE FORMULARIOS ---
from .forms import (
    UserCreateForm, ProfileCreateForm, UserUpdateForm, 
    ProfileUpdateForm, UserEditAdminForm
)

# ==============================================================================
# 1. GESTIÓN DE USUARIOS: LISTA
# ==============================================================================
class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = "pages/usuarios/usuarios_lista.html"
    context_object_name = "users"
    paginate_by = 9

    def get_queryset(self):
        queryset = super().get_queryset().select_related('profile').order_by("-id")
        search_query = self.request.GET.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) | 
                Q(first_name__icontains=search_query) | 
                Q(last_name__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        verification_users = []
        for user in context["users"]:
            # Auto-reparación si falta perfil
            if not hasattr(user, 'profile'):
                Profile.objects.create(user_FK=user)
                user.refresh_from_db()
            
            verification = EmailAddress.objects.filter(user=user, verified=True).exists()
            verification_users.append((user, verification))
        
        context["verification_users"] = verification_users
        context["placeholder"] = "Buscar por usuario..."
        context["search_query"] = self.request.GET.get("search", "")
        return context

# ==============================================================================
# 2. GESTIÓN DE USUARIOS: CREAR
# ==============================================================================
class UserCreateView(LoginRequiredMixin, PermitsPositionMixin, View):
    template_name = "pages/usuarios/registro_usuario.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {
            "user_form": UserCreateForm(), 
            "profile_form": ProfileCreateForm()
        })

    def post(self, request, *args, **kwargs):
        user_form = UserCreateForm(request.POST)
        profile_form = ProfileCreateForm(request.POST, request.FILES)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            grupo = user_form.cleaned_data.get('grupo')
            
            if grupo:
                user.groups.add(grupo)
                if grupo.name == 'GERENCIA':
                    user.is_staff = True
                    user.save()

            profile = profile_form.save(commit=False)
            profile.user_FK = user
            profile.save()
            
            messages.success(request, f"Usuario {user.username} creado correctamente.")
            return redirect("Register")

        return render(request, self.template_name, {
            "user_form": user_form, 
            "profile_form": profile_form
        })

# ==============================================================================
# 3. GESTIÓN DE USUARIOS: EDITAR
# ==============================================================================
class UserEditView(LoginRequiredMixin, PermitsPositionMixin, View):
    template_name = "pages/usuarios/editar_usuario.html"

    def get(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        
        # Auto-reparación
        if not hasattr(user, 'profile'):
            Profile.objects.create(user_FK=user)
            user.refresh_from_db()
        
        initial = {}
        if user.groups.exists():
            initial['grupo'] = user.groups.first()

        return render(request, self.template_name, {
            "user_form": UserEditAdminForm(instance=user, initial=initial),
            "profile_form": ProfileCreateForm(instance=user.profile),
            "user_editar": user
        })

    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        
        if not hasattr(user, 'profile'):
            Profile.objects.create(user_FK=user)
            user.refresh_from_db()

        user_form = UserEditAdminForm(request.POST, instance=user)
        profile_form = ProfileCreateForm(request.POST, request.FILES, instance=user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile_form.save()

            nuevo_grupo = user_form.cleaned_data.get('grupo')
            if nuevo_grupo:
                user.groups.clear()
                user.groups.add(nuevo_grupo)
                user.is_staff = (nuevo_grupo.name == 'GERENCIA')
                user.save()

            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("User")

        return render(request, self.template_name, {
            "user_form": user_form, 
            "profile_form": profile_form, 
            "user_editar": user
        })

# ==============================================================================
# 4. GESTIÓN DE USUARIOS: ELIMINAR
# ==============================================================================
class UserDeleteView(LoginRequiredMixin, PermitsPositionMixin, View):
    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, "No puedes eliminar tu propia cuenta.")
        else:
            try:
                user.delete()
                messages.success(request, "Usuario eliminado.")
            except Exception:
                messages.error(request, "Error al eliminar.")
        return redirect("User")

# ==============================================================================
# 5. PERFIL PROPIO
# ==============================================================================
class ProfileUpdateView(LoginRequiredMixin, View):
    template_name = "pages/perfil/perfil.html"

    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'profile'): 
             Profile.objects.create(user_FK=request.user)
             request.user.refresh_from_db()
             
        return render(request, self.template_name, {
            "user_form": UserUpdateForm(instance=request.user), 
            "profile_form": ProfileUpdateForm(instance=request.user.profile)
        })

    def post(self, request, *args, **kwargs):
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Perfil actualizado.")
            return redirect("Profile")
            
        return render(request, self.template_name, {
            "user_form": user_form, 
            "profile_form": profile_form
        })

# ==============================================================================
# 6. PORTAL TÉCNICO (VISUALIZACIÓN DE ÓRDENES)
# ==============================================================================
class PortalTecnicoView(LoginRequiredMixin, View):
    template_name = "pages/portal_tecnico.html" 

    def get(self, request, *args, **kwargs):
        # 1. Buscamos el objeto 'Tecnico' asociado al usuario logueado
        # CORRECCIÓN: Usamos 'user' (campo del modelo Tecnico) en lugar de 'user_FK'
        try:
            tecnico_actual = Tecnico.objects.get(user=request.user)
        except Tecnico.DoesNotExist:
            return render(request, self.template_name, {'ordenes': [], 'error_tecnico': True})

        # 2. Filtramos las órdenes
        # CORRECCIÓN: Usamos 'cliente' (campo del modelo OrdenTrabajo) en select_related
        ordenes = OrdenTrabajo.objects.filter(
            tecnico=tecnico_actual
        ).exclude(
            estado='TERMINADA'
        ).select_related('cliente').order_by('-prioridad', '-id')
        
        context = {
            'ordenes': ordenes
        }
        return render(request, self.template_name, context)


# ==============================================================================
# 7. API PARA CAMBIAR ESTADO (PARA LOS BOTONES DEL PORTAL)
# ==============================================================================
def cambiar_estado_orden(request, pk):
    """
    Recibe una petición POST (fetch) para actualizar el estado de una orden.
    """
    if request.method == 'POST':
        try:
            # Parseamos el body JSON
            data = json.loads(request.body)
            nuevo_estado = data.get('estado')
            
            # Verificamos que la orden exista y pertenezca al técnico logueado
            # Usamos 'tecnico__user' para la relación inversa desde Orden -> Tecnico -> User
            orden = get_object_or_404(OrdenTrabajo, pk=pk, tecnico__user=request.user)
            
            # Validamos estados permitidos
            if nuevo_estado in ['EN_CAMINO', 'EN_PROCESO', 'TERMINADA']:
                orden.estado = nuevo_estado
                
                # Si se termina, guardamos la fecha de cierre
                if nuevo_estado == 'TERMINADA':
                    orden.fecha_cierre = timezone.now()
                    
                    # Opcional: Liberar al técnico (poner disponible=True)
                    # tecnico = orden.tecnico
                    # tecnico.disponible = True
                    # tecnico.save()

                orden.save()
                return JsonResponse({'status': 'ok', 'mensaje': f'Estado actualizado a {nuevo_estado}'})
            else:
                return JsonResponse({'status': 'error', 'mensaje': 'Estado inválido'}, status=400)

        except OrdenTrabajo.DoesNotExist:
            return JsonResponse({'status': 'error', 'mensaje': 'Orden no encontrada o no autorizada'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'mensaje': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'}, status=405)