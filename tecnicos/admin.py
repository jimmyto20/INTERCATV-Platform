from django.contrib import admin
from .models import Tecnico

@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rut', 'especialidad', 'disponible', 'telefono')
    list_filter = ('disponible', 'especialidad')
    search_fields = ('nombre', 'rut')