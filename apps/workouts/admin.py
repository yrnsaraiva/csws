from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import (
    MuscleGroup, Exercise, WorkoutPlan,
    WorkoutDay, WorkoutExercise, WorkoutLog, ExerciseLog,
)
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline


# ── Inlines ──────────────────────────────────────────

class WorkoutExerciseInline(TabularInline):
    """Exercícios dentro de um dia de treino."""
    model = WorkoutExercise
    extra = 1
    autocomplete_fields = ["exercise"]
    fields = [
        "order", "exercise", "sets", "reps",
        "rest_seconds", "tempo", "exercise_type",
        "superset_group", "notes",
    ]
    ordering = ["order"]


class WorkoutDayInline(TabularInline):
    """Dias dentro de um plano de treino."""
    model = WorkoutDay
    extra = 0
    show_change_link = True
    fields = ["order", "name", "day_of_week", "notes"]
    ordering = ["order", "day_of_week"]


class ExerciseLogInline(TabularInline):
    """Logs de séries dentro de um WorkoutLog."""
    model = ExerciseLog
    extra = 0
    readonly_fields = ["workout_exercise", "set_number", "weight_kg", "reps_done", "completed"]
    fields = ["workout_exercise", "set_number", "weight_kg", "reps_done", "completed", "notes"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# ── ModelAdmins ──────────────────────────────────────

@admin.register(MuscleGroup)
class MuscleGroupAdmin(ModelAdmin):
    list_display = ["name", "icon", "exercise_count"]
    search_fields = ["name"]

    def exercise_count(self, obj):
        return obj.exercises.count()
    exercise_count.short_description = "Nº Exercícios"


@admin.register(Exercise)
class ExerciseAdmin(ModelAdmin):
    list_display = ["name", "muscle_groups_display", "has_video", "created_by", "created_at"]
    list_filter = ["muscle_groups", "created_by"]
    search_fields = ["name", "description"]
    filter_horizontal = ["muscle_groups"]
    readonly_fields = ["created_at", "video_preview"]
    fieldsets = (
        (None, {"fields": ("name", "description", "muscle_groups", "created_by")}),
        ("Mídia", {"fields": ("video", "video_url", "thumbnail", "video_preview")}),
        ("Instruções", {"fields": ("instructions",)}),
    )

    def muscle_groups_display(self, obj):
        return ", ".join(mg.name for mg in obj.muscle_groups.all())
    muscle_groups_display.short_description = "Grupos Musculares"

    def has_video(self, obj):
        if obj.video or obj.video_url:
            return format_html('<span style="color: #22c55e;">{}</span>', "✔")
        return format_html('<span style="color: #ef4444;">{}</span>', "✘")

    def video_preview(self, obj):
        if obj.video_url:
            return format_html(
                '<iframe src="{}" width="400" height="225" frameborder="0" allowfullscreen></iframe>',
                obj.video_url,
            )
        if obj.video:
            return format_html(
                '<video width="400" controls><source src="{}" type="video/mp4"></video>',
                obj.video.url,
            )
        return "Sem vídeo"
    video_preview.short_description = "Pré-visualização"

    def save_model(self, request, obj, form, change):
        if not change:  # Novo exercício
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(ModelAdmin):
    list_display = ["name", "coach", "duration_weeks", "days_count", "is_active", "created_at"]
    list_filter = ["is_active", "coach", "duration_weeks"]
    search_fields = ["name", "description"]
    list_editable = ["is_active"]
    inlines = [WorkoutDayInline]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("name", "description", "coach")}),
        ("Configuração", {"fields": ("duration_weeks", "is_active")}),
        ("Datas", {"fields": ("created_at", "updated_at")}),
    )

    def days_count(self, obj):
        return obj.days.count()
    days_count.short_description = "Dias"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.coach = request.user
        super().save_model(request, obj, form, change)

    # --- Ações ---
    @admin.action(description="Duplicar plano(s) selecionado(s)")
    def duplicate_plan(self, request, queryset):
        for plan in queryset:
            days = list(plan.days.prefetch_related("exercises").all())
            plan.pk = None
            plan.name = f"{plan.name} (cópia)"
            plan.save()
            for day in days:
                exercises = list(day.exercises.all())
                day.pk = None
                day.plan = plan
                day.save()
                for we in exercises:
                    we.pk = None
                    we.workout_day = day
                    we.save()
        self.message_user(request, f"{queryset.count()} plano(s) duplicado(s).")

    @admin.action(description="Desativar plano(s)")
    def deactivate_plans(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} plano(s) desativado(s).")

    actions = ["duplicate_plan", "deactivate_plans"]


@admin.register(WorkoutDay)
class WorkoutDayAdmin(ModelAdmin):
    list_display = ["name", "plan", "day_of_week", "exercises_count"]
    list_filter = ["plan", "day_of_week"]
    search_fields = ["name", "plan__name"]
    inlines = [WorkoutExerciseInline]

    def exercises_count(self, obj):
        return obj.exercises.count()
    exercises_count.short_description = "Exercícios"


@admin.register(WorkoutLog)
class WorkoutLogAdmin(ModelAdmin):
    """Visualização dos treinos realizados pelos clientes (read-only para coach)."""
    list_display = ["client", "workout_day", "date", "completed", "duration_minutes", "sets_summary"]
    list_filter = ["completed", "date", "client", "workout_day__plan"]
    search_fields = ["client__first_name", "client__last_name", "workout_day__name"]
    date_hierarchy = "date"
    readonly_fields = ["client", "workout_day", "date", "completed", "duration_minutes"]
    inlines = [ExerciseLogInline]

    def sets_summary(self, obj):
        total = obj.exercise_logs.count()
        done = obj.exercise_logs.filter(completed=True).count()
        pct = round(done / total * 100) if total > 0 else 0
        color = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 50 else "#ef4444"
        return format_html(
            '<span style="color: {};">{}/{} ({}%)</span>',
            color, done, total, pct,
        )
    sets_summary.short_description = "Séries"

    def has_add_permission(self, request):
        return False  # Logs são criados pelo cliente

    def has_change_permission(self, request, obj=None):
        return False