"""
Corre este ficheiro directamente no terminal do PyCharm:
  python tests/test_paysuite.py

Nao precisa de Django settings configuradas.
"""
import requests

API_KEY = "1963|Dnq1dYwUZ9xsBG7DSClhtyNTK00ZkiGCyRkvms31a73c272f"   # <-- substitui
RETURN_URL = "https://jonia.up.railway.app/checkout/obrigado/"
WEBHOOK_URL = "https://jonia.up.railway.app/checkout/webhook/"

payload = {
    "amount": 149.0,
    "reference": "JNA4F2BC",
    "description": "Jonia - Pack Iniciante 30d",
    "return_url": RETURN_URL,
    "callback_url": WEBHOOK_URL,
}

r = requests.post(
    "https://paysuite.tech/api/v1/payments",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    json=payload,
    timeout=10,
)

print(f"Status: {r.status_code}")
print(f"Body:   {r.text}")