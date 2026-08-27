import secrets
import string
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

from apps.accounts.models import ClientProfile
from apps.packages.models import ClientPackage

User = get_user_model()


def _generate_password(length=12):
    """Gera uma password aleatória segura."""
    chars = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(secrets.choice(chars) for _ in range(length))


def _derive_username(email):
    """
    Deriva um username único a partir do email.
    ex: yuran.saraiva@gmail.com → yuransaraiva, yuransaraiva2, ...
    """
    base = email.split('@')[0].replace('.', '').replace('-', '').replace('_', '').lower()
    username = base
    counter = 2
    while User.objects.filter(username=username).exists():
        username = f'{base}{counter}'
        counter += 1
    return username


def activate_client_package(order):
    """
    Chamado pelo webhook após payment.success.

    1. Cria (ou recupera) o User com o email do cliente
    2. Cria o ClientProfile se não existir
    3. Cria o ClientPackage ligado ao pacote comprado
    4. Envia email com credenciais de acesso

    Retorna o User criado/encontrado.
    """
    coach = User.objects.filter(role='coach').first()

    # ── 1. User ──────────────────────────────────────────────────────────────
    user, created = User.objects.get_or_create(
        email=order.client_email,
        defaults={
            'username':   _derive_username(order.client_email),
            'first_name': order.client_name.split()[0],
            'last_name':  ' '.join(order.client_name.split()[1:]),
            'phone':      order.client_phone,
            'role':       'client',
            'is_active':  True,
            'coach':      coach,
        }
    )

    # Se o user já existia (re-compra), apenas garante que está activo
    if not created:
        user.is_active = True
        if coach and not user.coach:
            user.coach = coach
        user.save(update_fields=['is_active', 'coach'])

    # ── 2. Password (só para contas novas) ───────────────────────────────────
    raw_password = None
    if created:
        raw_password = _generate_password()
        user.set_password(raw_password)
        user.save(update_fields=['password'])

    # ── 3. ClientProfile ─────────────────────────────────────────────────────
    ClientProfile.objects.get_or_create(
        user=user,
        defaults={
            'goal':  order.goal,
            'notes': order.notes,
        }
    )

    # ── 4. ClientPackage ─────────────────────────────────────────────────────
    start_date = date.today()
    end_date = start_date + timedelta(days=order.package.duration_days)

    ClientPackage.objects.create(
        client=user,
        package=order.package,
        status='active',
        start_date=start_date,
        end_date=end_date,
        assigned_by=coach,
    )

    # ── 5. Email de boas-vindas ───────────────────────────────────────────────
    import logging
    logger = logging.getLogger(__name__)
    try:
        _send_welcome_email(user, order, raw_password)
        logger.warning(f"EMAIL enviado para {user.email}")
    except Exception as e:
        logger.error(f"EMAIL FALHOU para {user.email}: {e}")

    return user


def _send_welcome_email(user, order, raw_password=None):
    """
    Envia email com credenciais de acesso (conta nova) ou confirmação (re-compra).
    """
    app_url = getattr(settings, 'APP_URL', 'https://app.cantstop.co.mz')

    if raw_password:
        subject = f'Bem-vindo(a) à can\'t stop, {user.first_name}!'
        message = f"""Olá {user.first_name},

O seu pagamento foi confirmado e a sua conta foi criada com sucesso!

Pacote: {order.package.name}
Validade: {order.package.duration_days} dias

Acesse o app com as seguintes credenciais:
  URL:      {app_url}
  Email:    {user.email}
  Password: {raw_password}

Recomendamos que altere a password após o primeiro login.

O coach entrará em contacto em breve para dar início ao seu plano.

Equipa Jonia
"""
    else:
        subject = f'Renovação confirmada, {user.first_name}!'
        message = f"""Olá {user.first_name},

A renovação do seu pacote foi confirmada!

Pacote: {order.package.name}
Validade: {order.package.duration_days} dias adicionais

Continue a aceder ao app com as suas credenciais habituais:
  URL: {app_url}

Equipa can't stop
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@cantstop.co.mz'),
        recipient_list=[user.email],
        fail_silently=False,
    )
