from django.urls import path
from . import views

app_name = "public_site"

urlpatterns = [
    path('', views.home, name='home'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/order/', views.create_order, name='create_order'),
    path('checkout/obrigado/', views.checkout_return, name='checkout_return'),
    path('checkout/webhook/', views.debitopay_webhook, name='debitopay_webhook'),
]