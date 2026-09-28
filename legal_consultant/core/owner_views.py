"""Owner catalogue and publication; source content is never regenerated here."""
from django import forms
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .import_views import staff_only
from .models import ConclusionDocument, Questionnaire
from .questionnaire_import import FORMAT, validate_package


@staff_only
@never_cache
@require_http_methods(['GET', 'POST'])
def owner_dashboard(request):
    if request.method == 'POST':
        if not request.POST.get('questionnaire_id', '').isdecimal():
            return HttpResponseBadRequest('Выберите опросник.')
        item = get_object_or_404(Questionnaire, pk=request.POST.get('questionnaire_id'))
        action = request.POST.get('action')
        if item.workflow.get('format') != FORMAT or action not in {'publish', 'unpublish'}:
            messages.error(request, 'Управление публикацией доступно для опросников из документов.')
        elif request.POST.get('revision') != item.workflow.get('import_digest'):
            messages.error(request, 'Версия изменилась. Обновите страницу и проверьте опросник.')
        elif action == 'publish' and validate_package(item.workflow):
            messages.error(request, 'В схеме есть ошибки. Откройте редактор и проверьте переходы перед публикацией.')
        elif action == 'publish' and not item.direction.is_active:
            messages.error(request, 'Раздел сайта отключён. Сначала включите его в настройках администратора.')
        else:
            item.is_active = action == 'publish'
            item.save(update_fields=['is_active'])
            messages.success(request, f'«{item.name}»: ' + ('опубликован.' if item.is_active else 'скрыт от посетителей.'))
        return redirect('core:admin_dashboard')
    items = list(Questionnaire.objects.select_related('direction').prefetch_related('questions', 'conclusions').order_by('-id'))
    for item in items:
        item.is_imported = item.workflow.get('format') == FORMAT
        item.question_count = len(item.workflow['nodes']) if item.is_imported else item.questions.count()
        item.result_count = len(item.workflow['conclusions']) if item.is_imported else item.conclusions.count()
        item.document_count = ConclusionDocument.objects.filter(conclusion__questionnaire=item).count()
    return render(request, 'admin/dashboard.html', {
        'questionnaires': items, 'total': len(items),
        'published': sum(item.is_active for item in items),
        'drafts': sum(not item.is_active for item in items),
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
