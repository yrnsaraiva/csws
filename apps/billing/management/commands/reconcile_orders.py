import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.billing.models import Order
from apps.billing.activation import activate_client_package
from apps.public_site.views import debitopay_check_status

logger = logging.getLogger(__name__)

# Valores de 'status' devolvidos pela Debito Pay em check-status que
# consideramos confirmados / definitivamente falhados. Ajustar conforme
# a documentação real da Debito Pay confirmar os valores exactos.
PAID_STATUSES = {'paid', 'completed', 'success'}
FAILED_STATUSES = {'failed', 'cancelled', 'expired', 'declined'}


class Command(BaseCommand):
    help = (
        "Reconcilia encomendas 'pending' há mais de 5 minutos consultando "
        "o estado real na Debito Pay (cobre timeouts em create_order e "
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
                data = debitopay_check_status(order)
            except Exception:
                logger.exception(f"RECONCILE falhou a consultar order {order.ref}")
                continue

            status = (data.get('status') or '').lower()

            if status in PAID_STATUSES:
                updated = Order.objects.filter(pk=order.pk, status='pending').update(
                    status='paid',
                    paysuite_id=data.get('payment_id') or order.paysuite_id,
                    paysuite_transaction_id=data.get('transactionId') or data.get('reference', ''),
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

            elif status in FAILED_STATUSES:
                Order.objects.filter(pk=order.pk, status='pending').update(status='failed')
                failed += 1

            # outros estados (ainda pending/processing) ficam como estão,
            # para serem verificados novamente na próxima execução.

        self.stdout.write(
            self.style.SUCCESS(
                f"{checked} encomenda(s) verificada(s): {confirmed} confirmada(s), "
                f"{failed} falhada(s)."
            )
        )
