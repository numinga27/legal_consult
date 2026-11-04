"""Select one provider for new checkouts, preserve existing attempts."""
from . import platega, yookassa
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone


def provider():
    return yookassa if platega.config('PAYMENT_PROVIDER', 'platega') == 'yookassa' else platega


def enabled():
    return provider().enabled()


def started(order):
    return order.yookassa_attempts.exists() or order.platega_attempts.exists()


def check(order):
    attempt = order.yookassa_attempts.exclude(payment_id=None).order_by('-created_at').first()
    if attempt:
        yookassa.refresh(attempt)
        return True
    attempt = order.platega_attempts.exclude(transaction_id=None).order_by('-created_at').first()
    if attempt:
        platega.refresh(attempt)
        return True
    return False


def refresh_on_return(order):
    if not yookassa.configured():
        return
    now = timezone.now()
    query = order.yookassa_attempts.filter(active=True, payment_id__isnull=False).filter(
        Q(checked_at=None) | Q(checked_at__lt=now-timedelta(seconds=15)))
    attempt = query.first()
    if attempt and query.filter(pk=attempt.pk).update(checked_at=now):
        try:
            yookassa.refresh(attempt)
        except platega.PaymentError:
            return  # The explicit check button remains available after an API outage.
