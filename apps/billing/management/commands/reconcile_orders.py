import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.billing.models import Order
from apps.billing.activation import activate_client_package
from apps.public_site import imali

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reconcilia encomendas 'pending' há mais de 5 minutos consultando "
        "o estado real na iMali (cobre timeouts em create_order e "
        "webhooks perdidos)."
    )

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(minutes=5)
        stuck_orders = Order.objects.filter(status='pending', created_at__lte=cutoff)

        checked = 0
        confirmed = 0
        failed = 0

        for order in stuck_orders:
            checked += 1
            try:
                data = imali.check_status(order.ref, payment_type='push')
            except Exception:
                logger.exception(f"RECONCILE falhou a consultar order {order.ref}")
                continue

            status = (data.get('status') or '').upper()

            if status == 'SUCCESS':
                updated = Order.objects.filter(pk=order.pk, status='pending').update(
                    status='paid',
                )
                if updated:
                    order.refresh_from_db()
                    try:
                        activate_client_package(order)
                    except Exception:
                        logger.exception(
                            f"RECONCILE activate_client_package falhou para order {order.ref}"
                        )
                    confirmed += 1

            elif status in ('FAILED', 'EXPIRED'):
                Order.objects.filter(pk=order.pk, status='pending').update(status='failed')
                failed += 1

            # PENDING fica como está, para ser verificado novamente na
            # próxima execução.

        self.stdout.write(
            self.style.SUCCESS(
                f"{checked} encomenda(s) verificada(s): {confirmed} confirmada(s), "
                f"{failed} falhada(s)."
            )
        )
