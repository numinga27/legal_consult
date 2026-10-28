from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django import forms
from django.utils import timezone
from django.db.models import Exists, OuterRef, Prefetch, Max
import json
import logging
from datetime import datetime

from .models import (
    LegalDirection, Questionnaire, Question, Answer,
    Conclusion, AnswerConclusion, UserSession, Payment,
    GeneratedDocument, DocumentTemplate, AIRules
)
from .pdf_generator import generate_document_for_user
from .ai_integration import get_ai_consultant
from .guided_views import imported, reset_completed_on_entry
from .import_views import staff_only
from django.urls import reverse


def imported_editor_redirect(questionnaire):
    return redirect(reverse('core:import_questionnaire') + f'?q={questionnaire.id}')


def imported_legacy_error():
    return JsonResponse({'error': 'Для импортированного опросника используйте новый интерфейс прохождения и импорта.'}, status=409)

logger = logging.getLogger(__name__)


# ============ АДМИН-ПАНЕЛЬ ============
from django.contrib.auth import login, authenticate, logout
from django.shortcuts import redirect
import logging

logger = logging.getLogger(__name__)

def admin_login(request):
    """Use Django's session middleware and cookie security settings."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('core:admin_dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('core:admin_dashboard')
        messages.error(request, 'Неверный логин или пароль, или у вас нет прав администратора')
    return render(request, 'admin/login.html')


@staff_only
def admin_dashboard(request):
    """Главная панель администратора"""
    if not request.user.is_staff:
        return redirect('core:admin_login')

    directions = LegalDirection.objects.all()
    questionnaires = Questionnaire.objects.all()
    total_sessions = UserSession.objects.count()
    total_payments = Payment.objects.filter(status='paid').count()
    total_documents = GeneratedDocument.objects.count()
    total_rules = AIRules.objects.count()

    context = {
        'directions': directions,
        'questionnaires': questionnaires,
        'total_sessions': total_sessions,
        'total_payments': total_payments,
        'total_documents': total_documents,
        'total_rules': total_rules,
    }
    return render(request, 'admin/dashboard.html', context)


@staff_only
def admin_logout(request):
    """Выход из админ-панели"""
    logout(request)
    return redirect('core:admin_login')


@staff_only
def admin_add_questionnaire(request):
    """Создание нового опросника"""
    if request.method == 'POST':
        direction_id = request.POST.get('direction_id')
        name = request.POST.get('name')
        description = request.POST.get('description', '')

        direction = get_object_or_404(LegalDirection, id=direction_id)
        questionnaire = Questionnaire.objects.create(
            direction=direction,
            name=name,
            description=description,
            is_active=True
        )
        messages.success(request, f'Опросник "{name}" успешно создан!')
        return redirect('core:admin_questionnaire', q_id=questionnaire.id)

    directions = LegalDirection.objects.all()
    return render(request, 'admin/add_questionnaire.html', {'directions': directions})


@staff_only
def admin_questionnaire(request, q_id):
    """Редактирование опросника"""
    questionnaire = get_object_or_404(Questionnaire, id=q_id)
    if imported(questionnaire):
        return imported_editor_redirect(questionnaire)
    questions = Question.objects.filter(questionnaire=questionnaire).order_by('order')
    conclusions = Conclusion.objects.filter(questionnaire=questionnaire).order_by('order')
    all_questions = questions

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_question':
            text = request.POST.get('question_text', '').strip()
            if not text:
                messages.error(request, 'Введите текст вопроса.')
                return redirect('core:admin_questionnaire', q_id=questionnaire.id)
            order = (questions.aggregate(last=Max('order'))['last'] or 0) + 1
            question = Question.objects.create(
                questionnaire=questionnaire,
                text=text,
                order=order
            )
            messages.success(request, 'Вопрос добавлен!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

        elif action == 'add_answer':
            question_id = request.POST.get('question_id')
            text = request.POST.get('answer_text')
            intermediate_text = request.POST.get('intermediate_text', '')
            next_question_id = request.POST.get('next_question') or None
            is_final = request.POST.get('is_final') == 'on'
            if not text or not text.strip() or len(text) > 200 or (is_final and next_question_id):
                messages.error(request, 'Введите ответ до 200 символов и выберите только один следующий шаг.')
                return redirect('core:admin_questionnaire', q_id=questionnaire.id)

            question = get_object_or_404(Question, id=question_id, questionnaire=questionnaire)
            if next_question_id:
                get_object_or_404(Question, id=next_question_id, questionnaire=questionnaire)
            answer = Answer.objects.create(
                question=question,
                text=text,
                intermediate_text=intermediate_text,
                next_question_id=next_question_id,
                is_final=is_final,
                order=question.answers.count() + 1
            )
            messages.success(request, 'Ответ добавлен!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

        elif action == 'add_conclusion':
            order = (conclusions.aggregate(last=Max('order'))['last'] or 0) + 1
            title = request.POST.get('title')
            short_text = request.POST.get('short_text')
            full_text = request.POST.get('full_text')
            pros = request.POST.get('pros', '')
            cons = request.POST.get('cons', '')
            try:
                title = forms.CharField(max_length=200).clean(title)
                short_text = forms.CharField().clean(short_text)
                full_text = forms.CharField().clean(full_text)
                success_rate = forms.IntegerField(min_value=0, max_value=100).clean(request.POST.get('success_rate', 50))
                price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0).clean(request.POST.get('price', 0))
            except forms.ValidationError:
                messages.error(request, 'Заполните заголовок и тексты вывода. Цена должна быть неотрицательной, вероятность — от 0 до 100%.')
                return redirect('core:admin_questionnaire', q_id=questionnaire.id)

            conclusion = Conclusion.objects.create(
                questionnaire=questionnaire,
                order=order,
                title=title,
                short_text=short_text,
                full_text=full_text,
                pros=pros,
                cons=cons,
                success_rate=success_rate,
                price=price
            )

            messages.success(request, 'Вывод добавлен!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

        elif action == 'link_answer':
            answer_id = request.POST.get('answer_id')
            conclusion_id = request.POST.get('conclusion_id')

            answer = get_object_or_404(Answer, id=answer_id, question__questionnaire=questionnaire)
            conclusion = get_object_or_404(Conclusion, id=conclusion_id, questionnaire=questionnaire)
            answer.next_question = None
            answer.is_final = True
            answer.save(update_fields=['next_question', 'is_final'])

            AnswerConclusion.objects.update_or_create(
                answer=answer,
                defaults={'conclusion': conclusion}
            )
            messages.success(request, 'Ответ связан с выводом!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

    context = {
        'questionnaire': questionnaire,
        'questions': questions,
        'conclusions': conclusions,
        'all_questions': all_questions,
    }
    return render(request, 'admin/questionnaire_edit.html', context)


@staff_only
@require_POST
def admin_delete_question(request, q_id):
    """Удаление вопроса"""
    question = get_object_or_404(Question, id=q_id)
    if imported(question.questionnaire):
        return imported_legacy_error()
    questionnaire_id = question.questionnaire.id
    question.delete()
    messages.success(request, 'Вопрос удален!')
    return redirect('core:admin_questionnaire', q_id=questionnaire_id)


@staff_only
@require_POST
def admin_delete_answer(request, a_id):
    """Удаление ответа"""
    answer = get_object_or_404(Answer, id=a_id)
    if imported(answer.question.questionnaire):
        return imported_legacy_error()
    questionnaire_id = answer.question.questionnaire.id
    answer.delete()
    messages.success(request, 'Ответ удален!')
    return redirect('core:admin_questionnaire', q_id=questionnaire_id)


@staff_only
def admin_generate_with_ai(request):
    messages.error(request, 'Генерация ИИ не подключена. Загрузите готовую схему и тексты или создайте опросник вручную.')
    return redirect('core:import_questionnaire')


@staff_only
def admin_test_rules(request):
    """Страница тестирования правил AI"""
    if not request.user.is_staff:
        return redirect('core:admin_login')

    rules = AIRules.objects.filter(is_active=True)
    return render(request, 'admin/test_rules.html', {'rules': rules})


# ============ ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ ============

def user_select_problem(request):
    """Показываем темы без создания тестовых данных при посещении страницы."""
    questionnaires = Questionnaire.objects.filter(
        is_active=True, is_archived=False, questions__isnull=False, conclusions__isnull=False,
    ).distinct()
    directions = (
        LegalDirection.objects.filter(is_active=True)
        .annotate(has_available_questionnaires=Exists(
            questionnaires.filter(direction_id=OuterRef('pk'))
        ))
        .order_by('-has_available_questionnaires', 'name')
        .prefetch_related(Prefetch(
            'questionnaires', queryset=questionnaires, to_attr='available_questionnaires'
        ))
    )
    from .platega import enabled
    return render(request, 'user/select_problem.html', {'directions': directions, 'payment_enabled': enabled()})


def user_questionnaire(request, q_id):
    """All catalogues use the same server-owned, reload-safe questionnaire UI."""
    questionnaire = get_object_or_404(Questionnaire, id=q_id)
    if not request.user.is_staff and (not questionnaire.is_active or questionnaire.is_archived or not questionnaire.direction.is_active):
        from django.http import Http404
        raise Http404
    reset_completed_on_entry(request, questionnaire)
    return redirect('core:guided_questionnaire', q_id=q_id)


def user_result(request, conclusion_id):
    """Legacy bookmarks resume the session; result IDs never select another outcome."""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    return redirect('core:guided_questionnaire', q_id=conclusion.questionnaire_id)


def user_payment(request, conclusion_id):
    """Retired demo checkout must never record fictitious payments."""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    if request.method == 'POST':
        return JsonResponse({'error': 'Оплата пока не подключена. Выберите услугу на странице результата.'}, status=409)
    return redirect('core:guided_questionnaire', q_id=conclusion.questionnaire_id)


def payment_success(request, payment_id):
    if not request.session.session_key:
        from django.http import Http404
        raise Http404
    payment = get_object_or_404(Payment, id=payment_id, session__session_key=request.session.session_key)
    return render(request, 'user/service_unavailable.html', {'questionnaire': payment.conclusion.questionnaire})


def download_document(request, doc_id):
    """Скачивание документа"""
    doc = get_object_or_404(GeneratedDocument, id=doc_id)

    if not doc.pdf_file:
        return JsonResponse({'error': 'Документ не найден'}, status=404)

    doc.downloaded_at = timezone.now()
    doc.save()

    response = FileResponse(doc.pdf_file.open('rb'), as_attachment=True)
    response['Content-Disposition'] = f'attachment; filename="{doc.pdf_file.name.split("/")[-1]}"'
    return response


# ============ API ВЬЮХИ ============

def api_get_next_question(request):
    return JsonResponse({'error': 'Этот интерфейс обновлён. Откройте опросник заново из каталога.'}, status=409)


@staff_only
def api_questionnaire_data(request, q_id):
    """API для получения данных опросника"""
    try:
        questionnaire = get_object_or_404(Questionnaire, id=q_id)
        if imported(questionnaire):
            return imported_legacy_error()
        questions = Question.objects.filter(questionnaire=questionnaire).order_by('order')

        data = {
            'id': questionnaire.id,
            'name': questionnaire.name,
            'description': questionnaire.description,
            'questions': []
        }

        for question in questions:
            q_data = {
                'id': question.id,
                'order': question.order,
                'text': question.text,
                'help_text': question.help_text,
                'answers': []
            }

            for answer in question.answers.all().order_by('order'):
                q_data['answers'].append({
                    'id': answer.id,
                    'text': answer.text,
                    'intermediate_text': answer.intermediate_text,
                    'is_final': answer.is_final,
                    'next_question_id': answer.next_question.id if answer.next_question else None
                })

            data['questions'].append(q_data)

        return JsonResponse(data)

    except Questionnaire.DoesNotExist:
        return JsonResponse({'error': 'Опросник не найден'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_check_answer(request):
    return JsonResponse({'error': 'Этот интерфейс обновлён. Откройте опросник заново из каталога.'}, status=409)


def api_get_session_data(request):
    """API для получения данных сессии пользователя"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    try:
        session_id = request.GET.get('session_id')
        if not session_id:
            return JsonResponse({'error': 'ID сессии не указан'}, status=400)

        user_session = get_object_or_404(UserSession, id=session_id)

        data = {
            'id': user_session.id,
            'questionnaire_id': user_session.questionnaire.id,
            'current_question_id': user_session.current_question.id if user_session.current_question else None,
            'completed': user_session.completed,
            'answers_count': len(user_session.answers_history or []),
            'history': user_session.answers_history or []
        }

        if user_session.conclusion:
            data['conclusion'] = {
                'id': user_session.conclusion.id,
                'title': user_session.conclusion.title
            }

        return JsonResponse(data)

    except UserSession.DoesNotExist:
        return JsonResponse({'error': 'Сессия не найдена'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_generate_document(request):
    return JsonResponse({'error': 'Этот интерфейс обновлён. Откройте опросник заново из каталога.'}, status=409)


@staff_only
@require_POST
def api_test_rules(request):
    return JsonResponse({'error': 'ИИ не подключён. Демонстрационные ответы не используются для юридических опросников.'}, status=409)


@staff_only
@require_POST
def api_save_workflow(request):
    return save_visual_request(request)


def save_visual_request(request):
    from .legacy_workflow import save_visual_draft
    from .questionnaire_import import ImportProblem
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not str(data.get('questionnaire_id', '')).isdecimal():
            return JsonResponse({'success': False, 'error': 'Выберите опросник.'}, status=400)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'Некорректные данные схемы.'}, status=400)
    questionnaire = get_object_or_404(Questionnaire, pk=data['questionnaire_id'])
    if imported(questionnaire):
        return imported_legacy_error()
    try:
        save_visual_draft(questionnaire.pk, data.get('workflow'))
    except ImportProblem as error:
        return JsonResponse({'success': False, 'error': str(error)}, status=400)
    return JsonResponse({'success': True, 'message': 'Схема проверена и сохранена.'})


@staff_only
def visual_editor(request, q_id):
    """Визуальный редактор алгоритмов"""
    questionnaire = get_object_or_404(Questionnaire, id=q_id)
    if imported(questionnaire):
        return imported_editor_redirect(questionnaire)
    return render(request, 'admin/visual_editor.html', {
        'questionnaire': questionnaire
    })

@staff_only
def api_load_workflow(request, q_id):
    """API для загрузки сохраненного алгоритма"""
    try:
        questionnaire = get_object_or_404(Questionnaire, id=q_id)
        if imported(questionnaire) and not request.user.is_staff:
            return JsonResponse({'error': 'Доступ только администратору.'}, status=403)
        workflow = questionnaire.workflow or {}
        return JsonResponse({
            'success': True,
            'workflow': workflow
        })
    except Exception as e:
        logger.error(f"Load workflow error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@staff_only
@require_POST
def api_sync_workflow(request):
    return save_visual_request(request)
