from django.db import models
from django.conf import settings


class FoodItem(models.Model):
    """Alimento individual com macros."""

    name = models.CharField(max_length=200, verbose_name="Alimento")
    calories_per_100g = models.FloatField(verbose_name="Calorias/100g")
    protein_per_100g = models.FloatField(verbose_name="Proteína/100g")
    carbs_per_100g = models.FloatField(verbose_name="Carboidratos/100g")
    fat_per_100g = models.FloatField(verbose_name="Gordura/100g")
    fiber_per_100g = models.FloatField(default=0, verbose_name="Fibra/100g")
    category = models.CharField(max_length=100, blank=True, verbose_name="Categoria")

    class Meta:
        verbose_name = "Alimento"
        ordering = ["name"]

    def __str__(self):
        return self.name


class NutritionPlan(models.Model):
    """Plano alimentar completo."""

    name = models.CharField(max_length=200, verbose_name="Nome do Plano")
    description = models.TextField(blank=True)
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="nutrition_plans", limit_choices_to={"role": "coach"}
    )
    target_calories = models.PositiveIntegerField(null=True, blank=True, verbose_name="Calorias Alvo")
    target_protein = models.FloatField(null=True, blank=True, verbose_name="Proteína Alvo (g)")
    target_carbs = models.FloatField(null=True, blank=True, verbose_name="Carboidratos Alvo (g)")
    target_fat = models.FloatField(null=True, blank=True, verbose_name="Gordura Alvo (g)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plano Alimentar"
        verbose_name_plural = "Planos Alimentares"

    def __str__(self):
        return self.name


class Meal(models.Model):
    """Refeição dentro do plano (Café da manhã, Almoço, etc.)."""

    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Café da Manhã"
        MORNING_SNACK = "morning_snack", "Lanche da Manhã"
        LUNCH = "lunch", "Almoço"
        AFTERNOON_SNACK = "afternoon_snack", "Lanche da Tarde"
        DINNER = "dinner", "Jantar"
        SUPPER = "supper", "Ceia"
        PRE_WORKOUT = "pre_workout", "Pré-Treino"
        POST_WORKOUT = "post_workout", "Pós-Treino"

    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, "Segunda"
        TUESDAY = 2, "Terça"
        WEDNESDAY = 3, "Quarta"
        THURSDAY = 4, "Quinta"
        FRIDAY = 5, "Sexta"
        SATURDAY = 6, "Sábado"
        SUNDAY = 7, "Domingo"

    plan = models.ForeignKey(NutritionPlan, on_delete=models.CASCADE, related_name="meals")
    day_of_week = models.IntegerField(
        choices=DayOfWeek.choices, null=True, blank=True,
        verbose_name="Dia da Semana",
        help_text="Deixa em branco para refeições disponíveis em qualquer dia (ex: lanche livre).",
    )
    meal_type = models.CharField(max_length=20, choices=MealType.choices, verbose_name="Tipo de Refeição")
    name = models.CharField(max_length=200, blank=True, verbose_name="Nome personalizado")
    time = models.TimeField(null=True, blank=True, verbose_name="Horário sugerido")
    order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Refeição"
        verbose_name_plural = "Refeições"
        ordering = ["day_of_week", "order"]

    def __str__(self):
        return f"{self.get_meal_type_display()} - {self.plan.name}"

    @property
    def total_calories(self):
        return sum(float(item.calories or 0) for item in self.items.all())


class MealItem(models.Model):
    """Item dentro de uma refeição (alimento + quantidade)."""

    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="items")
    food = models.ForeignKey(FoodItem, on_delete=models.CASCADE)
    quantity_grams = models.FloatField(verbose_name="Quantidade (g)")
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Item da Refeição"

    @property
    def calories(self):
        try:
            return (float(self.food.calories_per_100g) * float(self.quantity_grams)) / 100
        except (TypeError, ValueError):
            return 0

    @property
    def protein(self):
        return (self.food.protein_per_100g * self.quantity_grams) / 100

    def __str__(self):
        return f"{self.food.name} ({self.quantity_grams}g)"


class NutritionLog(models.Model):
    """Registro diário de alimentação do cliente."""

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nutrition_logs")
    date = models.DateField()
    meal = models.ForeignKey(Meal, on_delete=models.SET_NULL, null=True, blank=True)
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Registro Alimentar"
        unique_together = ["client", "date", "meal"]