import json
from uuid import uuid4
from functools import wraps

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from .models import LegalDirection, Questionnaire, QuestionnaireSource
from .paid_help import help_offers
from .google_docs_import import download_google_doc
from .route_review import route_review
from .questionnaire_import import (FORMAT, MAX_BYTES, ImportProblem, prepare_import,
                                   save_package, validate_package)


def staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:admin_login')
        if not request.user.is_staff:
            return render(request, '403.html', status=403)
        return view(request, *args, **kwargs)
    return wrapped


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def import_questionnaire(request):
    package = request.session.get('questionnaire_import_draft')
    draft_revision = request.session.get('questionnaire_import_revision', '')
    selected_direction = request.session.get('questionnaire_import_direction', '')
    source_ids = request.session.get('questionnaire_import_sources', [])
    errors, saved = [], None
    if request.method == 'GET' and request.GET.get('q'):
        item = get_object_or_404(Questionnaire, pk=request.GET['q'])
        if item.workflow.get('format') == FORMAT:
            source_ids = list(item.source_files.values_list('id', flat=True))
            request.session['questionnaire_import_sources'] = source_ids
            package = {key: value for key, value in item.workflow.items() if key != 'import_digest'}
            request.session['questionnaire_import_draft'] = package
            draft_revision = uuid4().hex
            selected_direction = str(item.direction_id)
            request.session['questionnaire_import_revision'] = draft_revision
            request.session['questionnaire_import_direction'] = selected_direction
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'clear':
                for key in ('questionnaire_import_draft', 'questionnaire_import_revision', 'questionnaire_import_direction', 'questionnaire_import_sources'):
                    request.session.pop(key, None)
                return redirect('core:import_questionnaire')
            if action in {'review', 'save', 'download'} and request.POST.get('draft_revision') != draft_revision:
                raise ImportProblem('Этот просмотр устарел: в другой вкладке открыта новая версия. Проверьте текущий опросник перед сохранением.')
            if action == 'analyze':
                graph, word = request.FILES.get('graph'), request.FILES.get('word')
                google_doc = request.POST.get('google_doc', '').strip()
                if not graph or (not word and not google_doc):
                    raise ImportProblem('Выберите схему Draw.io и укажите Google Docs или загрузите .docx с текстами.')
                if word and google_doc:
                    raise ImportProblem('Выберите один источник текстов: Google Docs или файл .docx.')
                word_data = word.read(MAX_BYTES + 1) if word else download_google_doc(google_doc)
                graph_data = graph.read(MAX_BYTES + 1)
                package = prepare_import(graph_data, word_data, request.POST.get('name', ''))
                scenarios = request.FILES.get('scenarios')
                scenario_data = scenarios.read(MAX_BYTES + 1) if scenarios else None
                if scenario_data is not None:
                    from .scenario_import import read_scenarios
                    package['scenario_checks'] = read_scenarios(scenario_data)
                from django.core.files.base import ContentFile
                uploads = [('graph', graph.name, graph_data), ('word', word.name if word else 'google-document.docx', word_data)]
                if scenarios:
                    uploads.append(('scenarios', scenarios.name, scenario_data))
                source_ids = []
                for kind, name, data in uploads:
                    if len(data) > MAX_BYTES:
                        raise ImportProblem('Файл больше 5 МБ.')
                    item = QuestionnaireSource(uploaded_by=request.user, name=name.replace('\\\\', '/').split('/')[-1][:255], kind=kind)
                    from pathlib import Path
                    item.file.save(uuid4().hex + Path(name).suffix.lower(), ContentFile(data), save=True)
                    source_ids.append(item.pk)
                request.session['questionnaire_import_sources'] = source_ids
                draft_revision = uuid4().hex
            elif action == 'load_json':
                uploaded = request.FILES.get('package')
                if not uploaded or uploaded.size > MAX_BYTES:
                    raise ImportProblem('Выберите JSON-пакет не больше 5 МБ.')
                package_data = uploaded.read()
                package = json.loads(package_data)
                errors = validate_package(package)
                if errors:
                    package = None
                    raise ImportProblem('\n'.join(errors))
                from django.core.files.base import ContentFile
                item = QuestionnaireSource(uploaded_by=request.user, name=uploaded.name[:255], kind='package')
                item.file.save(uuid4().hex + '.json', ContentFile(package_data), save=True)
                source_ids = [item.pk]
                request.session['questionnaire_import_sources'] = source_ids
                draft_revision = uuid4().hex
            elif action in {'review', 'save', 'download'} and package:
                selected_direction = request.POST.get('direction', selected_direction)
                package['name'] = request.POST.get('name', package['name']).strip()
                package['start'] = request.POST.get('start', package['start'])
                if any(f'offer_price_{i}' in request.POST for i in range(3)):
                    old_prices = package.get('offer_prices', ['', '', ''])
                    package['offer_prices'] = [request.POST.get(f'offer_price_{i}', old_prices[i]).strip() for i in range(3)]
                for i, node in enumerate(package['nodes'].values()):
                    node['text'] = request.POST.get(f'q{i}', node['text']).strip()
                    for j, answer in enumerate(node['answers']):
                        answer['target'] = request.POST.get(f't{i}_{j}', answer['target'])
                        answer['intermediate_text'] = request.POST.get(f'h{i}_{j}', answer.get('intermediate_text', ''))
                        answer['text'] = request.POST.get(f'a{i}_{j}', answer['text']).strip()
                for i, result in enumerate(package['conclusions'].values()):
                    for field in ['title', 'short_text', 'full_text', 'plan_text']:
                        result[field] = request.POST.get(f'c{i}_{field}', result.get(field, ''))
                errors = validate_package(package)
                draft_revision = uuid4().hex
                if action == 'save' and not errors:
                    if request.POST.get('reviewed') != 'yes':
                        raise ImportProblem('Подтвердите проверку переходов и текстов перед сохранением.')
                    if not selected_direction.isdecimal():
                        raise ImportProblem('Выберите раздел сайта для опросника.')
                    direction = get_object_or_404(LegalDirection, pk=selected_direction)
                    saved, created = save_package(package, direction, activate=request.POST.get('activate') == 'yes')
                    saved.source_files.add(*QuestionnaireSource.objects.filter(pk__in=source_ids))
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
        'sources': QuestionnaireSource.objects.filter(pk__in=source_ids),
        'package': package, 'errors': errors, 'saved': saved,
        'offers': help_offers(package) if package else [],
        'draft_revision': draft_revision, 'selected_direction': selected_direction,
        'directions': LegalDirection.objects.all(),
        'imports': [],  # The paginated owner catalogue is the single saved-questionnaire list.
        'route_review': route_review(package) if package and not errors else None,
    })

@staff_only
@never_cache
@require_http_methods(['GET'])
def download_source(request, source_id):
    from django.http import FileResponse, Http404
    source = get_object_or_404(QuestionnaireSource, pk=source_id)
    try:
        response = FileResponse(source.file.open('rb'), as_attachment=True, filename=source.name, content_type='application/octet-stream')
    except FileNotFoundError:
        raise Http404
    response['X-Content-Type-Options'] = 'nosniff'
    return response
