from django.db import models
from django.utils import timezone
from django.conf import settings
from apps.workouts.models import *
from apps.nutrition.models import *


class CoachingPackage(models.Model):
    """Pacote de coaching (agrega treino + nutrição)."""

    name = models.CharField(max_length=200, verbose_name="Nome do Pacote")
    description = models.TextField(blank=True)
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="packages", limit_choices_to={"role": "coach"}
    )
    workout_plan = models.ForeignKey(
        WorkoutPlan, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Plano de Treino"
    )
    nutrition_plan = models.ForeignKey(
        NutritionPlan, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Plano Alimentar"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Preço")
    duration_days = models.PositiveIntegerField(default=30, verbose_name="Duração (dias)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pacote de Coaching"
        verbose_name_plural = "Pacotes de Coaching"
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class ClientPackage(models.Model):
    """Atribuição de pacote a um cliente (com datas)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        PAUSED = "paused", "Pausado"
        COMPLETED = "completed", "Concluído"
        CANCELLED = "cancelled", "Cancelado"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="client_packages", limit_choices_to={"role": "client"}
    )
    package = models.ForeignKey(CoachingPackage, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField()
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="assigned_packages", limit_choices_to={"role": "coach"}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        return self.end_date < timezone.now().date()

    def expire_if_needed(self):
        """Marca como 'completed' se a data já passou."""
        if self.status == 'active' and self.is_expired:
            self.status = 'completed'
            self.save(update_fields=['status'])
            return True
        return False

    class Meta:
        verbose_name = "Pacote do Cliente"

    def __str__(self):
        return f"{self.client} - {self.package.name} ({self.get_status_display()})"
