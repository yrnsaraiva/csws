# Can't Stop Won't Stop

App de coaching (treino + nutrição) com checkout online. Django no backend,
templates server-side no site público e na área de membros, pagamentos via
iMali.Way / Paytek (M-Pesa / e-Mola / mKesh), deploy no Railway.

## Stack

- Python 3.12, Django 6.0
- PostgreSQL em produção, SQLite em desenvolvimento (`DEBUG=1`)
- WhiteNoise para ficheiros estáticos
- django-storages (S3-compatível, para Cloudflare R2) para ficheiros enviados via admin
- iMali.Way (Paytek) como gateway de pagamento (M-Pesa / e-Mola / mKesh)

## Correr localmente

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # ver secção "Variáveis de ambiente" abaixo
# preencher pelo menos DJANGO_SECRET_KEY

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Com `DEBUG=1` a app usa SQLite (`db.sqlite3`, não versionado) e não precisa
de `DATABASE_URL`. As variáveis são lidas de um ficheiro `.env` na raiz do
projeto (via `python-dotenv`) se existir, ou do ambiente.

### Testes

```bash
DEBUG=1 python manage.py test
```

O CI (`.github/workflows/tests.yml`) corre os testes contra PostgreSQL a
cada push/PR.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Sim | Chave secreta do Django. Sem valor por omissão — a app não arranca sem ela. |
| `DEBUG` | Não (default `0`) | `1` para desenvolvimento (SQLite, hosts extra permitidos). Nunca `1` em produção. |
| `ALLOWED_HOSTS` | Não | Lista separada por vírgulas. Default: `cantstopwontstop.lt,www.cantstopwontstop.lt`. |
| `DATABASE_URL` | Sim quando `DEBUG=0` | Connection string do PostgreSQL (formato `postgresql://user:pass@host:port/db`). |
| `SECURE_SSL_REDIRECT` | Não (default `1` quando `DEBUG=0`) | Só existe para desligar o redirect HTTPS em ambientes sem TLS (ex.: CI). Não mexer em produção. |
| `APP_URL` | Não | URL pública da área de membros, usada nos emails. Default `https://cantstopwontstop.lt/app/`. |
| `IMALI_API_KEY` | Sim em produção | `api_key` do parceiro, fornecido pela Paytek. |
| `IMALI_PUBLIC_KEY` | Sim em produção | Chave pública RSA (PEM) fornecida pela Paytek, usada para gerar o token de autenticação de cada pedido. |
| `IMALI_CLIENT_ID` | Sim em produção | `client_id` do parceiro (header `X-Client-ID`). |
| `IMALI_WEBHOOK_SECRET` | Sim em produção | Segredo para validar a assinatura HMAC dos webhooks da iMali. |
| `IMALI_STORE_ACCOUNT_NUMBER` | Sim em produção | Conta iMali da loja para a qual os pagamentos do checkout são dirigidos. A empresa tem mais do que uma Store Account Number atribuída — confirmar no dashboard iMali qual corresponde ao canal do site antes de ir para produção. |
| `EMAIL_HOST_PASSWORD` | Sim em produção | Password (app password) da caixa `geral@cantstopwontstop.lt` na Hostinger. |
| `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL` | Não | Credenciais do Cloudflare R2. Sem elas, ficheiros carregados via admin ficam no disco local (perdem-se a cada deploy no Railway). |
| `R2_PUBLIC_DOMAIN` | Não | Domínio público do bucket R2, se configurado. |
| `R2_REGION` | Não (default `auto`) | Região S3 a usar no cliente do R2. |

**Nunca** commitar um `.env` com valores reais — está no `.gitignore`. Se
algum destes segredos foi exposto (ex.: num repositório público), rodar
imediatamente nos respetivos painéis (Paytek/iMali, Hostinger, Railway,
Cloudflare).

## Deploy (Railway)

- `Procfile`:
  - `release`: corre `migrate` e `collectstatic` antes de cada deploy.
  - `web`: `gunicorn`.
- Dois comandos de manutenção que devem correr num serviço cron separado no
  Railway (não incluídos no `Procfile` porque não são processos web):
  - `python manage.py expire_packages` — diariamente (ex.: `15 0 * * *`).
  - `python manage.py reconcile_orders` — a cada poucos minutos (ex.:
    `*/5 * * * *`), para apanhar encomendas que ficaram `pending` por um
    timeout na chamada à iMali ou um webhook perdido.

## Estrutura

```
apps/
  accounts/     autenticação, dashboard, perfil
  billing/      encomendas, faturas, ativação de acesso pós-pagamento
  packages/     pacotes de coaching, atribuição a clientes
  workouts/     planos e sessões de treino
  nutrition/    planos alimentares e registos
  public_site/  site público, checkout, webhook da iMali
config/         settings, urls, wsgi/asgi
templates/      templates por app + `templates/accounts/email/`, `templates/billing/email/`
```
