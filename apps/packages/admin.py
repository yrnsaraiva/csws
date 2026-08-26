from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import CoachingPackage, ClientPackage
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline
from django.utils.safestring import mark_safe



class ClientPackageInline(TabularInline):
    """Clientes atribuídos a um pacote."""
    model = ClientPackage
    extra = 0
    autocomplete_fields = ["client"]
    fields = ["client", "status", "start_date", "end_date", "assigned_by"]
    readonly_fields = ["assigned_by"]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if not obj.assigned_by_id:
                obj.assigned_by = request.user
            obj.save()
        formset.save_m2m()


@admin.register(CoachingPackage)
class CoachingPackageAdmin(ModelAdmin):
    list_display = [
        "name", "coach", "workout_plan_link",
        "nutrition_plan_link", "price", "duration_days",
        "active_clients", "is_active",
    ]
    list_filter = ["is_active", "coach"]
    search_fields = ["name", "description"]
    list_editable = ["is_active", "price"]
    autocomplete_fields = ["workout_plan", "nutrition_plan"]
    inlines = [ClientPackageInline]
    readonly_fields = ["created_at"]

    fieldsets = (
        (None, {"fields": ("name", "description", "coach")}),
        ("Planos", {"fields": ("workout_plan", "nutrition_plan")}),
        ("Comercial", {"fields": ("price", "duration_days", "is_active")}),
        ("Info", {"fields": ("created_at",)}),
    )

    def workout_plan_link(self, obj):
        if obj.workout_plan:
            return format_html(
                '<a href="/admin/workouts/workoutplan/{}/change/">🏋️ {}</a>',
                obj.workout_plan.pk, obj.workout_plan.name,
            )
        return "—"
    workout_plan_link.short_description = "Plano Treino"

    def nutrition_plan_link(self, obj):
        if obj.nutrition_plan:
            return format_html(
                '<a href="/admin/nutrition/nutritionplan/{}/change/">🍽️ {}</a>',
                obj.nutrition_plan.pk, obj.nutrition_plan.name,
            )
        return "—"
    nutrition_plan_link.short_description = "Plano Alimentar"

    def active_clients(self, obj):
        count = obj.clientpackage_set.filter(status="active").count()
        return format_html('<span style="color:#22c55e; font-weight:bold;">{}</span>', count)
    active_clients.short_description = "Clientes Ativos"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.coach = request.user
        super().save_model(request, obj, form, change)

    # --- Ações ---
    @admin.action(description="Duplicar pacote(s)")
    def duplicate_package(self, request, queryset):
        for pkg in queryset:
            pkg.pk = None
            pkg.name = f"{pkg.name} (cópia)"
            pkg.save()
        self.message_user(request, f"{queryset.count()} pacote(s) duplicado(s).")

    actions = ["duplicate_package"]


@admin.register(ClientPackage)
class ClientPackageAdmin(ModelAdmin):
    list_display = [
        "client", "package", "status_badge",
        "start_date", "end_date", "days_remaining",
        "assigned_by", "status"
    ]
    list_filter = ["status", "package", "assigned_by"]
    search_fields = ["client__first_name", "client__last_name", "package__name"]
    autocomplete_fields = ["client", "package", "assigned_by"]
    date_hierarchy = "start_date"
    list_editable = ["status"]

    fieldsets = (
        (None, {"fields": ("client", "package")}),
        ("Período", {"fields": ("start_date", "end_date", "status")}),
        ("Atribuição", {"fields": ("assigned_by",)}),
    )

    def status_badge(self, obj):
        colors = {
            "active": "#22c55e",
            "paused": "#f59e0b",
            "completed": "#60a5fa",
            "cancelled": "#ef4444",
        }
        color = colors.get(obj.status, "#9ca3af")
        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Estado"

    def days_remaining(self, obj):
        if obj.status != "active":
            return "—"
        remaining = (obj.end_date - timezone.now().date()).days
        if remaining < 0:
            return mark_safe('<span style="color:#ef4444;">Expirado</span>')
        if remaining <= 7:
            return mark_safe('<span style="color:#f59e0b;">{} dias</span>', remaining)
        return f"{remaining} dias"
    days_remaining.short_description = "Dias Restantes"

    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)

    # --- Ações ---
    @admin.action(description="Ativar pacote(s)")
    def activate_packages(self, request, queryset):
        count = queryset.update(status="active")
        self.message_user(request, f"{count} pacote(s) ativado(s).")

    @admin.action(description="Pausar pacote(s)")
    def pause_packages(self, request, queryset):
        count = queryset.update(status="paused")
        self.message_user(request, f"{count} pacote(s) pausado(s).")

    @admin.action(description="Cancelar pacote(s)")
    def cancel_packages(self, request, queryset):
        count = queryset.update(status="cancelled")
        self.message_user(request, f"{count} pacote(s) cancelado(s).")

    @admin.action(description="Renovar por 30 dias")
    def renew_30_days(self, request, queryset):
        from datetime import timedelta
        for cp in queryset:
            cp.end_date = timezone.now().date() + timedelta(days=30)
            cp.status = "active"
            cp.save()
        self.message_user(request, f"{queryset.count()} pacote(s) renovado(s) por 30 dias.")

    actions = ["activate_packages", "pause_packages", "cancel_packages", "renew_30_days"]