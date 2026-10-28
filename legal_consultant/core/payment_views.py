import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .account_history import owned_records
from .models import HelpOrder, PlategaAttempt
from . import platega


def materials_ready(order):
    if order.summary.get('service_code') in ('consultation', 'plan'):
        return bool(order.private_text.strip())
    if order.summary.get('service_code') == 'documents':
        from .help_views import _order_conclusion
        result = _order_conclusion(order)
        if result:
            return any(d.docx_file and d.pdf_file and d.docx_file.storage.exists(d.docx_file.name)
                       and d.pdf_file.storage.exists(d.pdf_file.name)
                       for d in result.download_documents.filter(is_active=True))
    return False


@never_cache
@require_POST
def pay_order(request, order_id):
    if not request.user.is_authenticated:
        return redirect('core:account_login')
    order = get_object_or_404(owned_records(HelpOrder, request), pk=order_id)
    try:
        if not materials_ready(order):
            raise platega.PaymentError('Материалы услуги ещё не готовы. Оплата недоступна.')
        return redirect(platega.create_checkout(order))
    except platega.PaymentError as exc:
        messages.error(request, str(exc))
        return redirect('core:help_order', order_id=order.pk)


@never_cache
@require_POST
def check_payment(request, order_id):
    if not request.user.is_authenticated:
        return redirect('core:account_login')
    order = get_object_or_404(owned_records(HelpOrder, request), pk=order_id)
    attempt = order.platega_attempts.exclude(transaction_id=None).order_by('-created_at').first()
    try:
        if attempt:
            platega.refresh(attempt)
            messages.info(request, 'Статус платежа проверен.')
        else:
            messages.info(request, 'Платёж пока не создан или ожидает проверки поддержки.')
    except platega.PaymentError as exc:
        messages.error(request, str(exc))
    return redirect('core:help_order', order_id=order.pk)


@csrf_exempt
@require_POST
def platega_callback(request):
    if not platega.configured():
        return HttpResponse(status=503)
    if not (constant_time_compare(request.headers.get('X-MerchantId', ''), platega.config('PLATEGA_MERCHANT_ID'))
            and constant_time_compare(request.headers.get('X-Secret', ''), platega.config('PLATEGA_SECRET'))):
        return HttpResponse(status=403)
    if len(request.body) > 16000:
        return HttpResponseBadRequest()
    try:
        data = json.loads(request.body)
        provider_id = UUID(data['id'])
        amount = Decimal(str(data['amount']))
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return HttpResponseBadRequest()
    attempt = PlategaAttempt.objects.select_related('order').filter(transaction_id=provider_id).first()
    if not attempt:
        return HttpResponse(status=409)  # Retry if callback raced creation persistence.
    if not amount.is_finite() or amount != attempt.order.amount or data.get('currency') != 'RUB':
        return HttpResponseBadRequest()
    try:
        platega.refresh(attempt)  # Authoritative API lookup, never trust browser return/status.
    except platega.PaymentError:
        return HttpResponse(status=503)
    return HttpResponse(status=200)
