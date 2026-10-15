"""Owner catalogue and publication; source content is never regenerated here."""
from django import forms
import hashlib
import json
import re
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .import_views import staff_only
from .models import ConclusionDocument, Questionnaire, LegalDirection, Payment, Question, Answer, Conclusion, QuestionnaireRun, HelpOrder
from .questionnaire_import import FORMAT, validate_package
from .questionnaire_runtime import runtime_package


def publication_errors(item):
    if item.is_archived:
        return ['Сначала верните опросник из архива.']
    if not item.direction.is_active:
        return ['Раздел сайта отключён.']
    if item.workflow.get('format') == FORMAT:
        return validate_package(item.workflow)
    package = runtime_package(item)
    if not package['nodes'] or not package['conclusions']:
        return ['Добавьте вопросы, ответы и выводы.']
    # Reuse graph validation for legacy routes, including cycles and unreachable results.
    return validate_package({**package, 'format': FORMAT, 'name': item.name})


class QuestionnaireForm(forms.ModelForm):
    class Meta:
        model = Questionnaire
        fields = ['name', 'direction', 'description']
        labels = {'direction': 'Раздел сайта'}
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def questionnaire_settings(request, q_id=None):
    item = get_object_or_404(Questionnaire, pk=q_id) if q_id else Questionnaire(is_active=False)
    form = QuestionnaireForm(request.POST if request.method == 'POST' else None, instance=item)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        if item.workflow.get('format') == FORMAT:
            package = {k: v for k, v in item.workflow.items() if k != 'import_digest'}
            package['name'] = item.name
            digest = hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            item.workflow = {**package, 'import_digest': digest}
        item.save()
        messages.success(request, 'Опросник сохранён.' if q_id else 'Черновик создан. Добавьте вопросы и выводы.')
        return redirect('core:questionnaire_settings', q_id=item.pk)
    return render(request, 'admin/questionnaire_settings.html', {
        'form': form, 'item': item, 'creating': q_id is None,
        'is_imported': item.workflow.get('format') == FORMAT,
    })


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def questionnaire_content_edit(request, q_id, kind, object_id):
    item = get_object_or_404(Questionnaire, pk=q_id)
    if item.workflow.get('format') == FORMAT:
        return HttpResponseBadRequest('Для этого опросника используйте редактор новой версии из документов.')
    definitions = {
        'question': (Question, ['text', 'help_text'], {'questionnaire': item}, 'Редактировать вопрос'),
        'answer': (Answer, ['text', 'intermediate_text', 'next_question', 'is_final'], {'question__questionnaire': item}, 'Редактировать ответ'),
        'conclusion': (Conclusion, ['title', 'short_text', 'full_text', 'pros', 'cons', 'price', 'success_rate'], {'questionnaire': item}, 'Редактировать вывод'),
    }
    if kind not in definitions:
        return HttpResponseBadRequest('Неизвестный тип записи.')
    model, fields, scope, title = definitions[kind]
    obj = get_object_or_404(model, pk=object_id, **scope)
    form_type = forms.modelform_factory(model, fields=fields)
    form = form_type(request.POST if request.method == 'POST' else None, instance=obj)
    if kind == 'answer':
        form.fields['next_question'].queryset = item.questions.all()
    if request.method == 'POST' and form.is_valid():
        if kind == 'answer' and form.cleaned_data.get('next_question') and form.cleaned_data.get('is_final'):
            form.add_error('next_question', 'Выберите либо следующий вопрос, либо финальный ответ.')
        else:
            obj = form.save()
            if kind == 'answer' and obj.next_question_id:
                from .models import AnswerConclusion
                AnswerConclusion.objects.filter(answer=obj).delete()
            messages.success(request, 'Изменения сохранены.')
            return redirect('core:admin_questionnaire', q_id=item.pk)
    return render(request, 'admin/questionnaire_content_edit.html', {'form': form, 'item': item, 'title': title})


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def questionnaire_delete(request, q_id):
    item = get_object_or_404(Questionnaire, pk=q_id)
    error = ''
    if request.method == 'POST':
        if request.POST.get('confirm_name') != item.name:
            error = 'Для подтверждения введите точное название опросника.'
        else:
            try:
                with transaction.atomic():
                    item = Questionnaire.objects.select_for_update().get(pk=q_id)
                    if item.helporder_set.exists() or Payment.objects.filter(Q(conclusion__questionnaire=item) | Q(session__questionnaire=item)).exists():
                        raise ProtectedError('Orders exist', [item])
                    item.delete()
                messages.success(request, 'Опросник удалён.')
                return redirect('core:admin_dashboard')
            except ProtectedError:
                error = 'У опросника есть заказы или платежи. Чтобы сохранить их историю, переместите его в архив.'
    return render(request, 'admin/questionnaire_delete.html', {'item': item, 'error': error})


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def owner_dashboard(request):
    if request.method == 'POST':
        if not request.POST.get('questionnaire_id', '').isdecimal():
            return HttpResponseBadRequest('Выберите опросник.')
        item = get_object_or_404(Questionnaire, pk=request.POST.get('questionnaire_id'))
        action = request.POST.get('action')
        if action not in {'publish', 'unpublish', 'archive', 'restore'}:
            return HttpResponseBadRequest('Неизвестное действие.')
        elif action == 'publish' and item.workflow.get('format') == FORMAT and request.POST.get('revision') != item.workflow.get('import_digest'):
            messages.error(request, 'Версия изменилась. Обновите страницу и проверьте опросник.')
        elif action == 'publish' and (errors := publication_errors(item)):
            messages.error(request, 'Публикация невозможна. ' + ' '.join(errors[:3]))
        else:
            item.is_active = action == 'publish'
            if action in {'archive', 'restore'}:
                item.is_archived = action == 'archive'
            item.save(update_fields=['is_active', 'is_archived', 'updated_at'])
            labels = {'publish': 'опубликован.', 'unpublish': 'скрыт от посетителей.', 'archive': 'перемещён в архив.', 'restore': 'возвращён в черновики.'}
            messages.success(request, f'«{item.name}»: ' + labels[action])
        return redirect(request.get_full_path())
    all_items = Questionnaire.objects.all()
    status = request.GET.get('status', 'current')
    if status not in {'current', 'published', 'draft', 'archive', 'all'}:
        status = 'current'
    items = all_items.select_related('direction')
    if status == 'archive':
        items = items.filter(is_archived=True)
    elif status != 'all':
        items = items.filter(is_archived=False)
        if status in {'published', 'draft'}:
            items = items.filter(is_active=status == 'published')
    search = request.GET.get('q', '').strip()[:200]
    direction = request.GET.get('direction', '')
    kind = request.GET.get('kind', '')
    if search:
        items = items.filter(Q(name__iregex=re.escape(search)) | Q(direction__name__iregex=re.escape(search)))
    if direction.isdecimal():
        items = items.filter(direction_id=direction)
    if kind == 'import':
        items = items.filter(workflow__format=FORMAT)
    elif kind == 'manual':
        items = items.exclude(pk__in=all_items.filter(workflow__format=FORMAT).values('pk'))
    page = Paginator(items.order_by('-id'), 10).get_page(request.GET.get('page'))
    ids = [item.pk for item in page]
    def counts(model, field='questionnaire_id'):
        return dict(model.objects.filter(**{field + '__in': ids}).values(field).annotate(n=Count('pk')).values_list(field, 'n'))
    questions, results = counts(Question), counts(Conclusion)
    documents, orders = counts(ConclusionDocument, 'conclusion__questionnaire_id'), counts(HelpOrder)
    runs = {row['questionnaire_id']: row for row in QuestionnaireRun.objects.filter(questionnaire_id__in=ids).values('questionnaire_id').annotate(starts=Count('pk'), finishes=Count('pk', filter=Q(completed_at__isnull=False)))}
    for item in page:
        item.question_count, item.result_count = questions.get(item.pk, 0), results.get(item.pk, 0)
        item.document_count, item.orders_count = documents.get(item.pk, 0), orders.get(item.pk, 0)
        item.starts = runs.get(item.pk, {}).get('starts', 0)
        item.finishes = runs.get(item.pk, {}).get('finishes', 0)
        item.is_imported = item.workflow.get('format') == FORMAT
        if item.is_imported:
            item.question_count = len(item.workflow.get('nodes', {}))
            item.result_count = len(item.workflow.get('conclusions', {}))
        item.completion_rate = round(item.finishes * 100 / item.starts) if item.starts else 0
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'admin/dashboard.html', {
        'questionnaires': page, 'page_obj': page, 'page_query': params.urlencode(),
        'total': all_items.filter(is_archived=False).count(),
        'published': all_items.filter(is_active=True, is_archived=False).count(),
        'drafts': all_items.filter(is_active=False, is_archived=False).count(),
        'archived': all_items.filter(is_archived=True).count(),
        'directions': LegalDirection.objects.all(), 'search': search,
        'selected_direction': direction, 'selected_kind': kind, 'selected_status': status,
    })


@staff_only
@never_cache
def import_guide(request):
    return render(request, 'admin/import_guide.html')


class ConclusionDocumentForm(forms.ModelForm):
    class Meta:
        model = ConclusionDocument
        fields = ['conclusion', 'title', 'docx_file', 'pdf_file', 'is_active']
        widgets = {
            'docx_file': forms.FileInput(attrs={'accept': '.docx'}),
            'pdf_file': forms.FileInput(attrs={'accept': '.pdf'}),
        }

    def __init__(self, *args, questionnaire, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['conclusion'].queryset = questionnaire.conclusions.order_by('order')


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def questionnaire_documents(request, q_id):
    questionnaire = get_object_or_404(Questionnaire, pk=q_id)
    document = None
    document_id = request.POST.get('document_id') if request.method == 'POST' else request.GET.get('edit')
    if document_id:
        document = get_object_or_404(
            ConclusionDocument,
            pk=document_id,
            conclusion__questionnaire=questionnaire,
        )
    form = ConclusionDocumentForm(
        request.POST or None,
        request.FILES or None,
        instance=document,
        questionnaire=questionnaire,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Комплект DOCX + PDF сохранён.')
        return redirect('core:questionnaire_documents', q_id=questionnaire.pk)
    documents = ConclusionDocument.objects.filter(
        conclusion__questionnaire=questionnaire,
    ).select_related('conclusion')
    return render(request, 'admin/questionnaire_documents.html', {
        'questionnaire': questionnaire,
        'documents': documents,
        'document': document,
        'form': form,
    })
