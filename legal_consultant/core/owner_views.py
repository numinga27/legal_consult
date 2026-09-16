"""Owner catalogue and publication; source content is never regenerated here."""
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .import_views import staff_only
from .models import Questionnaire
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
    return render(request, 'admin/dashboard.html', {
        'questionnaires': items, 'total': len(items),
        'published': sum(item.is_active for item in items),
        'drafts': sum(not item.is_active for item in items),
    })


@staff_only
@never_cache
def import_guide(request):
    return render(request, 'admin/import_guide.html')
