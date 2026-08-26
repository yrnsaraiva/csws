from django.contrib import admin
from django.utils.html import format_html
from .models import Order, Invoice
from unfold.admin import ModelAdmin, TabularInline


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        'ref',
        'client_name',
        'package',
        'amount',
        'status_badge',
        'created_at',
    )

    list_filter = (
        'status',
        'created_at',
        'package',
    )

    search_fields = (
        'ref',
        'client_name',
        'client_email',
        'client_phone',
        'paysuite_transaction_id',
    )

    readonly_fields = (
        'ref',
        'paysuite_id',
        'paysuite_transaction_id',
        'created_at',
        'updated_at',
    )

    autocomplete_fields = ('package',)

    ordering = ('-created_at',)

    fieldsets = (
        ('Informações da Encomenda', {
            'fields': (
                'ref',
                'package',
                'amount',
                'status',
            )
        }),

        ('Cliente', {
            'fields': (
                'client_name',
                'client_email',
                'client_phone',
                'goal',
                'notes',
            )
        }),

        ('PaySuite', {
            'fields': (
                'paysuite_id',
                'paysuite_transaction_id',
            )
        }),

        ('Datas', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'paid': '#22c55e',
            'failed': '#ef4444',
            'refunded': '#60a5fa',
        }

        color = colors.get(obj.status, '#9ca3af')

        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color,
            obj.get_status_display()
        )

    status_badge.short_description = 'Estado'


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = (
        'invoice_number',
        'order',
        'issued_at',
        'pdf_status',
    )

    search_fields = (
        'invoice_number',
        'order__ref',
        'order__client_name',
    )

    readonly_fields = (
        'issued_at',
    )

    ordering = ('-issued_at',)

    autocomplete_fields = ('order',)

    def pdf_status(self, obj):
        if obj.pdf_file:
            return format_html(
                '<span style="color:{}; font-weight:600;">{}</span>',
                '#22c55e',
                'PDF Disponível'
            )

        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            '#ef4444',
            'Sem PDF'
        )

    pdf_status.short_description = 'PDF'