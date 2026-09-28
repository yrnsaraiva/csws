import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.billing.models import Order
from apps.nutrition.models import NutritionPlan
from apps.packages.models import ClientPackage, CoachingPackage
from apps.workouts.models import WorkoutPlan

User = get_user_model()


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


@override_settings(DEBITOPAY_WEBHOOK_SECRET='test-webhook-secret')
class CheckoutFlowTests(TestCase):
    """Fluxo de compra: create_order (Debito Pay simulada) + webhook."""

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

    @patch('apps.public_site.views.http_requests.post')
    def test_create_order_mpesa_confirmado_cria_acesso_e_envia_email(self, mock_post):
        mock_post.return_value = _fake_response({
            'success': True,
            'status': 'success',
            'payment_id': 'pay_123',
            'transactionId': 'tx_123',
            'reference': 'ref_123',
        })

        response = self._post_order('mpesa')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'paid')
        self.assertTrue(data['order_ref'])

        order = Order.objects.get(ref=data['order_ref'])
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.paysuite_id, 'pay_123')

        user = User.objects.get(email='cliente@example.com')
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            ClientPackage.objects.filter(client=user, package=self.package, order=order, status='active').exists()
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('password', mail.outbox[0].alternatives[0][0].lower())

    @patch('apps.public_site.views.http_requests.post')
    def test_create_order_mpesa_nao_confirmado_nao_cria_acesso(self, mock_post):
        mock_post.return_value = _fake_response({
            'success': True,
            'status': 'failed',
            'payment_id': 'pay_456',
        })

        response = self._post_order('mpesa')
        data = response.json()

        self.assertEqual(response.status_code, 402)
        self.assertEqual(data['status'], 'failed')
        self.assertFalse(User.objects.filter(email='cliente@example.com').exists())

    @patch('apps.public_site.views.http_requests.post')
    def test_create_order_emola_fica_a_aguardar_confirmacao(self, mock_post):
        mock_post.return_value = _fake_response({
            'success': True,
            'payment_id': 'pay_789',
            'reference': 'ref_789',
        })

        response = self._post_order('emola')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'pending')
        self.assertTrue(data['awaiting_confirmation'])
        self.assertEqual(Order.objects.get(ref=data['order_ref']).status, 'pending')

    def _sign(self, body: bytes) -> str:
        return hmac.new(b'test-webhook-secret', body, hashlib.sha256).hexdigest()

    def _post_webhook(self, event, signed=True):
        body = json.dumps(event).encode()
        headers = {}
        if signed:
            headers['HTTP_X_WEBHOOK_SIGNATURE'] = self._sign(body)
        return self.client.post(
            reverse('public_site:debitopay_webhook'),
            data=body,
            content_type='application/json',
            **headers,
        )

    def test_webhook_assinatura_invalida_rejeitado(self):
        order = Order.objects.create(
            ref='JNWEBHOOK1', package=self.package, client_name='X', client_email='x@example.com',
            client_phone='+258800000000', goal='g', amount=self.package.price, status='pending',
            paysuite_id='pay_sig',
        )
        response = self._post_webhook(
            {'event': 'payment.completed', 'data': {'payment_id': 'pay_sig'}}, signed=False
        )
        self.assertEqual(response.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_webhook_payment_completed_activa_acesso(self):
        order = Order.objects.create(
            ref='JNWEBHOOK2', package=self.package, client_name='Y', client_email='y@example.com',
            client_phone='+258800000001', goal='g', amount=self.package.price, status='pending',
            paysuite_id='pay_ok',
        )
        response = self._post_webhook({
            'event': 'payment.completed',
            'data': {'payment_id': 'pay_ok', 'reference': 'tx_ok'},
        })
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertTrue(ClientPackage.objects.filter(order=order, status='active').exists())

    def test_webhook_repetido_nao_duplica_activacao(self):
        order = Order.objects.create(
            ref='JNWEBHOOK3', package=self.package, client_name='Z', client_email='z@example.com',
            client_phone='+258800000002', goal='g', amount=self.package.price, status='pending',
            paysuite_id='pay_dup',
        )
        event = {'event': 'payment.completed', 'data': {'payment_id': 'pay_dup', 'reference': 'tx_dup'}}
        self._post_webhook(event)
        self._post_webhook(event)

        self.assertEqual(
            ClientPackage.objects.filter(order=order).count(), 1,
            'o segundo webhook não deve criar um segundo acesso',
        )

    def test_webhook_sem_paysuite_id_usa_ref_como_fallback(self):
        """Timeout em create_order: paysuite_id nunca foi gravado."""
        order = Order.objects.create(
            ref='JNTIMEOUT1', package=self.package, client_name='W', client_email='w@example.com',
            client_phone='+258800000003', goal='g', amount=self.package.price, status='pending',
            paysuite_id='',
        )
        response = self._post_webhook({
            'event': 'payment.completed',
            'data': {'payment_id': 'pay_late', 'reference': 'tx_late', 'source_id': order.ref},
        })
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.paysuite_id, 'pay_late')

    def test_webhook_refund_cancela_acesso(self):
        order = Order.objects.create(
            ref='JNREFUND1', package=self.package, client_name='R', client_email='r@example.com',
            client_phone='+258800000004', goal='g', amount=self.package.price, status='paid',
            paysuite_id='pay_refund',
        )
        user = User.objects.create_user(username='rclient', email='r@example.com', password='x', role='client')
        cp = ClientPackage.objects.create(
            client=user, package=self.package, order=order, status='active',
            start_date='2026-01-01', end_date='2026-12-31',
        )

        response = self._post_webhook({
            'event': 'payment.refunded',
            'data': {'payment_id': 'pay_refund'},
        })
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        cp.refresh_from_db()
        self.assertEqual(order.status, 'refunded')
        self.assertEqual(cp.status, 'cancelled')

    def test_order_status_endpoint(self):
        order = Order.objects.create(
            ref='JNSTATUS1', package=self.package, client_name='S', client_email='s@example.com',
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
