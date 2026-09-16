import hashlib
from datetime import timedelta
from uuid import uuid4

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .account_history import claim_guest_history
from .models import AccountAttempt, CustomerAccount


class SignInForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=254, widget=forms.EmailInput(attrs={'autocomplete': 'email', 'placeholder': 'you@example.com'}))
    password = forms.CharField(label='Пароль', max_length=128, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def clean_email(self):
        return self.cleaned_data['email'].strip().casefold()


class SignUpForm(SignInForm):
    password = forms.CharField(label='Придумайте пароль', max_length=128, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), help_text='Не менее 8 символов. Не используйте только цифры или распространённый пароль.')
    password_confirm = forms.CharField(label='Повторите пароль', max_length=128, strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password_confirm') and data['password'] != data['password_confirm']:
            self.add_error('password_confirm', 'Пароли не совпадают.')
        if data.get('password'):
            try:
                validate_password(data['password'], get_user_model()(email=data.get('email', '')))
            except ValidationError as exc:
                self.add_error('password', exc)
        return data


def allow_attempt(email):
    """Database-backed limit shared by all Gunicorn workers; no raw emails in keys."""
    key = hashlib.sha256(('account:' + email).encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        record, _ = AccountAttempt.objects.get_or_create(key=key)
        AccountAttempt.objects.filter(key=key, started_at__lt=now-timedelta(minutes=15)).update(started_at=now, count=0)
        changed = AccountAttempt.objects.filter(key=key, count__lt=10).update(count=F('count')+1)
    return bool(changed)


@never_cache
@require_http_methods(['GET', 'POST'])
def account_auth(request, mode='login'):
    if not settings.DEBUG and (not request.is_secure() or not settings.SESSION_COOKIE_SECURE):
        return render(request, 'user/account_unavailable.html', status=503)
    if request.user.is_authenticated:
        return redirect('core:help_orders')
    registration = mode == 'register'
    form = (SignUpForm if registration else SignInForm)(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        if not allow_attempt(email):
            form.add_error(None, 'Слишком много попыток. Попробуйте через 15 минут.')
        elif registration:
            if CustomerAccount.objects.filter(email=email).exists() or get_user_model().objects.filter(email__iexact=email).exists():
                form.add_error(None, 'Не удалось создать аккаунт с этим email. Попробуйте войти или укажите другой адрес.')
            else:
                try:
                    with transaction.atomic():
                        user = get_user_model().objects.create_user(username='customer_' + uuid4().hex, email=email, password=form.cleaned_data['password'])
                        CustomerAccount.objects.create(user=user, email=email)
                        claim_guest_history(request, user)
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    messages.success(request, 'Аккаунт создан. Результаты и заказы этого браузера сохранены в кабинете.')
                    return redirect('core:help_orders')
                except IntegrityError:
                    form.add_error(None, 'Не удалось создать аккаунт с этим email. Попробуйте войти.')
        else:
            account = CustomerAccount.objects.select_related('user').filter(email=email).first()
            candidates = list(get_user_model().objects.filter(email__iexact=email)[:2]) if not account else []
            candidate = account.user if account else (candidates[0] if len(candidates) == 1 else None)
            # Django performs a password hash even when no account exists.
            user = authenticate(request, username=candidate.username if candidate else 'missing_' + uuid4().hex,
                                password=form.cleaned_data['password'])
            if user is None:
                form.add_error(None, 'Не удалось войти. Проверьте email и пароль.')
            else:
                claim_guest_history(request, user)
                login(request, user)
                AccountAttempt.objects.filter(key=hashlib.sha256(('account:' + email).encode()).hexdigest()).delete()
                return redirect('core:help_orders')
    return render(request, 'user/account_auth.html', {'form': form, 'registration': registration})


@never_cache
@require_POST
def account_logout(request):
    logout(request)
    return redirect('core:user_select_problem')
