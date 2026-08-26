from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.packages.models import ClientPackage


class Command(BaseCommand):
    help = 'Marca como "completed" todos os ClientPackages cuja end_date já passou.'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        updated = ClientPackage.objects.filter(
            status='active',
            end_date__lt=today,
        ).update(status='completed')
        self.stdout.write(
            self.style.SUCCESS(f'{updated} pacote(s) expirado(s) com sucesso.')
        )
