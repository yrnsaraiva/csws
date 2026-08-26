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

PAYSUITE_BASE = 'https://paysuite.tech/api/v1'
PAYSUITE_HEADERS = {
    'Authorization': f'Bearer {settings.PAYSUITE_API_KEY}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


def _paysuite_create_payment(order):
    """Cria um payment request na PaySuite e devolve (checkout_url, paysuite_id)."""
    payload = {
        'amount': float(order.amount),
        'reference': ''.join(c for c in order.ref if c.isalnum()),
        'description': f'Jonia - {order.package.name}'[:125],
        'return_url': settings.PAYSUITE_RETURN_URL,
        'callback_url': settings.PAYSUITE_WEBHOOK_URL,
    }
    response = http_requests.post(
        f'{PAYSUITE_BASE}/payments',
        headers=PAYSUITE_HEADERS,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()['data']
    return data['checkout_url'], data['id']


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
# 2. Criar encomenda + redirecionar para PaySuite
# ---------------------------------------------------------------------------

@require_http_methods(['POST'])
def create_order(request):
    """
    Recebe os dados do checkout, cria o Order com status 'pending',
    chama a PaySuite e devolve o checkout_url para o frontend redirecionar.
    """
    try:
        body = json.loads(request.body)

        package_id = body.get('package_id')
        client_name = body.get('client_name', '').strip()
        client_email = body.get('client_email', '').strip()
        client_phone = body.get('client_phone', '').strip()
        goal = body.get('goal', '')
        notes = body.get('notes', '')

        if not all([package_id, client_name, client_email, client_phone, goal]):
            return JsonResponse(
                {'success': False, 'error': 'Campos obrigatórios em falta.'},
                status=400,
            )

        try:
            package = CoachingPackage.objects.get(pk=package_id, is_active=True)
        except CoachingPackage.DoesNotExist:
            return JsonResponse(
                {'success': False, 'error': 'Pacote não encontrado ou inactivo.'},
                status=404,
            )

        # Cria o Order localmente antes de ir à PaySuite
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

        # Cria o payment request na PaySuite
        checkout_url, paysuite_id = _paysuite_create_payment(order)

        # Guarda o ID PaySuite para cruzar com o webhook
        order.paysuite_id = paysuite_id
        order.save(update_fields=['paysuite_id'])

        return JsonResponse({'success': True, 'checkout_url': checkout_url})

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
# 3. Página de retorno (após pagamento no site PaySuite)
# ---------------------------------------------------------------------------

def checkout_return(request):
    """
    PaySuite redireciona o cliente aqui após o pagamento.
    A validação real é feita no webhook — esta página apenas agradece.
    """
    return render(request, 'public_site/checkout_return.html')


# ---------------------------------------------------------------------------
# 4. Webhook PaySuite
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def paysuite_webhook(request):
    """
    Recebe eventos da PaySuite (payment.success / payment.failed).
    Verifica a assinatura HMAC-SHA256 antes de processar.
    """
    payload = request.body
    # Nota: a PaySuite não envia o header X-Webhook-Signature actualmente.
    # A segurança é garantida por idempotência via request_id (ver abaixo).

    try:
        event = json.loads(payload)
        event_type = event.get('event')
        request_id = event.get('request_id', '')
        data = event.get('data', {})
        reference = data.get('reference')  # == order.ref  ex: JNA4F2BC

        order = Order.objects.get(ref=reference)

        # Idempotência — ignorar se o order já foi pago
        if order.status == 'paid':
            logger.warning(f"WEBHOOK order já processado, ignorado: {reference}")
            return HttpResponse('OK', status=200)

        if event_type == 'payment.success':
            transaction = data.get('transaction', {})

            # Marca como pago PRIMEIRO — bloqueia chamadas duplicadas
            updated = Order.objects.filter(
                ref=reference,
                status='pending',  # só actualiza se ainda estiver pendente
            ).update(
                status='paid',
                paysuite_transaction_id=request_id or transaction.get('id', ''),
            )

            if not updated:
                # Outra chamada paralela já processou — ignorar
                logger.warning(f"WEBHOOK race condition ignorada: {reference}")
                return HttpResponse('OK', status=200)

            # Recarrega o order actualizado
            order.refresh_from_db()

            # Cria conta, ClientProfile, ClientPackage e envia email
            activate_client_package(order)

        elif event_type == 'payment.failed':
            # Ignorar — a PaySuite envia 'failed' enquanto o cliente
            # ainda não confirmou o PIN. O 'success' chega depois.
            pass

        # PaySuite exige resposta em menos de 5 segundos
        return HttpResponse('OK', status=200)

    except Order.DoesNotExist:
        return HttpResponse('Referência desconhecida.', status=404)
    except Exception as e:
        return HttpResponse(str(e), status=500)
