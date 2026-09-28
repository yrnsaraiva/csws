import hashlib
import hmac
import json
import uuid
import logging

logger = logging.getLogger(__name__)

import requests as http_requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.db.models import Count
from django.utils import timezone

from apps.packages.models import CoachingPackage, ClientPackage
from apps.billing.models import Order
from apps.billing.activation import activate_client_package


def home(request):
    return render(request, "public_site/home.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEBITOPAY_BASE = 'https://gyqoaningqhurhvdugne.supabase.co/functions/v1'
DEBITOPAY_HEADERS = {
    'Authorization': f'Bearer {settings.DEBITOPAY_API_KEY}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

DEBITOPAY_MOBILE_MONEY_METHODS = {'mpesa', 'emola', 'mkesh'}
DEBITOPAY_HOSTED_CHECKOUT_METHODS = {'visa_mastercard', 'payfast'}
DEBITOPAY_SUPPORTED_METHODS = DEBITOPAY_MOBILE_MONEY_METHODS | DEBITOPAY_HOSTED_CHECKOUT_METHODS

DEBITOPAY_TIMEOUTS = {
    'mpesa': 90,
    'emola': 60,
    'mkesh': 60,
    'visa_mastercard': 30,
    'payfast': 30,
}


def _debitopay_create_payment(order, payment_method, phone=None):
    payload = {
        'action': 'process',
        'payment_method': payment_method,
        'merchant_id': settings.DEBITOPAY_MERCHANT_ID,
        'wallet_code': settings.DEBITOPAY_WALLET_CODE,
        'amount': float(order.amount),
        'currency': getattr(settings, 'DEBITOPAY_CURRENCY', 'MZN'),
        'source': 'gateway',
        'source_id': order.ref,
        'customer_name': order.client_name,
        'customer_email': order.client_email,
        'customer_phone': order.client_phone,
    }

    if payment_method in DEBITOPAY_MOBILE_MONEY_METHODS:
        if not phone:
            raise ValueError('Número de telefone obrigatório para mobile money.')
        payload['phone'] = phone
    elif payment_method in DEBITOPAY_HOSTED_CHECKOUT_METHODS:
        payload['return_url'] = settings.DEBITOPAY_RETURN_URL
    else:
        raise ValueError(f'Método de pagamento não suportado: {payment_method}')

    request_headers = {**DEBITOPAY_HEADERS, 'X-Idempotency-Key': order.ref}

    response = http_requests.post(
        f'{DEBITOPAY_BASE}/payment-orchestrator',
        headers=request_headers,
        json=payload,
        timeout=DEBITOPAY_TIMEOUTS.get(payment_method, 30),
    )
    response.raise_for_status()
    data = response.json()

    if not data.get('success'):
        raise http_requests.RequestException(data.get('error', 'Erro desconhecido na Debito Pay'))

    return data


def debitopay_check_status(order):
    """
    Consulta o estado real de um pagamento na Debito Pay (usado pelo
    comando reconcile_orders para encomendas 'pending' há muito tempo,
    tipicamente por causa de um timeout na chamada original a create_order).

    Devolve o dict da resposta da Debito Pay (inclui 'status').
    """
    payload = {
        'action': 'check-status',
        'merchant_id': settings.DEBITOPAY_MERCHANT_ID,
        'source': 'gateway',
        'source_id': order.ref,
    }
    if order.paysuite_id:
        payload['payment_id'] = order.paysuite_id

    response = http_requests.post(
        f'{DEBITOPAY_BASE}/payment-orchestrator',
        headers=DEBITOPAY_HEADERS,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _verify_debitopay_signature(request):
    signature = request.headers.get('X-Webhook-Signature', '')
    if not signature:
        return False
    expected = hmac.new(
        settings.DEBITOPAY_WEBHOOK_SECRET.encode('utf-8'),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _activate_client_package_safe(order, context=''):
    """
    Corre activate_client_package isolando qualquer falha não-crítica
    (ex.: envio de email de boas-vindas) para que nunca impeça o caller
    de devolver sucesso quando o pagamento já está confirmado e o
    order.status já foi actualizado para 'paid'.

    Devolve True se activate_client_package correu sem excepções,
    False se falhou (mas já foi registado em log — o caller decide
    se isso deve afectar a resposta).
    """
    try:
        activate_client_package(order)
        return True
    except Exception:
        logger.exception(
            f"ACTIVATION falhou depois do pagamento confirmado para order "
            f"{order.ref} ({context}) — verificar manualmente se o "
            f"email de boas-vindas / passos pós-activação ficaram por fazer."
        )
        return False


# ---------------------------------------------------------------------------
# 1. Página de checkout
# ---------------------------------------------------------------------------

def checkout_view(request):
    today = timezone.localdate()

    if request.user.is_authenticated and request.user.is_client:
        has_active = ClientPackage.objects.filter(
            client=request.user,
            status="active",
            end_date__gte=today,
        ).exists()
        if has_active:
            return redirect("accounts:dashboard")

    packages = list(
        CoachingPackage.objects
        .filter(is_active=True)
        .annotate(num_clients=Count('clientpackage'))
        .order_by('price')
    )

    if packages:
        most_popular = max(packages, key=lambda p: (p.num_clients, p.price))
        for pkg in packages:
            pkg.is_featured = (pkg.pk == most_popular.pk)

    return render(request, 'public_site/checkout.html', {'packages': packages})


# ---------------------------------------------------------------------------
# 2. Criar encomenda + iniciar pagamento na Debito Pay
# ---------------------------------------------------------------------------

@require_http_methods(['POST'])
def create_order(request):
    order = None
    try:
        body = json.loads(request.body)

        package_id = body.get('package_id')
        client_name = body.get('client_name', '').strip()
        client_email = body.get('client_email', '').strip()
        client_phone = body.get('client_phone', '').strip()
        goal = body.get('goal', '')
        notes = body.get('notes', '')
        payment_method = body.get('payment_method', 'mpesa').strip().lower()

        if not all([package_id, client_name, client_email, client_phone, goal]):
            return JsonResponse(
                {'success': False, 'error': 'Campos obrigatórios em falta.'},
                status=400,
            )

        if payment_method not in DEBITOPAY_SUPPORTED_METHODS:
            return JsonResponse(
                {'success': False, 'error': 'Método de pagamento não suportado.'},
                status=400,
            )

        try:
            package = CoachingPackage.objects.get(pk=package_id, is_active=True)
        except CoachingPackage.DoesNotExist:
            return JsonResponse(
                {'success': False, 'error': 'Pacote não encontrado ou inactivo.'},
                status=404,
            )

        order = Order.objects.create(
            ref=f'JN{uuid.uuid4().hex[:6].upper()}',
            package=package,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            goal=goal,
            notes=notes,
            amount=package.price,
            status='pending',
        )

        data = _debitopay_create_payment(order, payment_method, phone=client_phone)

        order.paysuite_id = data.get('payment_id', '')
        order.save(update_fields=['paysuite_id'])

        if payment_method == 'mpesa':
            if data.get('status') == 'success':
                Order.objects.filter(pk=order.pk, status='pending').update(
                    status='paid',
                    paysuite_transaction_id=data.get('transactionId', ''),
                )
                order.refresh_from_db()

                # O pagamento já está confirmado e o order já está 'paid'.
                # A partir daqui, activate_client_package é best-effort:
                # se falhar (ex.: SMTP do email de boas-vindas), NÃO
                # devolvemos erro ao cliente nem bloqueamos o redirect —
                # a conta/pacote já foram criados dentro dessa função
                # antes de chegar ao envio de email.
                _activate_client_package_safe(order, context='create_order/mpesa')

                return JsonResponse({
                    'success': True,
                    'status': 'paid',
                    'order_ref': order.ref,
                    'reference': data.get('reference', ''),
                })
            else:
                order.status = 'failed'
                order.save(update_fields=['status'])
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Pagamento M-Pesa não confirmado.',
                        'order_ref': order.ref,
                        'status': 'failed',
                    },
                    status=402,
                )

        elif payment_method in ('emola', 'mkesh'):
            return JsonResponse({
                'success': True,
                'status': 'pending',
                'awaiting_confirmation': True,
                'order_ref': order.ref,
                'reference': data.get('reference', ''),
            })

        else:  # visa_mastercard / payfast — Hosted Checkout
            return JsonResponse({
                'success': True,
                'status': 'redirect',
                'order_ref': order.ref,
                'checkout_url': data.get('checkout_url'),
            })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except http_requests.exceptions.Timeout:
        # A nossa ligação caiu, mas isso NÃO significa que a Debito Pay não
        # processou o pagamento. order.paysuite_id pode ainda não ter sido
        # guardado neste ponto (o timeout acontece antes do response.json()),
        # por isso a reconciliação posterior tem de usar order.ref
        # (enviado como source_id no payload) e não order.paysuite_id.
        ref = order.ref if order is not None else None
        logger.warning(f"GATEWAY timeout ao criar pagamento para order {ref}")
        return JsonResponse(
            {
                'success': False,
                'error': 'A confirmar o pagamento, isto pode demorar um pouco. Verifique o estado antes de tentar novamente.',
                'status': 'pending',
                'order_ref': ref,
            },
            status=202,
        )
    except http_requests.RequestException as e:
        logger.exception(f"GATEWAY erro ao criar pagamento (order {order.ref if order else '?'})")
        return JsonResponse(
            {'success': False, 'error': 'Erro ao contactar o gateway de pagamento. Tente novamente.'},
            status=502,
        )
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Pedido inválido.'}, status=400)
    except Exception:
        logger.exception(f"CREATE_ORDER erro inesperado (order {order.ref if order else '?'})")
        return JsonResponse(
            {'success': False, 'error': 'Ocorreu um erro inesperado. Tente novamente.'},
            status=500,
        )


# ---------------------------------------------------------------------------
# 3. Página de retorno (após pagamento cartão / PayFast no Hosted Checkout)
# ---------------------------------------------------------------------------

def checkout_return(request):
    return render(request, 'public_site/checkout_return.html')


# ---------------------------------------------------------------------------
# 4. Webhook Debito Pay
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def debitopay_webhook(request):
    if not _verify_debitopay_signature(request):
        logger.warning('WEBHOOK assinatura inválida — pedido rejeitado')
        return HttpResponse('Assinatura inválida.', status=401)

    try:
        event = json.loads(request.body)
        event_type = event.get('event')
        data = event.get('data', {})
        payment_id = data.get('payment_id')
        source_id = data.get('source_id') or event.get('source_id')

        order = None
        if payment_id:
            order = Order.objects.filter(paysuite_id=payment_id).first()
        if order is None and source_id:
            # Cobre o caso de um timeout em create_order: o pagamento foi
            # criado na Debito Pay mas paysuite_id nunca chegou a ser
            # gravado. order.ref foi enviado como source_id nesse pedido.
            order = Order.objects.filter(ref=source_id).first()

        if order is None:
            return HttpResponse('Referência desconhecida.', status=404)

        if payment_id and order.paysuite_id != payment_id:
            order.paysuite_id = payment_id
            order.save(update_fields=['paysuite_id'])

        if event_type == 'payment.completed' and order.status == 'paid':
            # Idempotência: só se aplica a payment.completed. Um
            # payment.refunded/chargeback chega precisamente quando o
            # order já está 'paid' e não deve ser ignorado por isso.
            logger.warning(f"WEBHOOK order já processado, ignorado: {order.ref}")
            return HttpResponse('OK', status=200)

        if event_type == 'payment.completed':
            updated = Order.objects.filter(
                pk=order.pk,
                status='pending',
            ).update(
                status='paid',
                paysuite_transaction_id=data.get('reference', ''),
            )

            if not updated:
                logger.warning(f"WEBHOOK race condition ignorada: {order.ref}")
                return HttpResponse('OK', status=200)

            order.refresh_from_db()

            # Mesma lógica do create_order: o order já está 'paid' neste
            # ponto. Se activate_client_package falhar a meio (ex.: email),
            # respondemos 200 à Debito Pay na mesma — devolver 500 aqui
            # só provoca retries do webhook que a idempotência acima (status
            # == 'paid') vai ignorar sem nunca voltar a tentar a activação.
            _activate_client_package_safe(order, context='webhook/payment.completed')

        elif event_type == 'payment.failed':
            Order.objects.filter(pk=order.pk, status='pending').update(
                status='failed',
            )

        elif event_type in ('payment.refunded', 'payment.chargeback'):
            new_status = 'refunded' if event_type == 'payment.refunded' else 'chargeback'
            Order.objects.filter(pk=order.pk).update(status=new_status)
            logger.warning(f"WEBHOOK {event_type} recebido para order {order.ref}")

            client_package = getattr(order, 'client_package', None)
            if client_package and client_package.status == 'active':
                client_package.status = 'cancelled'
                client_package.save(update_fields=['status'])

        return HttpResponse('OK', status=200)

    except Exception:
        logger.exception('WEBHOOK erro inesperado')
        return HttpResponse('Erro interno.', status=500)


# ---------------------------------------------------------------------------
# 5. Estado da encomenda (para o polling do checkout)
# ---------------------------------------------------------------------------

def order_status(request, ref):
    try:
        order = Order.objects.get(ref=ref)
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Encomenda não encontrada.'}, status=404)

    return JsonResponse({
        'success': True,
        'order_ref': order.ref,
        'status': order.status,
    })