"""Server-owned branching: one answer advances one question, with PRG navigation."""
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


def reset_completed_on_entry(request, questionnaire):
    """Choosing a completed questionnaire from the catalogue starts a new attempt."""
    key = f'guided_questionnaire_{questionnaire.id}'
    state = request.session.get(key)
    if not isinstance(state, dict):
        return
    try:
        completed = position(questionnaire.workflow, state.get('history', [])).startswith('result:')
    except (ValueError, KeyError, IndexError, TypeError):
        completed = True
    if completed:
        request.session[key] = {'history': [], 'pending': None,
                                'revision': state.get('revision', 0) + 1}


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
    # Finish an answer selected in the former explanation screen exactly once.
    if state.get('pending') is not None:
        choice = state['pending']
        if current in package['nodes'] and isinstance(choice, int) and 0 <= choice < len(package['nodes'][current]['answers']):
            history.append({'node': current, 'answer': choice})
            current = position(package, history)
        state['pending'] = None
        state['revision'] += 1
        request.session[state_key] = state
    if request.method == 'POST':
        action = request.POST.get('action')
        # Restart is explicit user intent even from a cached page or an older tab.
        # Answers still require the exact revision to avoid duplicate submissions.
        if action != 'restart' and request.POST.get('revision') != str(state['revision']):
            return redirect('core:guided_questionnaire', q_id=q_id)
        if action == 'restart':
            state = {'history': [], 'pending': None, 'revision': state['revision']}
        elif action == 'back':
            if history:
                history.pop()
        elif action == 'answer' and current in package['nodes']:
            try:
                choice = int(request.POST['answer'])
                if not 0 <= choice < len(package['nodes'][current]['answers']):
                    raise ValueError
                history.append({'node': current, 'answer': choice})
            except (ValueError, KeyError):
                return HttpResponseBadRequest('Выберите один из предложенных ответов.')
        else:
            return HttpResponseBadRequest('Недопустимый переход.')
        state['revision'] += 1
        request.session[state_key] = state
        return redirect('core:guided_questionnaire', q_id=q_id)
    request.session[state_key] = state
    node, result = None, None
    if current.startswith('result:'):
        source = package['conclusions'][current[7:]]
        # Paid text and unassigned prices never leave the server in the public result.
        result = {key: source[key] for key in ['title', 'short_text']}
    else:
        node = package['nodes'][current]
    return render(request, 'user/guided_questionnaire.html', {
        'questionnaire': questionnaire, 'state': state, 'node': node, 'result': result,
        'step': len(history) + 1, 'can_back': bool(history),
    })
