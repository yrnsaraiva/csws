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

# Métodos suportados no checkout. mpesa/emola/mkesh exigem "phone" e são
# mobile money (mpesa confirma sync, emola/mkesh confirmam via webhook).
# visa_mastercard/payfast devolvem um checkout_url (Hosted Checkout) e
# exigem "return_url".
DEBITOPAY_MOBILE_MONEY_METHODS = {'mpesa', 'emola', 'mkesh'}
DEBITOPAY_HOSTED_CHECKOUT_METHODS = {'visa_mastercard', 'payfast'}
DEBITOPAY_SUPPORTED_METHODS = DEBITOPAY_MOBILE_MONEY_METHODS | DEBITOPAY_HOSTED_CHECKOUT_METHODS

DEBITOPAY_TIMEOUTS = {
    'mpesa': 90,          # síncrono, espera confirmação do PIN no telemóvel
    'emola': 60,
    'mkesh': 60,
    'visa_mastercard': 30,
    'payfast': 30,
}


def _debitopay_create_payment(order, payment_method, phone=None):
    """
    Cria um payment na Debito Pay via /payment-orchestrator e devolve o
    JSON de resposta completo (o formato varia consoante payment_method).
    """
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

    # X-Idempotency-Key evita que um retry (ex.: depois de um timeout) crie
    # um segundo pagamento na Debito Pay para o mesmo order.
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


def _verify_debitopay_signature(request):
    """Valida a assinatura HMAC-SHA256 do webhook (header X-Webhook-Signature)."""
    signature = request.headers.get('X-Webhook-Signature', '')
    if not signature:
        return False
    expected = hmac.new(
        settings.DEBITOPAY_WEBHOOK_SECRET.encode('utf-8'),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# 1. Página de checkout
# ---------------------------------------------------------------------------

def checkout_view(request):
    """
    Renderiza a página de checkout com os pacotes activos da base de dados.
    Marca como 'is_featured' o pacote com mais clientes.
    Em empate, ganha o de maior preço.

    Clientes com subscrição ainda activa são redirecionados para o dashboard.
    """
    today = timezone.now().date()

    # Bloquear acesso ao checkout se o cliente já tem subscrição activa
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
    """
    Recebe os dados do checkout, cria o Order com status 'pending' e chama a
    Debito Pay. O comportamento depende do payment_method escolhido:

    - mpesa: confirmação síncrona. Se success, activamos o pacote já aqui.
    - emola / mkesh: assíncrono, fica 'pending' até o webhook confirmar.
    - visa_mastercard / payfast: devolvemos checkout_url para o frontend
      redirecionar para o Hosted Checkout da Debito Pay.
    """
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

        # Cria o Order localmente antes de ir à Debito Pay
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

        # Cria o payment na Debito Pay
        data = _debitopay_create_payment(order, payment_method, phone=client_phone)

        # NOTA: reaproveitamos os campos paysuite_id / paysuite_transaction_id
        # que já existiam no modelo para guardar o payment_id / referência da
        # Debito Pay, para não obrigar a uma migração. Considera renomeá-los
        # (ex.: debitopay_payment_id) numa migração futura.
        order.paysuite_id = data.get('payment_id', '')
        order.save(update_fields=['paysuite_id'])

        if payment_method == 'mpesa':
            # Confirmação síncrona
            if data.get('status') == 'success':
                Order.objects.filter(pk=order.pk, status='pending').update(
                    status='paid',
                    paysuite_transaction_id=data.get('transactionId', ''),
                )
                order.refresh_from_db()
                activate_client_package(order)
                return JsonResponse({
                    'success': True,
                    'status': 'paid',
                    'reference': data.get('reference', ''),
                })
            else:
                order.status = 'failed'
                order.save(update_fields=['status'])
                return JsonResponse(
                    {'success': False, 'error': 'Pagamento M-Pesa não confirmado.'},
                    status=402,
                )

        elif payment_method in ('emola', 'mkesh'):
            # Assíncrono — aguardar webhook payment.completed
            return JsonResponse({
                'success': True,
                'status': 'pending',
                'awaiting_confirmation': True,
                'reference': data.get('reference', ''),
            })

        else:  # visa_mastercard / payfast — Hosted Checkout
            return JsonResponse({
                'success': True,
                'checkout_url': data.get('checkout_url'),
            })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except http_requests.exceptions.Timeout:
        # A nossa ligação caiu, mas isso NÃO significa que a Debito Pay não
        # processou o pagamento (sobretudo no mpesa, que espera o cliente
        # confirmar no telemóvel). Não marcamos o order como 'failed' aqui —
        # fica 'pending' e deve ser reconciliado via webhook ou por uma
        # chamada posterior a action=check-status usando order.paysuite_id.
        logger.warning(f"GATEWAY timeout ao criar pagamento para order {order.ref}")
        return JsonResponse(
            {
                'success': False,
                'error': 'A confirmar o pagamento, isto pode demorar um pouco. Verifique o estado antes de tentar novamente.',
                'status': 'pending',
            },
            status=202,
        )
    except http_requests.RequestException as e:
        return JsonResponse(
            {'success': False, 'error': f'Erro ao contactar gateway de pagamento: {e}'},
            status=502,
        )
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Pedido inválido.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# 3. Página de retorno (após pagamento cartão / PayFast no Hosted Checkout)
# ---------------------------------------------------------------------------

def checkout_return(request):
    """
    A Debito Pay redireciona o cliente aqui após o pagamento (cartão/PayFast),
    devolvendo ?status=success ou ?status=failed na query string.
    A validação real é feita no webhook — esta página apenas agradece.
    """
    return render(request, 'public_site/checkout_return.html')


# ---------------------------------------------------------------------------
# 4. Webhook Debito Pay
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def debitopay_webhook(request):
    """
    Recebe eventos da Debito Pay (payment.completed / payment.failed /
    payment.refunded / payment.chargeback).
    Verifica a assinatura HMAC-SHA256 (header X-Webhook-Signature) antes de
    processar, conforme documentação da Debito Pay.
    """
    if not _verify_debitopay_signature(request):
        logger.warning('WEBHOOK assinatura inválida — pedido rejeitado')
        return HttpResponse('Assinatura inválida.', status=401)

    try:
        event = json.loads(request.body)
        event_type = event.get('event')
        data = event.get('data', {})
        payment_id = data.get('payment_id')

        # Correspondência feita pelo payment_id devolvido na criação do
        # pagamento (guardado em order.paysuite_id) — o campo "reference"
        # do webhook é a referência do provedor, não o order.ref.
        order = Order.objects.get(paysuite_id=payment_id)

        # Idempotência — ignorar se o order já foi pago
        if order.status == 'paid':
            logger.warning(f"WEBHOOK order já processado, ignorado: {payment_id}")
            return HttpResponse('OK', status=200)

        if event_type == 'payment.completed':
            # Marca como pago PRIMEIRO — bloqueia chamadas duplicadas
            updated = Order.objects.filter(
                paysuite_id=payment_id,
                status='pending',  # só actualiza se ainda estiver pendente
            ).update(
                status='paid',
                paysuite_transaction_id=data.get('reference', ''),
            )

            if not updated:
                # Outra chamada paralela já processou — ignorar
                logger.warning(f"WEBHOOK race condition ignorada: {payment_id}")
                return HttpResponse('OK', status=200)

            # Recarrega o order actualizado
            order.refresh_from_db()

            # Cria conta, ClientProfile, ClientPackage e envia email
            activate_client_package(order)

        elif event_type == 'payment.failed':
            Order.objects.filter(paysuite_id=payment_id, status='pending').update(
                status='failed',
            )

        elif event_type in ('payment.refunded', 'payment.chargeback'):
            Order.objects.filter(paysuite_id=payment_id).update(
                status='refunded' if event_type == 'payment.refunded' else 'chargeback',
            )
            logger.warning(f"WEBHOOK {event_type} recebido para order {order.ref}")

        # A Debito Pay exige resposta em menos de 5 segundos
        return HttpResponse('OK', status=200)

    except Order.DoesNotExist:
        return HttpResponse('Referência desconhecida.', status=404)
    except Exception as e:
        return HttpResponse(str(e), status=500)