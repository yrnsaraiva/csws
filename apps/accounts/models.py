from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user com role de coach ou cliente."""

    class Role(models.TextChoices):
        COACH = "coach", "Coach"
        CLIENT = "client", "Cliente"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CLIENT)
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Relação coach ↔ clientes
    coach = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
        limit_choices_to={"role": Role.COACH},
    )

    @property
    def is_coach(self):
        return self.role == self.Role.COACH

    @property
    def is_client(self):
        return self.role == self.Role.CLIENT

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


class ClientProfile(models.Model):
    """Dados adicionais do cliente (medidas, objetivos)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_profile")
    height_cm = models.FloatField(null=True, blank=True, verbose_name="Altura (cm)")
    weight_kg = models.FloatField(null=True, blank=True, verbose_name="Peso (kg)")
    goal = models.CharField(max_length=200, blank=True, verbose_name="Objetivo")
    notes = models.TextField(blank=True, verbose_name="Observações")

    def __str__(self):
        return f"Perfil de {self.user.get_full_name()}"
