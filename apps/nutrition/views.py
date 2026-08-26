from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone

from .models import NutritionPlan, Meal, MealItem, NutritionLog
from apps.accounts.mixins import ClientRequiredMixin
from apps.packages.models import ClientPackage


class NutritionPlanListView(LoginRequiredMixin, ClientRequiredMixin, ListView):
    """Lista planos alimentares do cliente."""
    model = NutritionPlan
    template_name = "nutrition/plan_list.html"
    context_object_name = "plans"

    def get_queryset(self):
        return NutritionPlan.objects.filter(
            coachingpackage__clientpackage__client=self.request.user,
            coachingpackage__clientpackage__status="active",
        ).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Calcular totais para cada plano
        for plan in ctx["plans"]:
            meals = plan.meals.prefetch_related("items__food").all()
            plan.total_calories = sum(m.total_calories for m in meals)
            plan.total_meals = meals.count()
        return ctx


class NutritionPlanDetailView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Detalhe do plano alimentar com macros e refeições."""
    model = NutritionPlan
    template_name = "nutrition/plan_detail.html"
    context_object_name = "plan"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plan = self.object
        today = timezone.now().date()

        # Refeições com macros calculados
        meals = plan.meals.prefetch_related("items__food").all()
        for meal in meals:
            items = meal.items.all()
            meal.calc_protein = sum(i.protein for i in items)
            meal.calc_carbs = sum(
                (i.food.carbs_per_100g * i.quantity_grams) / 100 for i in items
            )
            meal.calc_fat = sum(
                (i.food.fat_per_100g * i.quantity_grams) / 100 for i in items
            )

        ctx["meals"] = meals

        # Totais do dia
        total_cals = sum(m.total_calories for m in meals)
        total_protein = sum(m.calc_protein for m in meals)
        total_carbs = sum(m.calc_carbs for m in meals)
        total_fat = sum(m.calc_fat for m in meals)

        ctx["total_calories"] = total_cals
        ctx["total_protein"] = total_protein
        ctx["total_carbs"] = total_carbs
        ctx["total_fat"] = total_fat

        # Percentuais para gráficos circulares
        if plan.target_calories and plan.target_calories > 0:
            ctx["calories_pct"] = min(100, round(total_cals / plan.target_calories * 100))
        else:
            ctx["calories_pct"] = 0

        # Refeições completadas hoje
        completed = NutritionLog.objects.filter(
            client=self.request.user,
            date=today,
            completed=True,
        ).values_list("meal_id", flat=True)
        ctx["completed_meals"] = set(completed)

        return ctx


class MealDetailView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Detalhe de uma refeição específica."""
    model = Meal
    template_name = "nutrition/meal_detail.html"
    context_object_name = "meal"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = self.object.items.select_related("food").all()

        ctx["items"] = items
        ctx["total_calories"] = sum(i.calories for i in items)
        ctx["total_protein"] = sum(i.protein for i in items)
        ctx["total_carbs"] = sum(
            (i.food.carbs_per_100g * i.quantity_grams) / 100 for i in items
        )
        ctx["total_fat"] = sum(
            (i.food.fat_per_100g * i.quantity_grams) / 100 for i in items
        )
        return ctx


class ToggleMealLogView(LoginRequiredMixin, ClientRequiredMixin, View):
    """Marcar/desmarcar refeição como completa (AJAX ou redirect)."""

    def post(self, request, pk):
        meal = get_object_or_404(Meal, pk=pk)
        today = timezone.now().date()

        log, created = NutritionLog.objects.get_or_create(
            client=request.user,
            date=today,
            meal=meal,
            defaults={"completed": True},
        )

        if not created:
            log.completed = not log.completed
            log.save()

        # Se AJAX, retornar JSON
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({
                "status": "ok",
                "completed": log.completed,
                "meal_id": meal.pk,
            })

        # Redirect normal
        return redirect("nutrition:plan_detail", pk=meal.plan.pk)


class NutritionLogView(LoginRequiredMixin, ClientRequiredMixin, ListView):
    """Histórico de logs alimentares do cliente."""
    model = NutritionLog
    template_name = "nutrition/log.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self):
        return NutritionLog.objects.filter(
            client=self.request.user,
        ).select_related("meal__plan").order_by("-date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Agrupar por data
        logs_by_date = {}
        for log in ctx["logs"]:
            date_str = log.date.strftime("%Y-%m-%d")
            if date_str not in logs_by_date:
                logs_by_date[date_str] = {
                    "date": log.date,
                    "meals": [],
                    "completed_count": 0,
                    "total_count": 0,
                }
            logs_by_date[date_str]["meals"].append(log)
            logs_by_date[date_str]["total_count"] += 1
            if log.completed:
                logs_by_date[date_str]["completed_count"] += 1

        ctx["logs_by_date"] = logs_by_date
        return ctx