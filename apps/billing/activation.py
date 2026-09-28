from datetime import timedelta
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import ClientProfile
from apps.packages.models import ClientPackage

User = get_user_model()


def _build_set_password_url(user):
    """
    Gera o link único de "definir password" (mesmo mecanismo do
    'esqueci-me da password'), válido por PASSWORD_RESET_TIMEOUT.
    """
    app_url = getattr(settings, 'APP_URL', 'https://cantstopwontstop.lt/app/')
    base = urlsplit(app_url)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
    return f'{base.scheme}://{base.netloc}{path}'


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
    coach = order.package.coach

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
    # Sem password gerada: a conta fica sem password utilizável até o
    # cliente definir a sua própria através do link enviado por email.
    if created:
        user.set_unusable_password()
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
    start_date = timezone.localdate()
    end_date = start_date + timedelta(days=order.package.duration_days)

    ClientPackage.objects.create(
        client=user,
        package=order.package,
        order=order,
        status='active',
        start_date=start_date,
        end_date=end_date,
        assigned_by=coach,
    )

    # ── 5. Email de boas-vindas ───────────────────────────────────────────────
    import logging
    logger = logging.getLogger(__name__)
    try:
        _send_welcome_email(user, order, is_new_account=created)
        logger.warning(f"EMAIL enviado para {user.email}")
    except Exception as e:
        logger.error(f"EMAIL FALHOU para {user.email}: {e}")

    return user


def _send_welcome_email(user, order, is_new_account):
    """
    Envia email de boas-vindas com link para definir password (conta nova)
    ou confirmação de renovação (re-compra). HTML com fallback em texto simples.
    """
    app_url = getattr(settings, 'APP_URL', 'https://cantstopwontstop.lt/app/')

    context = {
        'user': user,
        'order': order,
        'app_url': app_url,
    }

    if is_new_account:
        subject = f"Bem-vindo(a) à can't stop, {user.first_name}!"
        context['set_password_url'] = _build_set_password_url(user)
        text_template = 'billing/email/welcome_email.txt'
        html_template = 'billing/email/welcome_email.html'
    else:
        subject = f'Renovação confirmada, {user.first_name}!'
        text_template = 'billing/email/renewal_email.txt'
        html_template = 'billing/email/renewal_email.html'

    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'geral@cantstopwontstop.lt'),
        to=[user.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)
