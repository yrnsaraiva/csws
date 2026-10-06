import types
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.public_site import imali


class Command(BaseCommand):
    help = (
        "Testa a API da iMali directamente (criação de pagamento ou consulta "
        "de estado), sem passar pelo checkout nem criar uma Order real. Útil "
        "para testar valores diferentes de store_account_number, telefone ou "
        "método sem precisar de redeploy a cada tentativa.\n\n"
        "AVISO: --check é só leitura, mas criar um pagamento envia mesmo um "
        "pedido de confirmação real para o telefone indicado (mesmo em "
        "ambiente de teste da iMali) — usa o teu próprio número."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            help='Número de telefone do cliente (ex: 84XXXXXXX ou +258 84 XXX XXXX).',
        )
        parser.add_argument(
            '--amount', type=float, default=10.0,
            help='Valor a pagar em MT (mínimo 10). Default: 10.',
        )
        parser.add_argument(
            '--method', default='mpesa', choices=sorted(imali.SUPPORTED_METHODS),
            help='Método de pagamento. Default: mpesa.',
        )
        parser.add_argument(
            '--store',
            help=(
                'Store account number a usar, só nesta execução '
                '(sobrepõe IMALI_STORE_ACCOUNT_NUMBER sem alterar a variável '
                'de ambiente nem precisar de redeploy).'
            ),
        )
        parser.add_argument(
            '--check', metavar='REF',
            help='Em vez de criar um pagamento, consulta o estado desta referência (partner_transaction_id).',
        )

    def handle(self, *args, **options):
        if options['store']:
            settings.IMALI_STORE_ACCOUNT_NUMBER = options['store']

        if options['check']:
            self._check(options['check'])
            return

        if not options['phone']:
            raise CommandError('--phone é obrigatório para criar um pagamento (ou usa --check <ref>).')

        self._create(options)

    def _create(self, options):
        ref = f'TEST{uuid.uuid4().hex[:8].upper()}'
        # Objecto descartável — só precisa de .ref e .amount, como uma Order.
        # Não cria nenhuma linha na base de dados.
        fake_order = types.SimpleNamespace(ref=ref, amount=options['amount'])

        self.stdout.write(self.style.WARNING(
            f"A criar pagamento de teste:\n"
            f"  método  = {options['method']}\n"
            f"  telefone= {options['phone']}\n"
            f"  valor   = {options['amount']}\n"
            f"  loja    = {settings.IMALI_STORE_ACCOUNT_NUMBER}\n"
            f"  ref     = {ref}\n"
        ))

        try:
            data = imali.create_push_payment(fake_order, options['method'], phone=options['phone'])
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Falhou: {e}"))
            return

        self.stdout.write(self.style.SUCCESS(f"OK — resposta da iMali: {data}"))
        self.stdout.write(
            f"\nPara consultar o estado depois de confirmar/rejeitar no telemóvel:\n"
            f"  python manage.py imali_test_payment --check {ref}"
        )

    def _check(self, ref):
        self.stdout.write(self.style.WARNING(f"A consultar estado de {ref}..."))
        try:
            data = imali.check_status(ref, payment_type='push')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Falhou: {e}"))
            return
        self.stdout.write(self.style.SUCCESS(f"Estado: {data}"))
