from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Max

from .models import WorkoutPlan, WorkoutDay, WorkoutLog, ExerciseLog, WorkoutExercise
from .forms import ExerciseLogForm
from apps.accounts.mixins import ClientRequiredMixin


class WorkoutPlanListView(LoginRequiredMixin, ClientRequiredMixin, ListView):
    """Lista planos de treino atribuídos ao cliente."""
    model = WorkoutPlan
    template_name = "workouts/plan_list.html"
    context_object_name = "plans"

    def get_queryset(self):
        return WorkoutPlan.objects.filter(
            coachingpackage__clientpackage__client=self.request.user,
            coachingpackage__clientpackage__status="active",
        ).prefetch_related(
            "days__exercises__exercise__muscle_groups"
        ).distinct()


class WorkoutPlanDetailView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Detalhes do plano com todos os dias."""
    model = WorkoutPlan
    template_name = "workouts/plan_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        days = self.object.days.prefetch_related(
            "exercises__exercise__muscle_groups"
        ).all()

        # Adicionar info de último treino por dia
        for day in days:
            last_log = WorkoutLog.objects.filter(
                client=self.request.user,
                workout_day=day,
                completed=True,
            ).order_by("-date").first()
            day.last_completed = last_log.date if last_log else None
            day.times_completed = WorkoutLog.objects.filter(
                client=self.request.user,
                workout_day=day,
                completed=True,
            ).count()

        ctx["days"] = days
        return ctx


class WorkoutDayDetailView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Visualização de um dia de treino (pré-sessão)."""
    model = WorkoutDay
    template_name = "workouts/day_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["exercises"] = self.object.exercises.select_related(
            "exercise"
        ).prefetch_related("exercise__muscle_groups").all()

        # Último peso usado por exercício (para sugerir)
        last_weights = {}
        for we in ctx["exercises"]:
            last_log = ExerciseLog.objects.filter(
                workout_log__client=self.request.user,
                workout_exercise=we,
            ).order_by("-workout_log__date", "-set_number").first()
            if last_log:
                last_weights[we.pk] = {
                    "weight": last_log.weight_kg,
                    "reps": last_log.reps_done,
                }
        ctx["last_weights"] = last_weights
        return ctx


class StartWorkoutView(LoginRequiredMixin, ClientRequiredMixin, View):
    """Inicia sessão de treino — cria WorkoutLog e redireciona."""

    def post(self, request, pk):
        day = get_object_or_404(WorkoutDay, pk=pk)

        # Verificar se já existe treino não finalizado hoje
        existing_log = WorkoutLog.objects.filter(
            client=request.user,
            workout_day=day,
            date=timezone.now().date(),
            completed=False,
        ).first()

        if existing_log:
            return redirect("workouts:session", pk=existing_log.pk)

        # Criar novo log
        log = WorkoutLog.objects.create(
            client=request.user,
            workout_day=day,
        )

        # Criar logs vazios para cada série de cada exercício
        for we in day.exercises.all():
            for s in range(1, we.sets + 1):
                ExerciseLog.objects.create(
                    workout_log=log,
                    workout_exercise=we,
                    set_number=s,
                    completed=False,
                )

        return redirect("workouts:session", pk=log.pk)


class WorkoutSessionView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Página de execução de treino (session ativa)."""
    model = WorkoutLog
    template_name = "workouts/workout_session.html"
    context_object_name = "log"

    def get_queryset(self):
        return WorkoutLog.objects.filter(client=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        log = self.object
        workout_day = log.workout_day

        exercises = workout_day.exercises.select_related(
            "exercise"
        ).prefetch_related("exercise__muscle_groups").all()

        # Adicionar set_range e logs existentes a cada exercício
        for we in exercises:
            we.set_range = range(1, we.sets + 1)
            we.existing_logs = {
                el.set_number: el
                for el in log.exercise_logs.filter(workout_exercise=we)
            }

        ctx["exercises"] = exercises
        ctx["workout_day"] = workout_day
        return ctx


class SaveSetLogView(LoginRequiredMixin, View):
    """AJAX: Salvar dados de uma série individual."""

    def post(self, request):
        log_id = request.POST.get("log_id")
        exercise_id = request.POST.get("workout_exercise_id")
        set_number = int(request.POST.get("set_number", 0))
        weight = request.POST.get("weight_kg")
        reps = request.POST.get("reps_done")
        completed = request.POST.get("completed") == "true"

        exercise_log, created = ExerciseLog.objects.update_or_create(
            workout_log_id=log_id,
            workout_exercise_id=exercise_id,
            set_number=set_number,
            defaults={
                "weight_kg": float(weight) if weight else None,
                "reps_done": int(reps) if reps else None,
                "completed": completed,
            },
        )

        return JsonResponse({
            "status": "ok",
            "created": created,
            "log_id": exercise_log.pk,
        })


class FinishWorkoutView(LoginRequiredMixin, ClientRequiredMixin, View):
    """Finaliza sessão de treino."""

    def post(self, request, pk):
        log = get_object_or_404(WorkoutLog, pk=pk, client=request.user)

        if log.started_at:
            delta = timezone.now() - log.started_at
            duration = int(delta.total_seconds() // 60)
            log.duration_minutes = min(duration, 300)  # cap 5h

        log.completed = True
        log.save()

        return redirect("workouts:log_detail", pk=log.pk)


class WorkoutLogDetailView(LoginRequiredMixin, ClientRequiredMixin, DetailView):
    """Resumo pós-treino."""
    model = WorkoutLog
    template_name = "workouts/log_detail.html"
    context_object_name = "log"

    def get_queryset(self):
        return WorkoutLog.objects.filter(client=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        log = self.object
        exercise_logs = log.exercise_logs.select_related(
            "workout_exercise__exercise"
        ).order_by("workout_exercise__order", "set_number")

        # Agrupar por exercício
        grouped = {}
        for el in exercise_logs:
            name = el.workout_exercise.exercise.name
            if name not in grouped:
                grouped[name] = []
            grouped[name].append(el)

        ctx["grouped_logs"] = grouped
        ctx["total_sets"] = exercise_logs.count()
        ctx["completed_sets"] = exercise_logs.filter(completed=True).count()
        ctx["total_volume"] = sum(
            (el.weight_kg or 0) * (el.reps_done or 0)
            for el in exercise_logs if el.completed
        )
        return ctx


class WorkoutHistoryView(LoginRequiredMixin, ClientRequiredMixin, ListView):
    """Histórico de treinos do cliente."""
    model = WorkoutLog
    template_name = "workouts/history.html"
    context_object_name = "logs"
    paginate_by = 20

    def get_queryset(self):
        return WorkoutLog.objects.filter(
            client=self.request.user,
            completed=True,
        ).select_related("workout_day__plan").order_by("-date")