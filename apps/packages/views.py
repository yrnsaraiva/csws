from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import ListView, DetailView

from .models import CoachingPackage, ClientPackage
from apps.accounts.mixins import ClientRequiredMixin


class MyPackagesView(LoginRequiredMixin, ClientRequiredMixin, ListView):
    """Pacotes atribuídos ao cliente."""
    model = ClientPackage
    template_name = "packages/my_packages.html"
    context_object_name = "client_packages"

    def get_queryset(self):
        today = timezone.now().date()

        # Auto-expirar pacotes cuja data já passou
        ClientPackage.objects.filter(
            client=self.request.user,
            status="active",
            end_date__lt=today,
        ).update(status="completed")

        return ClientPackage.objects.filter(
            client=self.request.user,
        ).select_related(
            "package__workout_plan",
            "package__nutrition_plan",
            "package__coach",
        ).order_by("-start_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()
        ctx["active_package"] = self.get_queryset().filter(
            status="active",
            end_date__gte=today,
        ).first()
        return ctx
