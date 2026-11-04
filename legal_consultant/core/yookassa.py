"""YooKassa redirect checkout. All confirmations are verified against the API."""
import base64
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import UUID

from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import HelpOrder, OrderPayment, PlategaAttempt, YooKassaAttempt
from .platega import config, PaymentError


def configured():
    return bool(config('YOOKASSA_SHOP_ID') and config('YOOKASSA_SECRET_KEY'))


def enabled():
    receipts_ready = (str(config('YOOKASSA_RECEIPTS', '0')) == '1' and str(config('YOOKASSA_VAT_CODE')).isdigit()) or str(config('YOOKASSA_RECEIPTS_EXTERNAL', '0')) == '1'
    return configured() and str(config('YOOKASSA_ENABLED', '0')) == '1' and receipts_ready


def api(method, path, payload=None, idempotence=None):
    if not configured():
        raise PaymentError('Приём оплаты пока не настроен.')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    authorization = base64.b64encode((str(config('YOOKASSA_SHOP_ID')) + ':' + config('YOOKASSA_SECRET_KEY')).encode()).decode()
    headers = {'Authorization': 'Basic ' + authorization, 'Content-Type': 'application/json'}
    if idempotence:
        headers['Idempotence-Key'] = str(idempotence)
    request = Request('https://api.yookassa.ru/v3' + path, method=method, headers=headers,
                      data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            raw = response.read(100001)
            if response.status != 200 or len(raw) > 100000:
                raise ValueError
        data = json.loads(raw, parse_float=Decimal)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (URLError, OSError, ValueError):
        raise PaymentError('ЮKassa временно не отвечает. Проверьте оплату позже.') from None


def safe_checkout(url):
    if not isinstance(url, str) or len(url) > 1000 or any(ord(c) < 33 for c in url):
        return False
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname in ('yoomoney.ru', 'yookassa.ru')
                and p.port in (None, 443) and not p.username and not p.password)
    except ValueError:
        return False


def payload(order, attempt_id):
    data = {'amount': {'value': format(order.amount, '.2f'), 'currency': 'RUB'}, 'capture': True,
            'confirmation': {'type': 'redirect', 'return_url': 'https://www.k-urist.ru/help/orders/' + str(order.pk) + '/'},
            'description': 'Карманный юрист. Заказ ' + str(order.pk),
            'metadata': {'order_id': str(order.pk), 'attempt_id': str(attempt_id)}}
    # Tax values must be supplied by the merchant, never inferred by the application.
    if str(config('YOOKASSA_RECEIPTS', '0')) == '1':
        try:
            vat = int(config('YOOKASSA_VAT_CODE'))
            if vat not in range(1, 13):
                raise ValueError
        except (ValueError, TypeError):
            raise PaymentError('Для оплаты необходимо настроить данные чека.') from None
        data['receipt'] = {'customer': {'email': order.email}, 'items': [{
            'description': order.summary.get('title', 'Юридическая услуга')[:128], 'quantity': '1.00',
            'amount': data['amount'], 'vat_code': vat, 'payment_subject': 'service', 'payment_mode': 'full_payment'}]}
        tax_system = str(config('YOOKASSA_TAX_SYSTEM_CODE'))
        if tax_system:
            if tax_system not in ('1', '2', '3', '4', '5', '6'):
                raise PaymentError('Проверьте систему налогообложения для чека.')
            data['receipt']['tax_system_code'] = int(tax_system)
    elif str(config('YOOKASSA_RECEIPTS_EXTERNAL', '0')) != '1':
        raise PaymentError('Приём оплаты ожидает настройки чеков.')
    return data


def create_checkout(order):
    if not enabled() or not order.user_id or order.amount <= 0:
        raise PaymentError('Оплата сейчас недоступна. Войдите в аккаунт и проверьте заказ.')
    with transaction.atomic():
        HelpOrder.objects.select_for_update().get(pk=order.pk)
        if OrderPayment.objects.filter(order=order).exists() or PlategaAttempt.objects.filter(order=order, active=True).exists():
            raise PaymentError('По этому заказу уже есть платёж. Проверьте его статус.')
        attempt, _ = YooKassaAttempt.objects.get_or_create(order=order, active=True)
        if not attempt.request_payload:
            attempt.request_payload = payload(order, attempt.pk)
            attempt.save(update_fields=['request_payload'])
    if attempt.payment_id:
        refresh(attempt)
        attempt.refresh_from_db()
        if attempt.status == 'pending' and safe_checkout(attempt.checkout_url):
            return attempt.checkout_url
        raise PaymentError('Статус оплаты обновлён. Если платёж отменён, можно оформить новую попытку.')
    # The same payload and key can be safely retried only within YooKassa's 24h window.
    if timezone.now() - attempt.created_at >= timedelta(hours=23):
        raise PaymentError('Неизвестный статус платежа. Требуется проверка поддержки по номеру заказа.')
    try:
        data = api('POST', '/payments', attempt.request_payload, attempt.pk)
        payment_id = UUID(str(data['id']))
        validate_payment(attempt, data, payment_id)
        status = data.get('status')
        url = data.get('confirmation', {}).get('confirmation_url', '')
        if status not in ('pending', 'succeeded', 'canceled', 'waiting_for_capture') or (status == 'pending' and not safe_checkout(url)):
            raise ValueError
        with transaction.atomic():
            locked = YooKassaAttempt.objects.select_for_update().get(pk=attempt.pk)
            if locked.payment_id and locked.payment_id != payment_id:
                raise ValueError
            locked.payment_id, locked.checkout_url, locked.status = payment_id, url if safe_checkout(url) else '', status
            locked.save(update_fields=['payment_id', 'checkout_url', 'status'])
    except (PaymentError, ValueError, KeyError, TypeError, AttributeError, IntegrityError):
        YooKassaAttempt.objects.filter(pk=attempt.pk, payment_id=None).update(status='unknown')
        raise PaymentError('Создание платежа пока не подтверждено. Повторите проверку: новая попытка использует тот же номер платежа.') from None
    if status == 'pending':
        return url
    refresh(locked)
    raise PaymentError('Статус платежа обновлён. Проверьте ваш заказ.')


def validate_payment(attempt, data, payment_id):
    try:
        amount = Decimal(str(data['amount']['value']))
        valid = (UUID(str(data['id'])) == payment_id and amount.is_finite() and amount == attempt.order.amount
                 and data['amount']['currency'] == 'RUB'
                 and str(data['recipient']['account_id']) == str(config('YOOKASSA_SHOP_ID'))
                 and data['metadata']['order_id'] == str(attempt.order_id)
                 and data['metadata']['attempt_id'] == str(attempt.pk)
                 and data.get('test') is (str(config('YOOKASSA_TEST', '0')) == '1'))
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation):
        valid = False
    if not valid:
        raise PaymentError('Данные платежа не совпадают с заказом.')


def refresh(attempt):
    data = api('GET', '/payments/' + str(attempt.payment_id))
    validate_payment(attempt, data, attempt.payment_id)
    status = data.get('status')
    if status not in ('pending', 'waiting_for_capture', 'succeeded', 'canceled'):
        raise PaymentError('ЮKassa вернула неизвестный статус.')
    try:
        refunded = Decimal(str(data.get('refunded_amount', {}).get('value', '0')))
        if (not refunded.is_finite() or refunded < 0 or refunded > attempt.order.amount
                or ('refunded_amount' in data and data['refunded_amount'].get('currency') != 'RUB')):
            raise ValueError
    except (TypeError, ValueError, InvalidOperation):
        raise PaymentError('Не удалось проверить сумму возврата.') from None
    with transaction.atomic():
        locked = YooKassaAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status == 'canceled' and not locked.active:
            return  # A delayed response must not reactivate an old canceled attempt.
        payment = OrderPayment.objects.select_for_update().filter(order=locked.order).first()
        if payment and (payment.provider != 'yookassa' or payment.transaction_id != str(attempt.payment_id)):
            raise PaymentError('По заказу найден другой платёж. Требуется проверка поддержки.')
        if payment and payment.status == 'refunded':
            return
        if status == 'succeeded' and data.get('paid') is True:
            OrderPayment.objects.update_or_create(order=locked.order, defaults={
                'provider': 'yookassa', 'transaction_id': str(attempt.payment_id),
                'status': 'refunded' if refunded == locked.order.amount else 'paid',
                'amount': locked.order.amount, 'currency': 'RUB', 'verified_at': timezone.now()})
        elif payment:
            return
        locked.status, locked.active, locked.checked_at = status, status != 'canceled', timezone.now()
        locked.save(update_fields=['status', 'active', 'checked_at'])
