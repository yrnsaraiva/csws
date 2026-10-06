import json
import uuid
import logging

logger = logging.getLogger(__name__)

import requests as http_requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.db.models import Count
from django.utils import timezone

from apps.packages.models import CoachingPackage, ClientPackage
from apps.billing.models import Order
from apps.billing.activation import activate_client_package
from apps.public_site import imali


def home(request):
    return render(request, "public_site/home.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# 2. Criar encomenda + iniciar pagamento na iMali
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

        if payment_method not in imali.SUPPORTED_METHODS:
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
            # 12 caracteres exactos — exigido pela iMali para partner_transaction_id.
            ref=f'CS{uuid.uuid4().hex[:10].upper()}',
            package=package,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            goal=goal,
            notes=notes,
            amount=package.price,
            status='pending',
        )

        data = imali.create_push_payment(order, payment_method, phone=client_phone)

        # A resposta da iMali a um Push Payment é sempre 'PENDING': a
        # confirmação (sucesso ou falha) só chega depois, por webhook ou
        # por polling via check_status/reconcile_orders.
        order.gateway_transaction_id = data.get('transaction_id', '')
        order.save(update_fields=['gateway_transaction_id'])

        return JsonResponse({
            'success': True,
            'status': 'pending',
            'awaiting_confirmation': True,
            'order_ref': order.ref,
        })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except http_requests.exceptions.Timeout:
        # A nossa ligação caiu, mas isso NÃO significa que a iMali não
        # processou o pedido. order.gateway_transaction_id pode ainda não
        # ter sido guardado neste ponto, por isso a reconciliação
        # posterior tem de usar order.ref (enviado como
        # partner_transaction_id) e não gateway_transaction_id.
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
# 3. Página de retorno (sem rota activa no momento — a iMali não tem um
#    fluxo de checkout alojado/redirect como o cartão tinha na Debito Pay;
#    fica preparada para um futuro Pay-By-Link, que também redireciona).
# ---------------------------------------------------------------------------

def checkout_return(request):
    return render(request, 'public_site/checkout_return.html')


# ---------------------------------------------------------------------------
# 4. Webhook iMali
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def imali_webhook(request):
    if not imali.verify_webhook_signature(request):
        logger.warning('WEBHOOK assinatura inválida — pedido rejeitado')
        return HttpResponse('Assinatura inválida.', status=401)

    try:
        event = json.loads(request.body)
        event_type = event.get('type')
        data = event.get('data', {})
        partner_transaction_id = data.get('partner_transaction_id')

        if not partner_transaction_id:
            return HttpResponse('partner_transaction_id em falta.', status=400)

        order = Order.objects.filter(ref=partner_transaction_id).first()
        if order is None:
            return HttpResponse('Referência desconhecida.', status=404)

        transaction_id = data.get('transaction_id')
        if transaction_id and order.gateway_transaction_id != transaction_id:
            order.gateway_transaction_id = transaction_id
            order.save(update_fields=['gateway_transaction_id'])

        if event_type == 'PAYMENT.SUCCESS':
            updated = Order.objects.filter(pk=order.pk, status='pending').update(
                status='paid',
            )

            if not updated:
                # Já estava 'paid' (retry do webhook) ou noutro estado —
                # em qualquer dos casos não há nada mais a fazer aqui.
                logger.warning(f"WEBHOOK order já processado ou em estado inesperado: {order.ref}")
                return HttpResponse('OK', status=200)

            order.refresh_from_db()

            # O order já está 'paid' neste ponto. Se activate_client_package
            # falhar a meio (ex.: email), respondemos 200 à iMali na mesma —
            # devolver erro aqui só provoca retries do webhook que a
            # idempotência acima (status == 'paid') vai ignorar sem nunca
            # voltar a tentar a activação.
            _activate_client_package_safe(order, context='webhook/PAYMENT.SUCCESS')

        elif event_type == 'PAYMENT.FAILED':
            Order.objects.filter(pk=order.pk, status='pending').update(
                status='failed',
            )
            reason = data.get('status_reason', '')
            logger.warning(f"WEBHOOK pagamento falhado para order {order.ref}: {reason}")

        # PAYMENT.PENDING não exige nenhuma ação — a encomenda já é criada
        # como 'pending'. A iMali não tem (nesta versão da API) eventos de
        # webhook para reembolsos/chargebacks; esses são tratados
        # manualmente na admin (ação "Marcar como reembolsada").

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