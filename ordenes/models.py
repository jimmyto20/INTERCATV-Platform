from django.db import models
from tecnicos.models import Tecnico # Importamos el modelo Técnico para relacionarlo

class Cliente(models.Model):
    nombre = models.CharField(max_length=200, verbose_name="Nombre Cliente")
    direccion = models.CharField(max_length=255, verbose_name="Dirección física")
    telefono = models.CharField(max_length=20, verbose_name="Teléfono/WhatsApp")
    correo = models.EmailField(blank=True, null=True, verbose_name="Correo electrónico (opcional)")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de registro")
    chat_state = models.CharField(max_length=50, default='START', null=True, blank=True, verbose_name="Estado del Chat")
    temp_data = models.JSONField(default=dict, null=True, blank=True, verbose_name="Datos Temporales del Chat")

    def __str__(self):
        return f"{self.nombre} - {self.telefono}"

class OrdenTrabajo(models.Model):
    # Definimos las opciones estandarizadas según tu tesis
    PRIORIDAD_CHOICES = [
        ('ALTA', 'Alta'),
        ('MEDIA', 'Media'),
        ('BAJA', 'Baja'),
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Asignación'),
        ('ASIGNADA', 'Asignada a Técnico'),
        ('EN_CAMINO', 'Técnico en Camino'),
        ('EN_PROCESO', 'En Proceso'),
        ('TERMINADO', 'Trabajo Terminado'),
        ('CERRADA', 'Cerrada por Administración'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='ordenes')
    tecnico = models.ForeignKey(Tecnico, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordenes_asignadas', verbose_name="Técnico asignado")
    
    descripcion = models.TextField(verbose_name="Detalle de la falla o servicio")
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default='MEDIA')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    
    ubicacion_servicio = models.CharField(max_length=100, help_text="Coordenadas lat,long del servicio", verbose_name="Ubicación del Servicio")
    
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Última actualización")
    
    evidencia_url = models.URLField(blank=True, null=True, verbose_name="Link a evidencia (foto/doc)")
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones finales")

    def __str__(self):
        return f"OT #{self.id} - {self.cliente.nombre} ({self.estado})"

    class Meta:
        verbose_name = "Orden de Trabajo"
        verbose_name_plural = "Órdenes de Trabajo"
        ordering = ['-fecha_creacion'] # Las más nuevas primero

class SystemState(models.Model):
    """
    Un modelo Singleton (siempre ID=1) para guardar el estado global del sistema.
    """
    is_emergency = models.BooleanField(default=False, verbose_name="¿Modo Emergencia Activado?")
    emergency_message = models.TextField(
        blank=True, 
        null=True, 
        default="Estamos experimentando una falla masiva en el sector. Nuestros técnicos ya están informados y trabajando para solucionarlo. Agradecemos su paciencia.",
        verbose_name="Mensaje de Emergencia"
    )

    def save(self, *args, **kwargs):
        # Nos aseguramos de que solo exista 1 objeto
        self.pk = 1
        super(SystemState, self).save(*args, **kwargs)

    @classmethod
    def get_state(cls):
        # Un método fácil para obtener el estado actual
        obj, created = cls.objects.get_or_create(pk=1)
        return obj