"""Bundle selection and private unpaid orders, without simulated payments."""
import hashlib
import json
import re

from django import forms
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .guided_views import imported, position
from .models import HelpOrder, Questionnaire, Consultation
from .paid_help import help_offers
from .account_history import capture_result, session_owner, owned_records, order_access


class CustomerForm(forms.Form):
    full_name = forms.CharField(label='ФИО', max_length=200, widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    email = forms.EmailField(label='Почта', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    phone = forms.CharField(label='Телефон', max_length=40, widget=forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel'}))

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if not re.fullmatch(r'[+0-9() .-]+', phone) or not 7 <= len(re.sub(r'\D', '', phone)) <= 15:
            raise forms.ValidationError('Укажите телефон с кодом страны или города.')
        return phone


@never_cache
@require_http_methods(['GET', 'POST'])
def select_help(request, q_id, bundle_index):
    questionnaire = get_object_or_404(Questionnaire, pk=q_id)
    if not imported(questionnaire) or (not questionnaire.is_active and not request.user.is_staff):
        raise Http404
    state = request.session.get(f'guided_questionnaire_{q_id}', {})
    try:
        current = position(questionnaire.workflow, state.get('history', []))
    except (KeyError, ValueError, IndexError, TypeError):
        return redirect('core:guided_questionnaire', q_id=q_id)
    if not current.startswith('result:'):
        return redirect('core:guided_questionnaire', q_id=q_id)
    offers = help_offers(questionnaire.workflow)
    if not 0 <= bundle_index < len(offers) or not offers[bundle_index]['price']:
        raise Http404
    offer = offers[bundle_index]
    source = questionnaire.workflow['conclusions'][current[7:]]
    owner_id = session_owner(request)
    consultation = capture_result(request, questionnaire, questionnaire.workflow, state, current)
    # Bind the form to the current path and published package, not posted price/result IDs.
    context = [owner_id, q_id, questionnaire.workflow, state.get('history', []), state.get('attempt_id'), bundle_index]
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    form = CustomerForm(request.POST if request.method == 'POST' else None,
                        initial={'email': request.user.email} if request.user.is_authenticated else None)
    if request.method == 'POST':
        if request.POST.get('revision') != str(state.get('revision', 0)) or request.POST.get('selection') != fingerprint:
            return redirect('core:guided_questionnaire', q_id=q_id)
        if form.is_valid():
            order, _ = HelpOrder.objects.get_or_create(fingerprint=fingerprint, defaults={
                'owner_id': owner_id, 'questionnaire': questionnaire,
                'user': request.user if request.user.is_authenticated else None,
                'consultation': consultation,
                'private_text': source.get('full_text', '') if bundle_index in (0, 2) else '',
                'result_code': current[7:], 'bundle_index': bundle_index,
                'summary': {'questionnaire': questionnaire.name, 'result': source['title'],
                            'title': offer['title'], 'services': list(offer['services'])},
                'amount': offer['price'], **form.cleaned_data,
            })
            return redirect('core:help_order', order_id=order.id)
    return render(request, 'user/help_checkout.html', {
        'questionnaire': questionnaire, 'offer': offer, 'form': form,
        'revision': state.get('revision', 0), 'selection': fingerprint,
    })


@never_cache
@require_http_methods(['GET'])
def help_order(request, order_id):
    order = get_object_or_404(owned_records(HelpOrder, request).select_related('payment_confirmation', 'consultation'), pk=order_id)
    order.access = order_access(order)
    return render(request, 'user/order_detail.html', {'order': order})


@never_cache
@require_http_methods(['GET'])
def help_orders(request):
    if not request.user.is_authenticated:
        return render(request, 'user/help_orders.html', {'guest': True})
    orders = owned_records(HelpOrder, request).select_related('payment_confirmation', 'consultation')
    consultations = owned_records(Consultation, request)
    tab = 'orders' if request.GET.get('tab') == 'orders' else 'results'
    page = Paginator(orders if tab == 'orders' else consultations, 10).get_page(request.GET.get('page'))
    if tab == 'orders':
        for order in page:
            order.access = order_access(order)
    return render(request, 'user/help_orders.html', {
        'page': page, 'tab': tab, 'results_count': consultations.count(), 'orders_count': orders.count(),
    })


@never_cache
@require_http_methods(['GET'])
def consultation_detail(request, consultation_id):
    if not request.user.is_authenticated:
        return redirect('core:account_login')
    consultation = get_object_or_404(owned_records(Consultation, request), pk=consultation_id)
    orders = list(owned_records(HelpOrder, request).filter(consultation=consultation).select_related('payment_confirmation'))
    for order in orders:
        order.access = order_access(order)
    return render(request, 'user/consultation_detail.html', {'consultation': consultation, 'orders': orders})
