import json
from uuid import uuid4
from functools import wraps

from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import LegalDirection, Questionnaire
from .questionnaire_import import (FORMAT, MAX_BYTES, ImportProblem, prepare_import,
                                   save_package, validate_package)


def staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:admin_login')
        if not request.user.is_staff:
            return HttpResponseForbidden('Доступ только владельцу и администраторам.')
        return view(request, *args, **kwargs)
    return wrapped


@staff_only
@require_http_methods(['GET', 'POST'])
def import_questionnaire(request):
    package = request.session.get('questionnaire_import_draft')
    draft_revision = request.session.get('questionnaire_import_revision', '')
    selected_direction = request.session.get('questionnaire_import_direction', '')
    errors, saved = [], None
    if request.method == 'GET' and request.GET.get('q'):
        item = get_object_or_404(Questionnaire, pk=request.GET['q'])
        if item.workflow.get('format') == FORMAT:
            package = {key: value for key, value in item.workflow.items() if key != 'import_digest'}
            request.session['questionnaire_import_draft'] = package
            draft_revision = uuid4().hex
            selected_direction = str(item.direction_id)
            request.session['questionnaire_import_revision'] = draft_revision
            request.session['questionnaire_import_direction'] = selected_direction
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action in {'review', 'save', 'download'} and request.POST.get('draft_revision') != draft_revision:
                raise ImportProblem('Этот просмотр устарел: в другой вкладке открыта новая версия. Проверьте текущий опросник перед сохранением.')
            if action == 'analyze':
                graph, word = request.FILES.get('graph'), request.FILES.get('word')
                if not graph or not word:
                    raise ImportProblem('Выберите схему Draw.io и Word с текстами.')
                package = prepare_import(graph.read(MAX_BYTES + 1), word.read(MAX_BYTES + 1),
                                         request.POST.get('name', ''))
                draft_revision = uuid4().hex
            elif action == 'load_json':
                uploaded = request.FILES.get('package')
                if not uploaded or uploaded.size > MAX_BYTES:
                    raise ImportProblem('Выберите JSON-пакет не больше 5 МБ.')
                package = json.loads(uploaded.read())
                errors = validate_package(package)
                if errors:
                    package = None
                    raise ImportProblem('\n'.join(errors))
                draft_revision = uuid4().hex
            elif action in {'review', 'save', 'download'} and package:
                selected_direction = request.POST.get('direction', selected_direction)
                package['name'] = request.POST.get('name', package['name']).strip()
                package['start'] = request.POST.get('start', package['start'])
                for i, node in enumerate(package['nodes'].values()):
                    node['text'] = request.POST.get(f'q{i}', node['text']).strip()
                    for j, answer in enumerate(node['answers']):
                        answer['target'] = request.POST.get(f't{i}_{j}', answer['target'])
                        answer['intermediate_text'] = request.POST.get(f'h{i}_{j}', answer['intermediate_text'])
                for i, result in enumerate(package['conclusions'].values()):
                    for field in ['title', 'short_text', 'full_text']:
                        result[field] = request.POST.get(f'c{i}_{field}', result[field])
                errors = validate_package(package)
                draft_revision = uuid4().hex
                if action == 'save' and not errors:
                    if request.POST.get('reviewed') != 'yes':
                        raise ImportProblem('Подтвердите проверку переходов и текстов перед сохранением.')
                    if not selected_direction.isdecimal():
                        raise ImportProblem('Выберите раздел сайта для опросника.')
                    direction = get_object_or_404(LegalDirection, pk=selected_direction)
                    saved, created = save_package(package, direction, activate=request.POST.get('activate') == 'yes')
                if action == 'download' and not errors:
                    response = HttpResponse(json.dumps(package, ensure_ascii=False, indent=2), content_type='application/json')
                    response['Content-Disposition'] = 'attachment; filename="questionnaire.json"'
                    request.session['questionnaire_import_draft'] = package
                    # Download does not replace the form currently shown in the browser.
                    request.session['questionnaire_import_direction'] = selected_direction
                    return response
            else:
                raise ImportProblem('Сначала загрузите исходные файлы.')
        except (ImportProblem, ValueError, TypeError) as exc:
            errors = [str(exc)]
        if package:
            request.session['questionnaire_import_draft'] = package
            request.session['questionnaire_import_revision'] = draft_revision
            request.session['questionnaire_import_direction'] = selected_direction
    if package:
        errors = errors or validate_package(package)
    return render(request, 'admin/questionnaire_import.html', {
        'package': package, 'errors': errors, 'saved': saved,
        'draft_revision': draft_revision, 'selected_direction': selected_direction,
        'directions': LegalDirection.objects.all(),
        'imports': [q for q in Questionnaire.objects.all() if q.workflow.get('format') == FORMAT],
    })
