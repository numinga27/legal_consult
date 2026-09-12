"""Server-owned branching state with explicit explanation/continue and PRG navigation."""
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import Questionnaire
from .questionnaire_import import FORMAT


def imported(questionnaire):
    return questionnaire.workflow.get('format') == FORMAT


def position(package, history):
    current = package['start']
    for entry in history:
        if current not in package['nodes'] or entry.get('node') != current:
            raise ValueError('История не соответствует опроснику.')
        answer = package['nodes'][current]['answers'][entry['answer']]
        current = answer['target']
    return current


@never_cache
@require_http_methods(['GET', 'POST'])
def guided_questionnaire(request, q_id):
    questionnaire = get_object_or_404(Questionnaire, pk=q_id)
    if not imported(questionnaire) or (not questionnaire.is_active and not request.user.is_staff):
        raise Http404
    package = questionnaire.workflow
    state_key = f'guided_questionnaire_{q_id}'
    state = request.session.get(state_key, {'history': [], 'pending': None, 'revision': 0})
    history = state['history']
    try:
        current = position(package, history)
    except (ValueError, KeyError, IndexError, TypeError):
        state = {'history': [], 'pending': None, 'revision': 0}
        history, current = [], package['start']
    if request.method == 'POST':
        if request.POST.get('revision') != str(state['revision']):
            return redirect('core:guided_questionnaire', q_id=q_id)
        action = request.POST.get('action')
        if action == 'restart':
            state = {'history': [], 'pending': None, 'revision': state['revision']}
        elif action == 'back':
            if state['pending'] is not None:
                state['pending'] = None
            elif history:
                history.pop()
        elif action == 'answer' and state['pending'] is None and current in package['nodes']:
            try:
                choice = int(request.POST['answer'])
                if not 0 <= choice < len(package['nodes'][current]['answers']):
                    raise ValueError
                state['pending'] = choice
            except (ValueError, KeyError):
                return HttpResponseBadRequest('Выберите один из предложенных ответов.')
        elif action == 'continue' and state['pending'] is not None:
            history.append({'node': current, 'answer': state['pending']})
            state['pending'] = None
        else:
            return HttpResponseBadRequest('Недопустимый переход.')
        state['revision'] += 1
        request.session[state_key] = state
        return redirect('core:guided_questionnaire', q_id=q_id)
    request.session[state_key] = state
    node, explanation, result = None, None, None
    if current.startswith('result:'):
        source = package['conclusions'][current[7:]]
        # Paid text and unassigned prices never leave the server in the public result.
        result = {key: source[key] for key in ['title', 'short_text']}
    else:
        node = package['nodes'][current]
        if state['pending'] is not None:
            explanation = node['answers'][state['pending']]
    return render(request, 'user/guided_questionnaire.html', {
        'questionnaire': questionnaire, 'state': state, 'node': node, 'result': result,
        'explanation': explanation, 'step': len(history) + 1,
        'can_back': bool(history) or state['pending'] is not None,
    })
