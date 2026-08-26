from django.db import models
from apps.packages.models import *


# apps/billing/models.py
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('paid', 'Pago'),
        ('failed', 'Falhado'),
        ('refunded', 'Reembolsado'),
    ]

    PAY_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('emola', 'e-Mola'),
        ('credit_card', 'Cartão de Crédito/Débito'),
    ]

    # Dados da encomenda
    ref = models.CharField(max_length=20, unique=True, editable=False)
    package = models.ForeignKey(CoachingPackage, on_delete=models.PROTECT, related_name='orders')
    client_name = models.CharField(max_length=150)
    client_email = models.EmailField()
    client_phone = models.CharField(max_length=25)
    goal = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Campos PaySuite (preenchidos após criar o payment request)
    paysuite_id = models.CharField(max_length=100, blank=True)
    paysuite_transaction_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Encomenda'
        verbose_name_plural = 'Encomendas'

    def __str__(self):
        return f'{self.ref} — {self.client_name} ({self.get_status_display()})'


class Invoice(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=50, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True)
