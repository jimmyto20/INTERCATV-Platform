from django.contrib import admin
from .models import Cliente, OrdenTrabajo

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'direccion')
    search_fields = ('nombre', 'telefono')

@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'tecnico', 'prioridad', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'prioridad', 'fecha_creacion')
    search_fields = ('cliente__nombre', 'descripcion')
    list_editable = ('estado', 'tecnico') # ¡Para asignar rápido desde la lista!