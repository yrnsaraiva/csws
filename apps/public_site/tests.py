import hashlib
import hmac
import json
import time
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat,
)
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.billing.models import Order
from apps.packages.models import ClientPackage, CoachingPackage
from apps.public_site import imali

User = get_user_model()

# Par de chaves RSA só para os testes — a publicKey precisa de ser válida
# para a encriptação em imali._private_key(), mas nenhum destes testes
# fala com um servidor real que a tente decifrar.
_TEST_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PUBLIC_KEY_PEM = _TEST_RSA_KEY.public_key().public_bytes(
    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo,
).decode('ascii')


def _fake_response(payload, status_code=200):
    class _Resp:
        def __init__(self, data, code):
            self._data = data
            self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f'HTTP {self.status_code}')

        def json(self):
            return self._data

    return _Resp(payload, status_code)


@override_settings(
    IMALI_API_KEY='test-api-key',
    IMALI_PUBLIC_KEY=_TEST_PUBLIC_KEY_PEM,
    IMALI_CLIENT_ID='test-client-id',
    IMALI_WEBHOOK_SECRET='test-webhook-secret',
    IMALI_STORE_ACCOUNT_NUMBER='260000079',
)
class CheckoutFlowTests(TestCase):
    """Fluxo de compra: create_order (iMali simulada) + webhook."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username='coach1', email='coach@example.com', password='x', role='coach',
        )
        self.package = CoachingPackage.objects.create(
            name='Pack Teste 30d',
            coach=self.coach,
            price=1000,
            duration_days=30,
            is_active=True,
        )
        self.order_payload = {
            'package_id': self.package.pk,
            'client_name': 'Cliente Teste',
            'client_email': 'cliente@example.com',
            'client_phone': '+258840000000',
            'goal': 'Hipertrofia',
            'notes': '',
        }

    def _post_order(self, payment_method='mpesa'):
        return self.client.post(
            reverse('public_site:create_order'),
            data=json.dumps({**self.order_payload, 'payment_method': payment_method}),
            content_type='application/json',
        )

    @patch('apps.public_site.imali.http_requests.post')
    def test_create_order_mpesa_fica_pending_a_aguardar_confirmacao(self, mock_post):
        mock_post.return_value = _fake_response({
            'data': {
                'transaction_id': 'MPS26ABCDEFG',
                'partner_transaction_id': 'placeholder',
                'amount': '1000',
                'status': 'PENDING',
            }
        })

        response = self._post_order('mpesa')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'pending')
        self.assertTrue(data['awaiting_confirmation'])
        self.assertTrue(data['order_ref'])

        order = Order.objects.get(ref=data['order_ref'])
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.gateway_transaction_id, 'MPS26ABCDEFG')

        # Verifica que o pedido enviado à iMali tem a forma certa.
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['payment_method'], 'mpesa')
        self.assertEqual(kwargs['json']['partner_transaction_id'], order.ref)
        self.assertEqual(len(order.ref), 12)
        self.assertIn('Authorization', kwargs['headers'])
        self.assertEqual(kwargs['headers']['X-Client-ID'], 'test-client-id')

    @patch('apps.public_site.imali.http_requests.post')
    def test_create_order_emola_fica_a_aguardar_confirmacao(self, mock_post):
        mock_post.return_value = _fake_response({
            'data': {
                'transaction_id': 'EML26ABCDEFG',
                'partner_transaction_id': 'placeholder',
                'amount': '1000',
                'status': 'PENDING',
            }
        })

        response = self._post_order('emola')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(Order.objects.get(ref=data['order_ref']).status, 'pending')

    @patch('apps.public_site.imali.http_requests.post')
    def test_create_order_metodo_nao_suportado(self, mock_post):
        response = self._post_order('visa')
        data = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        mock_post.assert_not_called()

    def _sign(self, timestamp: str, body: bytes) -> str:
        signed_payload = f'{timestamp}.'.encode('utf-8') + body
        digest = hmac.new(b'test-webhook-secret', signed_payload, hashlib.sha256).hexdigest()
        return f'sha256={digest}'

    def _post_webhook(self, event, signed=True, timestamp=None):
        body = json.dumps(event).encode()
        timestamp = timestamp or str(int(time.time()))
        headers = {'HTTP_X_WEBHOOK_TIMESTAMP': timestamp}
        if signed:
            headers['HTTP_X_WEBHOOK_SIGNATURE'] = self._sign(timestamp, body)
        return self.client.post(
            reverse('public_site:imali_webhook'),
            data=body,
            content_type='application/json',
            **headers,
        )

    def test_webhook_assinatura_invalida_rejeitado(self):
        order = Order.objects.create(
            ref='CSWEBHOOK001', package=self.package, client_name='X', client_email='x@example.com',
            client_phone='+258800000000', goal='g', amount=self.package.price, status='pending',
            gateway_transaction_id='tx_sig',
        )
        response = self._post_webhook(
            {'type': 'PAYMENT.SUCCESS', 'data': {'partner_transaction_id': order.ref}},
            signed=False,
        )
        self.assertEqual(response.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_webhook_timestamp_fora_da_janela_rejeitado(self):
        order = Order.objects.create(
            ref='CSWEBHOOK002', package=self.package, client_name='X', client_email='x@example.com',
            client_phone='+258800000000', goal='g', amount=self.package.price, status='pending',
        )
        old_timestamp = str(int(time.time()) - 600)  # 10 minutos atrás
        response = self._post_webhook(
            {'type': 'PAYMENT.SUCCESS', 'data': {'partner_transaction_id': order.ref}},
            timestamp=old_timestamp,
        )
        self.assertEqual(response.status_code, 401)

    def test_webhook_payment_success_activa_acesso_e_envia_email(self):
        order = Order.objects.create(
            ref='CSWEBHOOK003', package=self.package, client_name='Y', client_email='y@example.com',
            client_phone='+258800000001', goal='g', amount=self.package.price, status='pending',
        )
        response = self._post_webhook({
            'id': 'evt_1',
            'type': 'PAYMENT.SUCCESS',
            'payment_type': 'C2B',
            'data': {
                'amount': 1000,
                'status': 'SUCCESS',
                'transaction_id': 'MPS26SUCCESS',
                'partner_transaction_id': order.ref,
            },
        })
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.gateway_transaction_id, 'MPS26SUCCESS')
        self.assertTrue(ClientPackage.objects.filter(order=order, status='active').exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_webhook_payment_failed_nao_activa_acesso(self):
        order = Order.objects.create(
            ref='CSWEBHOOK004', package=self.package, client_name='Z', client_email='z@example.com',
            client_phone='+258800000002', goal='g', amount=self.package.price, status='pending',
        )
        response = self._post_webhook({
            'id': 'evt_2',
            'type': 'PAYMENT.FAILED',
            'payment_type': 'C2B',
            'data': {
                'status': 'FAILED',
                'status_reason': 'emola - Customer did not enter PIN',
                'transaction_id': 'EML26FAILED',
                'partner_transaction_id': order.ref,
            },
        })
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'failed')
        self.assertFalse(ClientPackage.objects.filter(order=order).exists())

    def test_webhook_repetido_nao_duplica_activacao(self):
        order = Order.objects.create(
            ref='CSWEBHOOK005', package=self.package, client_name='W', client_email='w@example.com',
            client_phone='+258800000003', goal='g', amount=self.package.price, status='pending',
        )
        event = {
            'type': 'PAYMENT.SUCCESS',
            'data': {'status': 'SUCCESS', 'transaction_id': 'DUP1', 'partner_transaction_id': order.ref},
        }
        self._post_webhook(event)
        self._post_webhook(event)

        self.assertEqual(
            ClientPackage.objects.filter(order=order).count(), 1,
            'o segundo webhook não deve criar um segundo acesso',
        )

    def test_webhook_referencia_desconhecida(self):
        response = self._post_webhook({
            'type': 'PAYMENT.SUCCESS',
            'data': {'partner_transaction_id': 'NAOEXISTE0001'},
        })
        self.assertEqual(response.status_code, 404)

    def test_order_status_endpoint(self):
        order = Order.objects.create(
            ref='CSSTATUS0001', package=self.package, client_name='S', client_email='s@example.com',
            client_phone='+258800000005', goal='g', amount=self.package.price, status='pending',
        )
        response = self.client.get(
            reverse('public_site:order_status', kwargs={'ref': order.ref})
        )
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'pending')

        response = self.client.get(
            reverse('public_site:order_status', kwargs={'ref': 'NAOEXISTE'})
        )
        self.assertEqual(response.status_code, 404)


class ImaliPublicKeyNormalizationTests(TestCase):
    """
    Regressão: "Unable to load PEM file ... MalformedFraming". Acontece
    quando o PEM é guardado numa variável de ambiente de uma linha e as
    quebras de linha ficam como `\\n` literal, ou com aspas a mais à volta.
    """

    def test_pem_com_quebras_de_linha_reais_carrega(self):
        with override_settings(IMALI_PUBLIC_KEY=_TEST_PUBLIC_KEY_PEM, IMALI_API_KEY='x'):
            imali._private_key()  # não deve lançar excepção

    def test_pem_com_barra_n_literal_carrega(self):
        single_line = _TEST_PUBLIC_KEY_PEM.replace('\n', '\\n')
        with override_settings(IMALI_PUBLIC_KEY=single_line, IMALI_API_KEY='x'):
            imali._private_key()

    def test_pem_entre_aspas_carrega(self):
        quoted = f'"{_TEST_PUBLIC_KEY_PEM}"'
        with override_settings(IMALI_PUBLIC_KEY=quoted, IMALI_API_KEY='x'):
            imali._private_key()

    def test_pem_invalido_da_erro_com_mensagem_util(self):
        with override_settings(IMALI_PUBLIC_KEY='isto não é um PEM', IMALI_API_KEY='x'):
            with self.assertRaisesMessage(ValueError, 'IMALI_PUBLIC_KEY'):
                imali._private_key()


class AdminRefundActionTests(TestCase):
    """A iMali não envia webhook de reembolso/chargeback — ação manual na admin."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username='coach2', email='coach2@example.com', password='x', role='coach',
        )
        self.package = CoachingPackage.objects.create(
            name='Pack Teste 30d', coach=self.coach, price=1000, duration_days=30, is_active=True,
        )
        self.client_user = User.objects.create_user(
            username='refundclient', email='refund@example.com', password='x', role='client',
        )
        self.order = Order.objects.create(
            ref='CSREFUND0001', package=self.package, client_name='R', client_email='refund@example.com',
            client_phone='+258800000009', goal='g', amount=self.package.price, status='paid',
        )
        self.client_package = ClientPackage.objects.create(
            client=self.client_user, package=self.package, order=self.order, status='active',
            start_date='2026-01-01', end_date='2026-12-31',
        )

    def test_marcar_reembolsada_cancela_acesso(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from apps.billing.admin import OrderAdmin

        request = RequestFactory().post('/admin/billing/order/')
        request.session = {}
        request._messages = FallbackStorage(request)

        admin = OrderAdmin(Order, AdminSite())
        admin.marcar_reembolsada(request, Order.objects.filter(pk=self.order.pk))

        self.order.refresh_from_db()
        self.client_package.refresh_from_db()
        self.assertEqual(self.order.status, 'refunded')
        self.assertEqual(self.client_package.status, 'cancelled')
