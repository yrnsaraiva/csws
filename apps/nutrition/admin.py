from django.contrib import admin
from django.utils.html import format_html
from .models import FoodItem, NutritionPlan, Meal, MealItem, NutritionLog

from unfold.admin import ModelAdmin, TabularInline


# ── Inlines ──────────────────────────────────────────

class MealItemInline(TabularInline):
    """Itens dentro de uma refeição."""
    model = MealItem
    extra = 1
    autocomplete_fields = ["food"]
    fields = ["food", "quantity_grams", "notes", "calculated_macros"]
    readonly_fields = ["calculated_macros"]

    def calculated_macros(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<span style="color:#60a5fa;">P {:.1f}g</span> · '
            '<span style="color:#fbbf24;">C {:.1f}g</span> · '
            '<span style="color:#f87171;">G {:.1f}g</span> · '
            '<strong>{:.0f} kcal</strong>',
            obj.protein,
            (obj.food.carbs_per_100g * obj.quantity_grams) / 100,
            (obj.food.fat_per_100g * obj.quantity_grams) / 100,
            obj.calories,
        )
    calculated_macros.short_description = "Macros"


class MealInline(TabularInline):
    """Refeições dentro de um plano alimentar."""
    model = Meal
    extra = 0
    show_change_link = True
    fields = ["order", "meal_type", "name", "time", "notes"]
    ordering = ["order"]


# ── ModelAdmins ──────────────────────────────────────

@admin.register(FoodItem)
class FoodItemAdmin(ModelAdmin):
    list_display = [
        "name", "category", "calories_per_100g",
        "protein_per_100g", "carbs_per_100g", "fat_per_100g",
    ]
    list_filter = ["category"]
    search_fields = ["name", "category"]
    list_editable = ["calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("name", "category")}),
        ("Macros por 100g", {"fields": (
            "calories_per_100g", "protein_per_100g",
            "carbs_per_100g", "fat_per_100g", "fiber_per_100g",
        )}),
    )

    # --- Ações ---
    @admin.action(description="Duplicar alimento(s)")
    def duplicate_food(self, request, queryset):
        for food in queryset:
            food.pk = None
            food.name = f"{food.name} (cópia)"
            food.save()
        self.message_user(request, f"{queryset.count()} alimento(s) duplicado(s).")

    actions = ["duplicate_food"]


@admin.register(NutritionPlan)
class NutritionPlanAdmin(ModelAdmin):
    list_display = [
        "name", "coach", "target_calories",
        "meals_count", "is_active", "created_at",
    ]
    list_filter = ["is_active", "coach"]
    search_fields = ["name", "description"]
    list_editable = ["is_active"]
    inlines = [MealInline]
    readonly_fields = ["created_at", "updated_at", "plan_summary"]

    fieldsets = (
        (None, {"fields": ("name", "description", "coach")}),
        ("Metas Diárias", {"fields": (
            "target_calories", "target_protein",
            "target_carbs", "target_fat",
        )}),
        ("Estado", {"fields": ("is_active",)}),
        ("Resumo", {"fields": ("plan_summary",)}),
        ("Datas", {"fields": ("created_at", "updated_at")}),
    )

    def meals_count(self, obj):
        return obj.meals.count()
    meals_count.short_description = "Refeições"

    def plan_summary(self, obj):
        meals = obj.meals.prefetch_related("items__food").all()
        total_cals = sum(m.total_calories for m in meals)
        total_protein = sum(
            sum((i.food.protein_per_100g * i.quantity_grams) / 100 for i in m.items.all())
            for m in meals
        )
        return format_html(
            '<div style="padding:8px; background:#1e293b; border-radius:8px; color:#e2e8f0;">'
            '<strong>{:.0f} kcal</strong> total calculado · '
            '<span style="color:#60a5fa;">{:.0f}g proteína</span> · '
            '{} refeições</div>',
            total_cals, total_protein, meals.count(),
        )
    plan_summary.short_description = "Resumo Calculado"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.coach = request.user
        super().save_model(request, obj, form, change)

    # --- Ações ---
    @admin.action(description="Duplicar plano(s) alimentar(es)")
    def duplicate_plan(self, request, queryset):
        for plan in queryset:
            meals = list(plan.meals.prefetch_related("items").all())
            plan.pk = None
            plan.name = f"{plan.name} (cópia)"
            plan.save()
            for meal in meals:
                items = list(meal.items.all())
                meal.pk = None
                meal.plan = plan
                meal.save()
                for item in items:
                    item.pk = None
                    item.meal = meal
                    item.save()
        self.message_user(request, f"{queryset.count()} plano(s) duplicado(s).")

    actions = ["duplicate_plan"]


@admin.register(Meal)
class MealAdmin(ModelAdmin):
    list_display = ["get_display_name", "plan", "meal_type", "time", "total_calories_display", "items_count"]
    list_filter = ["meal_type", "plan"]
    search_fields = ["name", "plan__name"]
    inlines = [MealItemInline]

    def get_display_name(self, obj):
        return obj.name or obj.get_meal_type_display()
    get_display_name.short_description = "Refeição"

    def total_calories_display(self, obj):
        try:
            cals = float(obj.total_calories)
            return format_html('<strong>{:.0f}</strong> kcal', cals)
        except (TypeError, ValueError):
            return "—"
    total_calories_display.short_description = "Calorias"

    def items_count(self, obj):
        return obj.items.count()
    items_count.short_description = "Itens"


@admin.register(NutritionLog)
class NutritionLogAdmin(ModelAdmin):
    """Logs alimentares dos clientes (read-only para coach)."""
    list_display = ["client", "date", "meal", "completed"]
    list_filter = ["completed", "date", "client"]
    search_fields = ["client__first_name", "client__last_name"]
    date_hierarchy = "date"
    readonly_fields = ["client", "date", "meal", "completed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False