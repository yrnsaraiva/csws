from django.contrib import admin, messages
from django.utils.html import format_html
from .models import Order, Invoice
from .activation import activate_client_package
from unfold.admin import ModelAdmin, TabularInline


class SemAcessoFilter(admin.SimpleListFilter):
    title = 'acesso'
    parameter_name = 'acesso'

    def lookups(self, request, model_admin):
        return [('sem_acesso', 'Pagas sem acesso criado')]

    def queryset(self, request, queryset):
        if self.value() == 'sem_acesso':
            return queryset.filter(status='paid', client_package__isnull=True)
        return queryset


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
        SemAcessoFilter,
        'created_at',
        'package',
    )

    actions = ['ativar_acesso', 'marcar_reembolsada']

    @admin.action(description='Ativar acesso (cria ClientPackage para encomendas pagas sem acesso)')
    def ativar_acesso(self, request, queryset):
        alvo = queryset.filter(status='paid', client_package__isnull=True)
        sucesso = 0
        for order in alvo:
            try:
                activate_client_package(order)
                sucesso += 1
            except Exception as e:
                self.message_user(
                    request, f'Falhou para {order.ref}: {e}', level=messages.ERROR
                )
        if sucesso:
            self.message_user(
                request, f'Acesso ativado para {sucesso} encomenda(s).', level=messages.SUCCESS
            )

    @admin.action(description='Marcar como reembolsada (cancela o acesso)')
    def marcar_reembolsada(self, request, queryset):
        """
        A iMali não tem (nesta versão da API) um evento de webhook para
        reembolsos/chargebacks — ao contrário da Debito Pay, um reembolso
        feito manualmente (ex.: B2C transfer) não chega a notificar a app.
        Esta ação cobre esse caso: usar depois de reembolsar o cliente.
        """
        alvo = list(queryset.filter(status='paid').select_related('client_package'))
        count = len(alvo)
        for order in alvo:
            order.status = 'refunded'
            order.save(update_fields=['status'])
            cp = getattr(order, 'client_package', None)
            if cp and cp.status == 'active':
                cp.status = 'cancelled'
                cp.save(update_fields=['status'])
        if count:
            self.message_user(
                request, f'{count} encomenda(s) marcada(s) como reembolsada(s) e acesso cancelado.',
                level=messages.SUCCESS,
            )

    search_fields = (
        'ref',
        'client_name',
        'client_email',
        'client_phone',
        'gateway_reference',
    )

    readonly_fields = (
        'ref',
        'gateway_transaction_id',
        'gateway_reference',
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

        ('Gateway de Pagamento', {
            'fields': (
                'gateway_transaction_id',
                'gateway_reference',
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
            'chargeback': '#a855f7',
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