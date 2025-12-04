from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q
from allauth.account.models import EmailAddress
from django.contrib import messages
from core.mixins import PermitsPositionMixin

# Importamos el modelo Profile para la corrección de usuarios antiguos
from .models import Profile

# Importamos los formularios actualizados
from .forms import (
    UserCreateForm, 
    ProfileCreateForm, 
    UserUpdateForm, 
    ProfileUpdateForm,
    UserEditAdminForm  # Nuevo form de edición
)

# ==============================================================================
# 1. LISTA DE USUARIOS (PANEL DE GESTIÓN)
# ==============================================================================
class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = "pages/usuarios/usuarios_lista.html"
    context_object_name = "users"
    paginate_by = 9

    def get_queryset(self):
        # Optimizamos la consulta trayendo el perfil de una vez (select_related)
        # para evitar múltiples consultas a la base de datos
        queryset = super().get_queryset().select_related('profile').order_by("-id")
        search_query = self.request.GET.get("search")

        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        verification_users = []
        
        for user in context["users"]:
            # Verificamos si existe el correo verificado en Allauth
            verification = EmailAddress.objects.filter(
                user=user, verified=True
            ).exists()
            
            # --- CORRECCIÓN DE EMERGENCIA EN LISTA ---
            # Si un usuario se lista pero no tiene perfil, evitamos que rompa el template
            if not hasattr(user, 'profile'):
                Profile.objects.create(user_FK=user)
                user.refresh_from_db()
            # -----------------------------------------

            verification_users.append((user, verification))

        context["verification_users"] = verification_users
        context["placeholder"] = "Buscar por usuario, nombre o apellido..."
        context["search_query"] = self.request.GET.get("search", "")
        return context


# ==============================================================================
# 2. CREAR USUARIO (CON GRUPO Y PERFIL)
# ==============================================================================
class UserCreateView(LoginRequiredMixin, PermitsPositionMixin, View):
    template_name = "pages/usuarios/registro_usuario.html"

    def get(self, request, *args, **kwargs):
        user_form = UserCreateForm()
        profile_form = ProfileCreateForm()

        context = {"user_form": user_form, "profile_form": profile_form}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        user_form = UserCreateForm(request.POST)
        profile_form = ProfileCreateForm(request.POST, request.FILES)

        if user_form.is_valid() and profile_form.is_valid():
            # a) Guardar Usuario base
            user = user_form.save()
            
            # b) Asignar Grupo (Rol)
            grupo = user_form.cleaned_data.get('grupo')
            if grupo:
                user.groups.add(grupo)
                # Si es Gerencia, damos permisos de Staff para entrar al Admin Django si fuera necesario
                if grupo.name == 'GERENCIA':
                    user.is_staff = True
                    user.save()

            # c) Guardar Perfil
            profile = profile_form.save(commit=False)
            profile.user_FK = user
            profile.save()
            
            messages.success(request, f"Usuario {user.username} creado correctamente con rol {grupo.name}.")
            return redirect("Register")

        context = {"user_form": user_form, "profile_form": profile_form}
        return render(request, self.template_name, context)


# ==============================================================================
# 3. EDITAR USUARIO (VISTA ADMINISTRATIVA)
# ==============================================================================
class UserEditView(LoginRequiredMixin, PermitsPositionMixin, View):
    template_name = "pages/usuarios/editar_usuario.html"

    def get(self, request, pk, *args, **kwargs):
        user_editar = get_object_or_404(User, pk=pk)
        
        # --- CORRECCIÓN DE ERROR: Crear perfil si no existe ---
        # Esto soluciona el crash con usuarios antiguos
        if not hasattr(user_editar, 'profile'):
            Profile.objects.create(user_FK=user_editar)
            user_editar.refresh_from_db()
        # ------------------------------------------------------
        
        # Pre-cargar el grupo actual en el selector
        initial_data = {}
        grupo_actual = user_editar.groups.first()
        if grupo_actual:
            initial_data['grupo'] = grupo_actual

        user_form = UserEditAdminForm(instance=user_editar, initial=initial_data)
        profile_form = ProfileCreateForm(instance=user_editar.profile)

        context = {
            "user_form": user_form, 
            "profile_form": profile_form,
            "user_editar": user_editar
        }
        return render(request, self.template_name, context)

    def post(self, request, pk, *args, **kwargs):
        user_editar = get_object_or_404(User, pk=pk)

        # --- CORRECCIÓN DE ERROR: Crear perfil si no existe (por seguridad en POST) ---
        if not hasattr(user_editar, 'profile'):
            Profile.objects.create(user_FK=user_editar)
            user_editar.refresh_from_db()
        # ------------------------------------------------------------------------------

        user_form = UserEditAdminForm(request.POST, instance=user_editar)
        profile_form = ProfileCreateForm(request.POST, request.FILES, instance=user_editar.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile_form.save()

            # Actualizar Grupo
            nuevo_grupo = user_form.cleaned_data.get('grupo')
            if nuevo_grupo:
                user.groups.clear() # Quitamos roles anteriores
                user.groups.add(nuevo_grupo)
                
                # Ajustar is_staff según el nuevo rol
                if nuevo_grupo.name == 'GERENCIA':
                    user.is_staff = True
                else:
                    user.is_staff = False
                user.save()

            messages.success(request, f"Usuario {user.username} actualizado correctamente.")
            return redirect("User")

        context = {"user_form": user_form, "profile_form": profile_form, "user_editar": user_editar}
        return render(request, self.template_name, context)


# ==============================================================================
# 4. ELIMINAR USUARIO
# ==============================================================================
class UserDeleteView(LoginRequiredMixin, PermitsPositionMixin, View):
    def post(self, request, pk, *args, **kwargs):
        user_eliminar = get_object_or_404(User, pk=pk)
        
        # Seguridad: Evitar que uno se elimine a sí mismo
        if user_eliminar == request.user:
            messages.error(request, "No puedes eliminar tu propia cuenta.")
            return redirect("User")
            
        try:
            nombre = user_eliminar.username
            user_eliminar.delete()
            messages.success(request, f"Usuario {nombre} eliminado correctamente.")
        except Exception as e:
            messages.error(request, "Error al eliminar usuario.")
            
        return redirect("User")


# ==============================================================================
# 5. ACTUALIZAR MI PERFIL (Para el usuario logueado)
# ==============================================================================
class ProfileUpdateView(LoginRequiredMixin, View):
    template_name = "pages/perfil/perfil.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        # Seguridad extra por si el propio usuario logueado no tiene perfil (raro, pero posible)
        if not hasattr(user, 'profile'):
             Profile.objects.create(user_FK=user)
             user.refresh_from_db()

        profile = user.profile
        user_form = UserUpdateForm(instance=user)
        profile_form = ProfileUpdateForm(instance=profile)

        context = {"user_form": user_form, "profile_form": profile_form}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        user = request.user
        profile = user.profile
        user_form = UserUpdateForm(request.POST, instance=user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            try:
                user_form.save()
                profile_form.save()
                messages.success(request, "Perfil actualizado con éxito.")
            except Exception as e:
                messages.error(request, "Error al guardar la imagen")

            return redirect("Profile")

        context = {"user_form": user_form, "profile_form": profile_form}
        return render(request, self.template_name, context)