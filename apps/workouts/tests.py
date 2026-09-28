from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.packages.models import ClientPackage, CoachingPackage
from apps.workouts.models import Exercise, WorkoutDay, WorkoutExercise, WorkoutLog, WorkoutPlan

User = get_user_model()


class TwoClientsAccessIsolationTests(TestCase):
    """
    Melhoria 2.1: um cliente não pode ver nem alterar treinos de outro
    cliente, mesmo sabendo o ID (ex: mudando o número no URL).
    """

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

        self.plan_a, self.day_a, self.we_a = self._build_plan('Plano A')
        self.plan_b, self.day_b, self.we_b = self._build_plan('Plano B')

        self._assign_active_package(self.client_a, self.plan_a)
        self._assign_active_package(self.client_b, self.plan_b)

    def _build_plan(self, name):
        plan = WorkoutPlan.objects.create(name=name, coach=self.coach)
        day = WorkoutDay.objects.create(plan=plan, name='Dia 1', day_of_week=1)
        exercise = Exercise.objects.create(name=f'Exercício {name}', created_by=self.coach)
        we = WorkoutExercise.objects.create(workout_day=day, exercise=exercise, sets=3)
        return plan, day, we

    def _assign_active_package(self, client, workout_plan):
        package = CoachingPackage.objects.create(
            name=f'Pack {client.username}', coach=self.coach, workout_plan=workout_plan,
            price=100, duration_days=30, is_active=True,
        )
        today = timezone.localdate()
        ClientPackage.objects.create(
            client=client, package=package, status='active',
            start_date=today, end_date=today + timedelta(days=30),
        )
        return package

    def test_cliente_nao_ve_plano_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        r_own = self.client.get(reverse('workouts:plan_detail', kwargs={'pk': self.plan_a.pk}))
        r_other = self.client.get(reverse('workouts:plan_detail', kwargs={'pk': self.plan_b.pk}))
        self.assertEqual(r_own.status_code, 200)
        self.assertEqual(r_other.status_code, 404)

    def test_cliente_nao_ve_dia_de_treino_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        r_own = self.client.get(reverse('workouts:day_detail', kwargs={'pk': self.day_a.pk}))
        r_other = self.client.get(reverse('workouts:day_detail', kwargs={'pk': self.day_b.pk}))
        self.assertEqual(r_own.status_code, 200)
        self.assertEqual(r_other.status_code, 404)

    def test_cliente_nao_consegue_iniciar_treino_de_outro_cliente(self):
        self.client.force_login(self.client_a)
        response = self.client.post(reverse('workouts:start_workout', kwargs={'pk': self.day_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(WorkoutLog.objects.filter(client=self.client_a, workout_day=self.day_b).exists())

    def test_save_set_so_grava_no_proprio_treino(self):
        self.client.force_login(self.client_a)
        log_b = WorkoutLog.objects.create(client=self.client_b, workout_day=self.day_b)

        response = self.client.post(reverse('workouts:save_set'), data={
            'log_id': log_b.pk,
            'workout_exercise_id': self.we_b.pk,
            'set_number': 1,
            'weight_kg': '50',
            'reps_done': '10',
            'completed': 'true',
        })

        self.assertEqual(response.status_code, 404)

    def test_save_set_no_proprio_treino_funciona(self):
        self.client.force_login(self.client_a)
        log_a = WorkoutLog.objects.create(client=self.client_a, workout_day=self.day_a)

        response = self.client.post(reverse('workouts:save_set'), data={
            'log_id': log_a.pk,
            'workout_exercise_id': self.we_a.pk,
            'set_number': 1,
            'weight_kg': '50',
            'reps_done': '10',
            'completed': 'true',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_save_set_com_treino_ja_terminado_falha(self):
        self.client.force_login(self.client_a)
        log_a = WorkoutLog.objects.create(client=self.client_a, workout_day=self.day_a, completed=True)

        response = self.client.post(reverse('workouts:save_set'), data={
            'log_id': log_a.pk,
            'workout_exercise_id': self.we_a.pk,
            'set_number': 1,
            'weight_kg': '50',
            'reps_done': '10',
            'completed': 'true',
        })

        self.assertEqual(response.status_code, 404)

    def test_save_set_numero_de_serie_fora_do_intervalo_falha(self):
        self.client.force_login(self.client_a)
        log_a = WorkoutLog.objects.create(client=self.client_a, workout_day=self.day_a)

        response = self.client.post(reverse('workouts:save_set'), data={
            'log_id': log_a.pk,
            'workout_exercise_id': self.we_a.pk,
            'set_number': 99,
            'weight_kg': '50',
            'reps_done': '10',
            'completed': 'true',
        })

        self.assertEqual(response.status_code, 400)
