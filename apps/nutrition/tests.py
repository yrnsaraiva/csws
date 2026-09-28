from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.nutrition.models import Meal, NutritionPlan
from apps.packages.models import ClientPackage, CoachingPackage

User = get_user_model()


class TwoClientsAccessIsolationTests(TestCase):
    """Melhoria 2.1: isolamento de planos alimentares entre clientes."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username='coach', email='coach@example.com', password='x', role='coach',
        )
        self.client_a = User.objects.create_user(
            username='clientea', email='a@example.com', password='x', role='client',
        )
        self.client_b = User.objects.create_user(
            username='clienteb', email='b@example.com', password='x', role='client',
        )

        self.plan_a, self.meal_a = self._build_plan('Plano Alimentar A')
        self.plan_b, self.meal_b = self._build_plan('Plano Alimentar B')

        self._assign_active_package(self.client_a, self.plan_a)
        self._assign_active_package(self.client_b, self.plan_b)

    def _build_plan(self, name):
        plan = NutritionPlan.objects.create(name=name, coach=self.coach, target_calories=2000)
        meal = Meal.objects.create(plan=plan, meal_type='lunch')
        return plan, meal

    def _assign_active_package(self, client, nutrition_plan):
        package = CoachingPackage.objects.create(
            name=f'Pack {client.username}', coach=self.coach, nutrition_plan=nutrition_plan,
            price=100, duration_days=30, is_active=True,
        )
        today = timezone.localdate()
        ClientPackage.objects.create(
            client=client, package=package, status='active',
            start_date=today, end_date=today + timedelta(days=30),
        )

    def test_cliente_nao_ve_plano_alimentar_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        r_own = self.client.get(reverse('nutrition:plan_detail', kwargs={'pk': self.plan_a.pk}))
        r_other = self.client.get(reverse('nutrition:plan_detail', kwargs={'pk': self.plan_b.pk}))
        self.assertEqual(r_own.status_code, 200)
        self.assertEqual(r_other.status_code, 404)

    def test_cliente_nao_ve_refeicao_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        r_own = self.client.get(reverse('nutrition:meal_detail', kwargs={'pk': self.meal_a.pk}))
        r_other = self.client.get(reverse('nutrition:meal_detail', kwargs={'pk': self.meal_b.pk}))
        self.assertEqual(r_own.status_code, 200)
        self.assertEqual(r_other.status_code, 404)

    def test_cliente_nao_consegue_marcar_refeicao_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        response = self.client.post(reverse('nutrition:toggle_meal', kwargs={'pk': self.meal_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_cliente_consegue_marcar_a_sua_propria_refeicao(self):
        self.client.force_login(self.client_a)
        response = self.client.post(
            reverse('nutrition:toggle_meal', kwargs={'pk': self.meal_a.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['completed'])
