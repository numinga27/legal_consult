"""Platega checkout and authenticated confirmation. Never log credentials or bodies."""
import json
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import HelpOrder, OrderPayment, PlategaAttempt


class PaymentError(ValueError):
    pass


def config(key, default=''):
    return getattr(settings, key, os.environ.get(key, default))


def configured():
    return bool(config('PLATEGA_MERCHANT_ID') and config('PLATEGA_SECRET'))


def enabled():
    return configured() and str(config('PLATEGA_ENABLED', '0')) == '1'


def api(method, path, payload=None):
    if not configured():
        raise PaymentError('Приём оплаты пока не настроен.')
    try:
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        req = Request('https://app.platega.io' + path, method=method,
            headers={'X-MerchantId': config('PLATEGA_MERCHANT_ID'), 'X-Secret': config('PLATEGA_SECRET'),
                     'Content-Type': 'application/json'},
            data=json.dumps(payload).encode() if payload is not None else None)
        with build_opener(NoRedirect).open(req, timeout=20) as response:
            raw = response.read(100001)
            if response.status != 200 or len(raw) > 100000:
                raise PaymentError('Не удалось получить подтверждение от платёжного сервиса.')
        data = json.loads(raw, parse_float=Decimal)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (URLError, OSError, ValueError):
        raise PaymentError('Платёжный сервис временно не отвечает. Проверьте статус заказа позже.') from None


def safe_checkout(url):
    if not isinstance(url, str) or len(url) > 1000 or any(ord(c) < 32 for c in url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'pay.platega.io'
                and not parsed.username and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        return False


def create_checkout(order):
    if not enabled():
        raise PaymentError('Приём оплаты пока не настроен.')
    if not order.user_id or order.amount <= 0:
        raise PaymentError('Для оплаты необходим аккаунт и положительная стоимость заказа.')
    # Reserve before outbound IO. A timeout must not silently create a second invoice.
    with transaction.atomic():
        HelpOrder.objects.select_for_update().get(pk=order.pk)
        if OrderPayment.objects.filter(order=order).exists():
            raise PaymentError('По заказу уже есть подтверждённый платёж. Проверьте его статус.')
        attempt, created = PlategaAttempt.objects.get_or_create(order=order, active=True)
    if not created:
        if attempt.transaction_id:
            refresh(attempt)
            attempt.refresh_from_db()
        if attempt.status == 'PENDING' and safe_checkout(attempt.checkout_url):
            return attempt.checkout_url
        raise PaymentError('Проверьте статус платежа. Если платёж отменён, нажмите «Оплатить» ещё раз. При неизвестном статусе обратитесь в поддержку.')
    order_url = 'https://www.k-urist.ru/help/orders/' + str(order.pk) + '/'
    try:
        data = api('POST', '/v2/transaction/process', {
            'paymentDetails': {'amount': float(order.amount), 'currency': 'RUB'},
            'description': 'Карманный юрист. Заказ ' + str(order.pk),
            'return': order_url, 'failedUrl': order_url, 'payload': str(attempt.pk),
            'metadata': {'userId': str(order.user_id)},
        })
        provider_id = UUID(data['transactionId'])
        if not safe_checkout(data.get('url')) or data.get('status') != 'PENDING':
            raise ValueError
        attempt.transaction_id = provider_id
        attempt.checkout_url = data['url']
        attempt.status = 'PENDING'
        with transaction.atomic():
            attempt.save(update_fields=['transaction_id', 'checkout_url', 'status'])
        return attempt.checkout_url
    except (PaymentError, ValueError, KeyError, TypeError, IntegrityError):
        PlategaAttempt.objects.filter(pk=attempt.pk, status='CREATING').update(status='UNKNOWN')
        raise PaymentError('Не удалось подтвердить создание платежа. Повторное списание не запускается. Обратитесь в поддержку с номером заказа.') from None


def refresh(attempt):
    data = api('GET', '/transaction/' + str(attempt.transaction_id))
    details = data.get('paymentDetails')
    try:
        amount = Decimal(str(details['amount']))
        valid = (UUID(data['id']) == attempt.transaction_id and amount.is_finite()
                 and amount == attempt.order.amount and details['currency'] == 'RUB'
                 and data.get('payload') == str(attempt.pk))
    except (ValueError, KeyError, TypeError, InvalidOperation):
        valid = False
    if not valid:
        raise PaymentError('Данные платежа не совпадают с заказом.')
    status = data.get('status')
    if status not in ('PENDING', 'CONFIRMED', 'CANCELED', 'CHARGEBACKED', 'PARTIALLY_REFUNDED', 'DISPUTED'):
        raise PaymentError('Платёжный сервис вернул неизвестный статус.')
    with transaction.atomic():
        locked = PlategaAttempt.objects.select_for_update().select_related('order').get(pk=attempt.pk)
        payment = OrderPayment.objects.select_for_update().filter(order=locked.order).first()
        if payment and payment.transaction_id != str(locked.transaction_id):
            raise PaymentError('Для заказа уже зарегистрирован другой платёж. Требуется проверка поддержки.')
        # Refunds are terminal; delayed CONFIRMED must never restore access.
        if locked.status == 'CHARGEBACKED' or (payment and payment.status == 'refunded'):
            return
        if status in ('CONFIRMED', 'PARTIALLY_REFUNDED', 'CHARGEBACKED', 'DISPUTED'):
            payment_status = {'CHARGEBACKED': 'refunded', 'DISPUTED': 'held'}.get(status, 'paid')
            OrderPayment.objects.update_or_create(order=locked.order, defaults={
                'provider': 'platega', 'transaction_id': str(locked.transaction_id),
                'status': payment_status, 'amount': amount, 'currency': 'RUB', 'verified_at': timezone.now()})
        elif payment:
            return  # Stale PENDING/CANCELED cannot undo confirmed access.
        locked.status = status
        locked.active = status != 'CANCELED'
        locked.checked_at = timezone.now()
        locked.save(update_fields=['status', 'active', 'checked_at'])
