"""
Cliente da API da iMali.Way (Paytek) — gateway de pagamentos M-Pesa / e-Mola /
mKesh / conta iMali, usado no checkout público.

Documentação: "iMali Payment Gateway API — Partner Integration" v1.4a.
"""
import base64
import hashlib
import hmac
import logging
import time

import requests as http_requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.conf import settings

logger = logging.getLogger(__name__)

MOBILE_MONEY_METHODS = {'mpesa', 'emola', 'mkesh'}
SUPPORTED_METHODS = MOBILE_MONEY_METHODS | {'imali'}

REQUEST_TIMEOUT = 30


def _private_key():
    """
    Gera o token de autenticação ("privateKey") exigido pela iMali:
    encripta o api_key com a publicKey fornecida, usando RSA-ES-PKCS1
    (RSAES-PKCS1-v1_5), e devolve o resultado em base64.

    É gerado a cada pedido (a encriptação RSA-PKCS1v1.5 usa padding
    aleatório, por isso o valor nunca é igual duas vezes — não há nada
    para cachear).
    """
    public_key = load_pem_public_key(settings.IMALI_PUBLIC_KEY.encode('utf-8'))
    ciphertext = public_key.encrypt(
        settings.IMALI_API_KEY.encode('utf-8'),
        padding.PKCS1v15(),
    )
    return base64.b64encode(ciphertext).decode('ascii')


def _headers():
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_private_key()}',
        'X-Client-ID': settings.IMALI_CLIENT_ID,
    }


def create_push_payment(order, payment_method, phone):
    """
    Cria um pedido de pagamento Push (C2B) — a iMali envia um pedido de
    confirmação para o telemóvel do cliente. A resposta inicial é sempre
    'PENDING': a confirmação chega depois por webhook (ou por polling via
    check_status).
    """
    if payment_method not in SUPPORTED_METHODS:
        raise ValueError(f'Método de pagamento não suportado: {payment_method}')

    payload = {
        'client_account_number': phone,
        'amount': float(order.amount),
        'store_account_number': settings.IMALI_STORE_ACCOUNT_NUMBER,
        'partner_transaction_id': order.ref,
        'payment_method': payment_method,
        'payment_type': 'push',
        'transaction_type': 'C2B',
    }

    response = http_requests.post(
        f'{settings.IMALI_BASE_URL}/payments',
        headers=_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    if 'errors' in data:
        raise http_requests.RequestException(str(data['errors']))

    return data.get('data', data)


def check_status(partner_transaction_id, payment_type='push'):
    """
    Consulta o estado real de um pagamento na iMali (usado pelo comando
    reconcile_orders para encomendas 'pending' há muito tempo).

    Devolve o dict de 'data' da resposta (inclui 'status': PENDING / SUCCESS
    / FAILED / EXPIRED).
    """
    payload = {
        'partner_transaction_id': partner_transaction_id,
        'payment_type': payment_type,
    }

    response = http_requests.request(
        'GET',
        f'{settings.IMALI_BASE_URL}/payments/status',
        headers=_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get('data', {})


def verify_webhook_signature(request):
    """
    Valida a assinatura HMAC-SHA256 (X-Webhook-Signature, formato
    "sha256=<hex>") e rejeita pedidos com timestamp (X-Webhook-Timestamp)
    com mais de 5 minutos, para prevenir replay attacks.
    """
    signature_header = request.headers.get('X-Webhook-Signature', '')
    timestamp = request.headers.get('X-Webhook-Timestamp', '')

    if not signature_header or not timestamp:
        return False

    received_signature = signature_header.removeprefix('sha256=')

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - timestamp_int) > 300:
        logger.warning('WEBHOOK timestamp fora da janela de 5 minutos — possível replay')
        return False

    signed_payload = f'{timestamp}.'.encode('utf-8') + request.body
    expected_signature = hmac.new(
        settings.IMALI_WEBHOOK_SECRET.encode('utf-8'),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, received_signature)
