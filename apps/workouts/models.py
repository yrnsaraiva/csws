from django.db import models
from django.conf import settings


class MuscleGroup(models.Model):
    """Grupo muscular (Peito, Costas, Pernas, etc.)."""

    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Nome do ícone (ex: 'bicep')")

    class Meta:
        verbose_name = "Grupo Muscular"
        verbose_name_plural = "Grupos Musculares"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Exercise(models.Model):
    """Exercício com vídeo demonstrativo."""

    name = models.CharField(max_length=200, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")
    muscle_groups = models.ManyToManyField(MuscleGroup, related_name="exercises", verbose_name="Grupos Musculares")
    video = models.FileField(upload_to="exercise_videos/", blank=True, null=True, verbose_name="Vídeo")
    video_url = models.URLField(blank=True, help_text="URL do vídeo (YouTube/Vimeo)", verbose_name="URL do Vídeo")
    thumbnail = models.ImageField(upload_to="exercise_thumbnails/", blank=True, null=True)
    instructions = models.TextField(blank=True, verbose_name="Instruções de Execução")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={"role": "coach"}, verbose_name="Criado por"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Exercício"
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkoutPlan(models.Model):
    """Plano de treino (ex: 'Plano Hipertrofia 12 semanas')."""

    name = models.CharField(max_length=200, verbose_name="Nome do Plano")
    description = models.TextField(blank=True)
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="workout_plans", limit_choices_to={"role": "coach"}
    )
    duration_weeks = models.PositiveIntegerField(default=4, verbose_name="Duração (semanas)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plano de Treino"
        verbose_name_plural = "Planos de Treino"

    def __str__(self):
        return self.name


class WorkoutDay(models.Model):
    """Dia de treino dentro de um plano (ex: 'Dia A - Peito/Tríceps')."""

    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, "Segunda"
        TUESDAY = 2, "Terça"
        WEDNESDAY = 3, "Quarta"
        THURSDAY = 4, "Quinta"
        FRIDAY = 5, "Sexta"
        SATURDAY = 6, "Sábado"
        SUNDAY = 7, "Domingo"

    plan = models.ForeignKey(WorkoutPlan, on_delete=models.CASCADE, related_name="days")
    name = models.CharField(max_length=100, verbose_name="Nome (ex: Treino A)")
    day_of_week = models.IntegerField(choices=DayOfWeek.choices, verbose_name="Dia da Semana")
    order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Dia de Treino"
        ordering = ["order", "day_of_week"]

    def __str__(self):
        return f"{self.plan.name} - {self.name}"


class WorkoutExercise(models.Model):
    """Exercício dentro de um dia de treino, com séries/reps."""

    class ExerciseType(models.TextChoices):
        NORMAL = "normal", "Normal"
        SUPERSET = "superset", "Superset"
        DROPSET = "dropset", "Drop Set"
        GIANT_SET = "giant_set", "Giant Set"

    workout_day = models.ForeignKey(WorkoutDay, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    sets = models.PositiveIntegerField(default=3, verbose_name="Séries")
    reps = models.CharField(max_length=50, default="12", verbose_name="Repetições", help_text="Ex: 12, 8-12, até falha")
    rest_seconds = models.PositiveIntegerField(default=60, verbose_name="Descanso (seg)")
    tempo = models.CharField(max_length=20, blank=True, help_text="Ex: 3-1-2-0")
    exercise_type = models.CharField(max_length=20, choices=ExerciseType.choices, default=ExerciseType.NORMAL)
    superset_group = models.PositiveIntegerField(null=True, blank=True, help_text="Agrupar exercícios do mesmo superset")
    notes = models.TextField(blank=True, verbose_name="Observações")

    class Meta:
        verbose_name = "Exercício do Treino"
        ordering = ["order"]

    def __str__(self):
        return f"{self.exercise.name} - {self.sets}x{self.reps}"


class WorkoutLog(models.Model):
    """Registro de execução de treino pelo cliente."""

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_logs")
    workout_day = models.ForeignKey(WorkoutDay, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Registro de Treino"

    def __str__(self):
        return f"{self.client} - {self.workout_day} ({self.date})"


class ExerciseLog(models.Model):
    """Log de cada exercício executado (peso, reps reais)."""

    workout_log = models.ForeignKey(WorkoutLog, on_delete=models.CASCADE, related_name="exercise_logs")
    workout_exercise = models.ForeignKey(WorkoutExercise, on_delete=models.CASCADE)
    set_number = models.PositiveIntegerField(verbose_name="Série #")
    weight_kg = models.FloatField(null=True, blank=True, verbose_name="Peso (kg)")
    reps_done = models.PositiveIntegerField(null=True, blank=True, verbose_name="Reps realizadas")
    completed = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Log de Exercício"
        ordering = ["set_number"]