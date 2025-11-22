from django.db import models
from django.contrib.auth.models import User

class Tecnico(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_tecnico', null=True, blank=True, verbose_name="Usuario (Login)")
    nombre = models.CharField(max_length=200, verbose_name="Nombre completo")
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    telefono = models.CharField(max_length=20, verbose_name="Teléfono de contacto")
    especialidad = models.CharField(max_length=100, verbose_name="Especialidad")
    disponible = models.BooleanField(default=True, verbose_name="¿Está disponible?")
    # Guardaremos la ubicación como "latitud,longitud" en texto por ahora para simplificar
    ubicacion_actual = models.CharField(max_length=100, blank=True, null=True, verbose_name="Ubicación GPS actual")

    def __str__(self):
        return f"{self.nombre} ({self.especialidad})"

    class Meta:
        verbose_name = "Técnico"
        verbose_name_plural = "Técnicos"

