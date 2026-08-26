from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, UpdateView, CreateView
from django.views import View
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.db.models import Count, Sum, Q
from datetime import timedelta

from .forms import ClientRegistrationForm, ProfileUpdateForm, ClientProfileForm
from .models import User, ClientProfile
from .mixins import ClientRequiredMixin
from apps.workouts.models import WorkoutLog, WorkoutPlan, WorkoutDay
from apps.nutrition.models import NutritionPlan, NutritionLog, Meal
from apps.packages.models import ClientPackage


class LoginView(View):
    """Login customizado com redirect para dashboard."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        return render(request, "accounts/login.html")

    def post(self, request):
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
            print(user)
        except User.DoesNotExist:
            user = None
            print(user)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "accounts:dashboard")
            return redirect(next_url)
        return render(request, "accounts/login.html", {
            "form": {"errors": True},
            "error_message": "Email ou senha incorretos.",
        })


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("accounts:login")


class RegisterView(CreateView):
    """Registro de cliente (pode ser desativado se coach cria contas)."""
    form_class = ClientRegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        user = form.save(commit=False)
        user.role = User.Role.CLIENT
        user.save()
        ClientProfile.objects.create(user=user)
        return super().form_valid(form)


class DashboardView(LoginRequiredMixin, ClientRequiredMixin, TemplateView):
    """Dashboard principal do cliente com resumo completo."""
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())

        # --- Auto-expirar pacotes cuja data já passou ---
        ClientPackage.objects.filter(
            client=user,
            status="active",
            end_date__lt=today,
        ).update(status="completed")

        # --- Pacote ativo (só conta se end_date ainda não passou) ---
        active_package = ClientPackage.objects.filter(
            client=user,
            status="active",
            end_date__gte=today,
        ).select_related("package__workout_plan", "package__nutrition_plan").first()
        ctx["active_package"] = active_package

        # --- Dias restantes do pacote ---
        if active_package:
            ctx["days_remaining"] = max(0, (active_package.end_date - today).days)
        else:
            ctx["days_remaining"] = 0

        # --- Treinos da semana ---
        workout_logs_week = WorkoutLog.objects.filter(
            client=user,
            date__gte=week_start,
            date__lte=today,
            completed=True,
        )
        ctx["workouts_this_week"] = workout_logs_week.count()

        # Total de dias de treino no plano ativo
        if active_package and active_package.package.workout_plan:
            plan = active_package.package.workout_plan
            ctx["total_days"] = plan.days.count()
        else:
            ctx["total_days"] = 0

        # --- Streak (dias consecutivos com treino) ---
        streak = 0
        check_date = today
        while True:
            has_log = WorkoutLog.objects.filter(
                client=user, date=check_date, completed=True
            ).exists()
            if has_log:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        ctx["streak"] = streak

        # --- Treino de hoje ---
        today_weekday = today.isoweekday()  # 1=Monday ... 7=Sunday
        today_workout = None
        if active_package and active_package.package.workout_plan:
            today_workout = WorkoutDay.objects.filter(
                plan=active_package.package.workout_plan,
                day_of_week=today_weekday,
            ).prefetch_related("exercises__exercise").first()
        ctx["today_workout"] = today_workout

        # Já treinou hoje?
        ctx["already_trained_today"] = WorkoutLog.objects.filter(
            client=user, date=today, completed=True
        ).exists()

        # --- Alimentação hoje ---
        if active_package and active_package.package.nutrition_plan:
            nutrition_plan = active_package.package.nutrition_plan
            ctx["today_meals"] = nutrition_plan.meals.prefetch_related("items__food").all()
            ctx["today_calories"] = nutrition_plan.target_calories or 0

            # Refeições completadas hoje
            completed_logs = NutritionLog.objects.filter(
                client=user, date=today, completed=True
            ).values_list("meal_id", flat=True)
            ctx["completed_meals"] = set(completed_logs)
        else:
            ctx["today_meals"] = []
            ctx["today_calories"] = 0
            ctx["completed_meals"] = set()

        # --- Atividade recente (últimos 7 treinos) ---
        ctx["recent_logs"] = WorkoutLog.objects.filter(
            client=user, completed=True
        ).select_related("workout_day").order_by("-date")[:7]

        return ctx


class ProfileView(LoginRequiredMixin, TemplateView):
    """Visualização do perfil do cliente."""
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["profile"] = getattr(user, "client_profile", None)

        # Estatísticas gerais
        ctx["total_workouts"] = WorkoutLog.objects.filter(
            client=user, completed=True
        ).count()
        ctx["total_minutes"] = WorkoutLog.objects.filter(
            client=user, completed=True
        ).aggregate(total=Sum("duration_minutes"))["total"] or 0
        ctx["member_since"] = user.date_joined

        return ctx


class ProfileUpdateView(LoginRequiredMixin, View):
    """Editar perfil e dados de cliente."""
    template_name = "accounts/profile_edit.html"

    def get(self, request):
        user_form = ProfileUpdateForm(instance=request.user)
        profile, _ = ClientProfile.objects.get_or_create(user=request.user)
        profile_form = ClientProfileForm(instance=profile)
        return render(request, self.template_name, {
            "user_form": user_form,
            "profile_form": profile_form,
        })

    def post(self, request):
        user_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        profile, _ = ClientProfile.objects.get_or_create(user=request.user)
        profile_form = ClientProfileForm(request.POST, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            return redirect("accounts:profile")

        return render(request, self.template_name, {
            "user_form": user_form,
            "profile_form": profile_form,
        })
