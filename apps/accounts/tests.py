from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.nutrition.models import Meal, NutritionPlan
from apps.packages.models import ClientPackage, CoachingPackage
from apps.workouts.models import WorkoutDay, WorkoutLog, WorkoutPlan

User = get_user_model()


class LoginTests(TestCase):
    """Melhoria 2.3: sem open redirect e email tratado sem diferenciar maiúsculas."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cliente', email='Cliente@Example.com', password='segredo123', role='client',
        )

    def test_login_email_case_insensitive(self):
        response = self.client.post(reverse('accounts:login'), {
            'email': 'cliente@example.com', 'password': 'segredo123',
        })
        self.assertRedirects(response, reverse('accounts:dashboard'))

    def test_login_next_url_externo_e_ignorado(self):
        response = self.client.post(
            reverse('accounts:login') + '?next=https://evil.example.com/phish',
            {'email': 'cliente@example.com', 'password': 'segredo123'},
        )
        self.assertRedirects(response, reverse('accounts:dashboard'))

    def test_login_next_url_interno_e_respeitado(self):
        response = self.client.post(
            reverse('accounts:login') + '?next=/app/profile/',
            {'email': 'cliente@example.com', 'password': 'segredo123'},
        )
        self.assertRedirects(response, '/app/profile/')


class DashboardTests(TestCase):
    """Dashboard: treino/refeições do dia, streak, expiração do pacote."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username='coach', email='coach@example.com', password='x', role='coach',
        )
        self.client_user = User.objects.create_user(
            username='cliente', email='cliente@example.com', password='x', role='client',
        )
        self.client.force_login(self.client_user)
        self.today = timezone.localdate()

    def _active_package(self, workout_plan=None, nutrition_plan=None, end_date=None):
        package = CoachingPackage.objects.create(
            name='Pack Dashboard', coach=self.coach,
            workout_plan=workout_plan, nutrition_plan=nutrition_plan,
            price=100, duration_days=30, is_active=True,
        )
        return ClientPackage.objects.create(
            client=self.client_user, package=package, status='active',
            start_date=self.today - timedelta(days=1),
            end_date=end_date or (self.today + timedelta(days=29)),
        )

    def test_treino_do_dia_aparece_no_dashboard(self):
        plan = WorkoutPlan.objects.create(name='Plano', coach=self.coach)
        day = WorkoutDay.objects.create(
            plan=plan, name='Treino de hoje', day_of_week=self.today.isoweekday(),
        )
        self._active_package(workout_plan=plan)

        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['today_workout'], day)

    def test_refeicoes_do_dia_aparecem_no_dashboard(self):
        plan = NutritionPlan.objects.create(name='Plano Alimentar', coach=self.coach, target_calories=2000)
        meal_today = Meal.objects.create(plan=plan, meal_type='lunch', day_of_week=self.today.isoweekday())
        meal_other_day = Meal.objects.create(
            plan=plan, meal_type='dinner',
            day_of_week=(self.today.isoweekday() % 7) + 1,
        )
        self._active_package(nutrition_plan=plan)

        response = self.client.get(reverse('accounts:dashboard'))

        meal_ids = {m.pk for m in response.context['today_meals']}
        self.assertIn(meal_today.pk, meal_ids)
        self.assertNotIn(meal_other_day.pk, meal_ids)

    def test_streak_conta_dias_consecutivos_ate_hoje(self):
        plan = WorkoutPlan.objects.create(name='Plano', coach=self.coach)
        day = WorkoutDay.objects.create(plan=plan, name='Dia', day_of_week=1)
        self._active_package(workout_plan=plan)

        for delta in range(3):  # hoje, ontem, anteontem
            log = WorkoutLog.objects.create(client=self.client_user, workout_day=day, completed=True)
            WorkoutLog.objects.filter(pk=log.pk).update(date=self.today - timedelta(days=delta))

        # um treino de há 10 dias não deve "colar" ao streak actual
        gap_log = WorkoutLog.objects.create(client=self.client_user, workout_day=day, completed=True)
        WorkoutLog.objects.filter(pk=gap_log.pk).update(date=self.today - timedelta(days=10))

        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.context['streak'], 3)

    def test_pacote_expirado_nao_conta_como_activo(self):
        cp = self._active_package(end_date=self.today - timedelta(days=1))

        response = self.client.get(reverse('accounts:dashboard'))

        self.assertIsNone(response.context['active_package'])
        cp.refresh_from_db()
        self.assertEqual(cp.status, 'completed')
