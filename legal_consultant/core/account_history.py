"""Capture the server-validated path and transfer only session-owned guest records."""
import hashlib
import json
from uuid import uuid4
from django.db import transaction
from .models import Consultation, HelpOrder, Questionnaire


def session_owner(request):
    if not request.session.get('help_owner_id'):
        request.session['help_owner_id'] = str(uuid4())
    return request.session['help_owner_id']


def capture_result(request, questionnaire, package, state, current):
    if not current.startswith('result:'):
        return None
    owner = session_owner(request)
    if not state.get('attempt_id'):
        state['attempt_id'] = uuid4().hex
        request.session[f'guided_questionnaire_{questionnaire.id}'] = state
    source = package['conclusions'][current[7:]]
    answers = []
    for entry in state.get('history', []):
        node = package['nodes'][entry['node']]
        answers.append({'question': node['text'], 'answer': node['answers'][entry['answer']]['text']})
    fingerprint = hashlib.sha256(json.dumps([owner, questionnaire.id, state['attempt_id'], answers, source],
                                           ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    item, _ = Consultation.objects.get_or_create(fingerprint=fingerprint, defaults={
        'owner_id': owner, 'user': request.user if request.user.is_authenticated else None,
        'questionnaire': questionnaire, 'title': questionnaire.name, 'answers': answers,
        'result_code': current[7:], 'result_title': source['title'], 'short_text': source['short_text'],
        'private_text': source.get('full_text', ''),
    })
    if request.user.is_authenticated and item.user_id is None:
        Consultation.objects.filter(pk=item.pk, user__isnull=True, owner_id=owner).update(user=request.user)
        item.refresh_from_db()
    return item


@transaction.atomic
def claim_guest_history(request, user):
    # Capture completed pre-account sessions, including those started before this release.
    from .guided_views import position
    from .questionnaire_runtime import runtime_package
    for key, state in list(request.session.items()):
        if not key.startswith('guided_questionnaire_') or not isinstance(state, dict):
            continue
        q_id = key.removeprefix('guided_questionnaire_')
        if not q_id.isdecimal():
            continue
        questionnaire = Questionnaire.objects.filter(pk=q_id).first()
        if questionnaire:
            try:
                package = runtime_package(questionnaire)
                capture_result(request, questionnaire, package, state, position(package, state.get('history', [])))
            except (KeyError, ValueError, IndexError, TypeError):
                continue
    owner = request.session.get('help_owner_id')
    if owner:
        Consultation.objects.filter(owner_id=owner, user__isnull=True).update(user=user)
        HelpOrder.objects.filter(owner_id=owner, user__isnull=True).update(user=user)


def owned_records(model, request):
    if request.user.is_authenticated:
        return model.objects.filter(user=request.user)
    owner = request.session.get('help_owner_id')
    return model.objects.filter(owner_id=owner, user__isnull=True) if owner else model.objects.none()


def order_access(order):
    try:
        confirmation = order.payment_confirmation
    except HelpOrder.payment_confirmation.RelatedObjectDoesNotExist:
        return 'pending'
    if confirmation.status == 'refunded':
        return 'refunded'
    return 'paid' if confirmation.grants_access else 'pending'
