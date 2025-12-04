from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from .models import Profile, Position
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


# --- FORMULARIOS DE USUARIO ---

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
        ]

class UserCreateForm(UserCreationForm, UserUpdateForm):
    password1 = forms.PasswordInput()
    password2 = forms.PasswordInput()

    # NUEVO CAMPO: Selector de Rol (Grupo de Django)
    grupo = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        label="Rol de Sistema (Permisos)",
        required=True,
        empty_label="Seleccione un Rol...",
        widget=forms.Select(attrs={
            'class': 'bg-white border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 mb-3'
        })
    )

    class Meta:
        model = User
        # Agregamos 'grupo' al principio para que se renderice
        fields = ["grupo"] + UserUpdateForm.Meta.fields + ["password1", "password2"]

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        validate_password(password1)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("Las contraseñas no coinciden")

        return cleaned_data


# NUEVO: Formulario para EDITAR usuarios (sin pedir password obligatoriamente)
class UserEditAdminForm(forms.ModelForm):
    grupo = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        label="Rol de Sistema",
        required=True,
        widget=forms.Select(attrs={
            'class': 'bg-white border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg block w-full p-2.5'}),
            'email': forms.EmailInput(attrs={'class': 'bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg block w-full p-2.5'}),
            'first_name': forms.TextInput(attrs={'class': 'bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg block w-full p-2.5'}),
            'last_name': forms.TextInput(attrs={'class': 'bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg block w-full p-2.5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500'}),
        }


# --- FORMULARIOS DE PERFIL ---

class ProfileUpdateForm(forms.ModelForm):
    image = forms.ImageField(
        label="Imagen",
        widget=forms.FileInput(attrs={"class": "hidden", "id": "id_image"}),
        required=False,
    )

    class Meta:
        model = Profile
        fields = ["image"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "El tamaño del archivo de imagen no debe exceder los 5 MB."
            )
        return image


class ProfileCreateForm(ProfileUpdateForm):
    position_FK = forms.ModelChoiceField(
        label="Cargo Laboral",
        queryset=Position.objects.exclude(pk=1), # Excluir admin si es necesario
        widget=forms.Select(
            attrs={
                "class": "bg-white border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 mb-3"
            }
        ),
    )

    class Meta(ProfileUpdateForm.Meta):
        fields = ProfileUpdateForm.Meta.fields + ["position_FK"]