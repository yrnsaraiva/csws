from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.db import models
from django.utils.html import format_html
from .models import User, ClientProfile

from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin
from unfold.admin import StackedInline


admin.site.unregister(Group)


class ClientProfileInline(StackedInline):
    model = ClientProfile
    can_delete = False
    verbose_name = "Dados do Cliente"
    verbose_name_plural = "Dados do Cliente"
    fields = ["height_cm", "weight_kg", "goal", "notes"]


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    """Admin customizado para User com roles."""
    list_display = ["email", "get_full_name", "role", "coach", "is_active", "date_joined"]
    list_filter = ["role", "is_active", "coach"]
    search_fields = ["email", "first_name", "last_name"]
    list_editable = ["role", "is_active"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informações Pessoais", {"fields": (
            "first_name", "last_name", "email", "phone",
            "photo", "bio", "date_of_birth",
        )}),
        ("Coaching", {"fields": ("role", "coach")}),
        ("Permissões", {"fields": (
            "is_active", "is_staff", "is_superuser",
            "groups", "user_permissions",
        )}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "first_name", "last_name",
                "role", "coach", "password1", "password2",
            ),
        }),
    )

    def get_inlines(self, request, obj=None):
        """Mostrar inline de perfil apenas para clientes."""
        if obj and obj.is_client:
            return [ClientProfileInline]
        return []

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Coach só vê os seus clientes + a si próprio
        if not request.user.is_superuser and request.user.is_coach:
            return qs.filter(
                models.Q(pk=request.user.pk) |
                models.Q(coach=request.user)
            )
        return qs

    # --- Ações customizadas ---
    @admin.action(description="Ativar utilizadores selecionados")
    def activate_users(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} utilizador(es) ativado(s).")

    @admin.action(description="Desativar utilizadores selecionados")
    def deactivate_users(self, request, queryset):
        queryset = queryset.exclude(pk=request.user.pk)  # Não desativar a si próprio
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} utilizador(es) desativado(s).")

    @admin.action(description="Atribuir-me como coach")
    def assign_me_as_coach(self, request, queryset):
        count = queryset.filter(role=User.Role.CLIENT).update(coach=request.user)
        self.message_user(request, f"{count} cliente(s) atribuído(s) a si.")

    actions = ["activate_users", "deactivate_users", "assign_me_as_coach"]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass