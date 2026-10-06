from django.urls import path
from . import views

app_name = "public_site"

urlpatterns = [
    path('', views.home, name='home'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/order/', views.create_order, name='create_order'),
    path('checkout/order/<str:ref>/status/', views.order_status, name='order_status'),
    path('checkout/obrigado/', views.checkout_return, name='checkout_return'),
    path('checkout/webhook/', views.imali_webhook, name='imali_webhook'),
]