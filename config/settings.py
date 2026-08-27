from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-tzj(-_+clh3=hw$_oh5dn!57&j9dqh7!fo!!t4e8w_v4od9q(6'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://*.railway.app',
    'http://localhost',
    'http://127.0.0.1',
]


# Application definition

INSTALLED_APPS = [
    "unfold",  # before django.contrib.admin
    "unfold.contrib.filters",  # optional, if special filters are needed
    "unfold.contrib.forms",  # optional, if special form elements are needed
    "unfold.contrib.inlines",  # optional, if special inlines are needed
    "unfold.contrib.import_export",  # optional, if django-import-export package is used
    "unfold.contrib.guardian",  # optional, if django-guardian package is used
    "unfold.contrib.simple_history",  # optional, if django-simple-history package is used
    "unfold.contrib.location_field",  # optional, if django-location-field package is used
    "unfold.contrib.constance",  # optional, if django-constance package is used

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    "rest_framework",
    "rest_framework_simplejwt",


    "apps.accounts.apps.AccountsConfig",
    "apps.workouts.apps.WorkoutsConfig",
    "apps.nutrition.apps.NutritionConfig",
    "apps.packages.apps.PackagesConfig",
    "apps.public_site.apps.PublicSiteConfig",
    "apps.billing.apps.BillingConfig",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/


STATIC_URL = "/static/"

# Pasta onde você coloca seus ficheiros estáticos do projeto
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Pasta onde o Django vai coletar tudo no deploy (collectstatic)
STATIC_ROOT = BASE_DIR / "staticfiles"


AUTH_USER_MODEL = "accounts.User"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"


UNFOLD = {
    "SITE_TITLE": "Can't Stop",

    "SITE_URL": "/",

    # "SITE_LOGO": lambda request: static("logo.svg"),  # both modes, optimise for 32px height
    "SITE_LOGO": {
        "light": lambda request: static("img/01_icon_texto_preto_fundo_transparente.png"),  # light mode
        "dark": lambda request: static("img/01_icon_texto_preto_fundo_transparente.png"),  # dark mode
    },
    "SITE_SYMBOL": "speed",  # symbol from icon set
    "SHOW_HISTORY": True, # show/hide "History" button, default: True
    "SHOW_VIEW_ON_SITE": True, # show/hide "View on site" button, default: True

    "BORDER_RADIUS": "6px",
    "COLORS": {
        "base": {
            "50": "oklch(98.5% .002 90)",
            "100": "oklch(96.7% .003 90)",
            "200": "oklch(92.8% .006 90)",
            "300": "oklch(87.2% .01 90)",
            "400": "oklch(70.7% .015 90)",
            "500": "oklch(55.1% .015 90)",
            "600": "oklch(44.6% .015 90)",
            "700": "oklch(37.3% .015 90)",
            "800": "oklch(27.8% .012 90)",
            "900": "oklch(21% .012 90)",
            "950": "oklch(13% .01 90)"
        },

        "primary": {
            "50": "oklch(97.5% .025 116)",
            "100": "oklch(94.5% .045 116)",
            "200": "oklch(89.5% .075 116)",
            "300": "oklch(84% .115 116)",
            "400": "oklch(81% .145 116)",
            "500": "oklch(79.5% .167 116)",
            "600": "oklch(69% .155 116)",
            "700": "oklch(59% .145 116)",
            "800": "oklch(49% .125 116)",
            "900": "oklch(40% .105 116)",
            "950": "oklch(30% .075 116)"
        },

        "font": {
            "subtle-light": "var(--color-base-500)",
            "subtle-dark": "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark": "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark": "var(--color-base-100)"
        }
    },
    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {
                "en": "🇬🇧",
            },
        },
    },
    "SIDEBAR": {
        "show_search": True,  # Search in applications and models names
        "show_all_applications": False,  # Dropdown with all applications and models
        "navigation": [
            {
                "items": [
                {
                    "title": _("Dashboard"),
                    "icon": "dashboard",  # Supported icon set: https://fonts.google.com/icons
                    "link": reverse_lazy("admin:index"),
                },]
            },
            {
                "title": _("Contas"),
                "separator": True,  # Top border
                "collapsible": True,  # Collapsible group of links
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "people",
                        "link": reverse_lazy("admin:accounts_user_changelist"),
                    },
                ],
            },
            {
                "title": _("Nutri"),
                "separator": False,  # Top border
                "collapsible": True,  # Collapsible group of links
                "items": [
                    {
                        "title": _("Alimento"),
                        "icon": "nutrition",
                        "link": reverse_lazy("admin:nutrition_fooditem_changelist"),
                    },
                    {
                        "title": _("Plano Nutricional"),
                        "icon": "calendar_meal",
                        "link": reverse_lazy("admin:nutrition_nutritionplan_changelist"),
                    },
                    {
                        "title": _("Refeição"),
                        "icon": "hand_meal",
                        "link": reverse_lazy("admin:nutrition_meal_changelist"),
                    },
                    {
                        "title": _("Registro Alimentar"),
                        "icon": "checkbook",
                        "link": reverse_lazy("admin:nutrition_nutritionlog_changelist"),
                    },
                ],
            },
            {
                "title": _("Exercícios"),
                "separator": False,  # Top border
                "collapsible": True,  # Collapsible group of links
                "items": [
                    {
                        "title": _("Grupo Muscular"),
                        "icon": "physical_therapy",
                        "link": reverse_lazy("admin:workouts_musclegroup_changelist"),
                    },
                    {
                        "title": _("Exercício"),
                        "icon": "fitness_center",
                        "link": reverse_lazy("admin:workouts_exercise_changelist"),
                    },
                    {
                        "title": _("Plano de Treino"),
                        "icon": "calendar_month",
                        "link": reverse_lazy("admin:workouts_workoutplan_changelist"),
                    },
                    {
                        "title": _("Dia de Treino"),
                        "icon": "today",
                        "link": reverse_lazy("admin:workouts_workoutday_changelist"),
                    },
                    {
                        "title": _("Registro de Treino"),
                        "icon": "checkbook",
                        "link": reverse_lazy("admin:workouts_workoutlog_changelist"),
                    },
                ],
            },
            {
                "title": _("Pacotes"),
                "separator": False,  # Top border
                "collapsible": True,  # Collapsible group of links
                "items": [
                    {
                        "title": _("Pacote de Coaching"),
                        "icon": "weight",
                        "link": reverse_lazy("admin:packages_coachingpackage_changelist"),
                    },
                    {
                        "title": _("Pacote do Cliente"),
                        "icon": "for_you",
                        "link": reverse_lazy("admin:packages_clientpackage_changelist"),
                    },
                ],
            },
        ],
    },
}


DEBITOPAY_API_KEY = os.environ.get("DEBITOPAY_API_KEY")
DEBITOPAY_MERCHANT_ID = os.environ.get("DEBITOPAY_MERCHANT_ID")
DEBITOPAY_WALLET_CODE = ""
DEBITOPAY_WEBHOOK_SECRET = os.environ.get("DEBITOPAY_WEBHOOK_SECRET")
DEBITOPAY_RETURN_URL = "https://csws.up.railway.app/checkout/obrigado/"
DEBITOPAY_CURRENCY = "MZN"


# Email - Gmail SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'yrnsaraiva.office@gmail.com'
EMAIL_HOST_PASSWORD = 'vooh zqje wmjp cyze'   # App Password, não a password normal
DEFAULT_FROM_EMAIL = 'yrnsaraiva.office@gmail.com'