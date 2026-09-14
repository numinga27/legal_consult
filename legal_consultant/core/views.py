from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.db.models import Exists, OuterRef, Prefetch
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


@login_required
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


@login_required
def admin_logout(request):
    """Выход из админ-панели"""
    logout(request)
    return redirect('core:admin_login')


@login_required
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


@login_required
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
            text = request.POST.get('question_text')
            order = questions.count() + 1
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
            intermediate_text = request.POST.get('intermediate_text')
            next_question_id = request.POST.get('next_question') or None
            is_final = request.POST.get('is_final') == 'on'

            question = get_object_or_404(Question, id=question_id)
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
            order = conclusions.count() + 1
            title = request.POST.get('title')
            short_text = request.POST.get('short_text')
            full_text = request.POST.get('full_text')
            pros = request.POST.get('pros', '')
            cons = request.POST.get('cons', '')
            success_rate = int(request.POST.get('success_rate', 50))
            price = request.POST.get('price', 0)

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

            if request.FILES.get('documents'):
                conclusion.documents = request.FILES['documents']
                conclusion.save()

            messages.success(request, 'Вывод добавлен!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

        elif action == 'link_answer':
            answer_id = request.POST.get('answer_id')
            conclusion_id = request.POST.get('conclusion_id')

            answer = get_object_or_404(Answer, id=answer_id)
            conclusion = get_object_or_404(Conclusion, id=conclusion_id)

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


@login_required
def admin_delete_question(request, q_id):
    """Удаление вопроса"""
    question = get_object_or_404(Question, id=q_id)
    if imported(question.questionnaire):
        return imported_legacy_error()
    questionnaire_id = question.questionnaire.id
    question.delete()
    messages.success(request, 'Вопрос удален!')
    return redirect('core:admin_questionnaire', q_id=questionnaire_id)


@login_required
def admin_delete_answer(request, a_id):
    """Удаление ответа"""
    answer = get_object_or_404(Answer, id=a_id)
    if imported(answer.question.questionnaire):
        return imported_legacy_error()
    questionnaire_id = answer.question.questionnaire.id
    answer.delete()
    messages.success(request, 'Ответ удален!')
    return redirect('core:admin_questionnaire', q_id=questionnaire_id)


@login_required
def admin_generate_with_ai(request):
    """Генерация опросника с помощью AI"""
    if request.method == 'POST':
        topic = request.POST.get('topic')
        category = request.POST.get('category')
        direction_id = request.POST.get('direction_id')
        instructions = request.POST.get('instructions', '')

        try:
            ai = get_ai_consultant('mock')

            questionnaire_data = ai.generate_questionnaire(topic, category, instructions)

            if not questionnaire_data.get('questions'):
                messages.error(request, 'Не удалось сгенерировать вопросы. Попробуйте другую тему.')
                return redirect('core:admin_dashboard')

            direction = get_object_or_404(LegalDirection, id=direction_id)

            questionnaire = Questionnaire.objects.create(
                direction=direction,
                name=f"{topic} (AI)",
                description=f"Сгенерировано AI по теме: {topic}\nКатегория: {category}",
                is_active=True
            )

            question_map = {}
            for q_data in questionnaire_data.get('questions', []):
                question = Question.objects.create(
                    questionnaire=questionnaire,
                    text=q_data['text'],
                    help_text=q_data.get('help_text', ''),
                    order=q_data.get('id', Question.objects.filter(questionnaire=questionnaire).count() + 1)
                )
                question_map[q_data['id']] = question

                for a_data in q_data.get('answers', []):
                    Answer.objects.create(
                        question=question,
                        text=a_data['text'],
                        intermediate_text=a_data.get('intermediate', ''),
                        is_final=a_data.get('is_final', False)
                    )

            for q_data in questionnaire_data.get('questions', []):
                question = question_map.get(q_data['id'])
                if not question:
                    continue
                for a_data in q_data.get('answers', []):
                    if a_data.get('next_question'):
                        try:
                            answer = Answer.objects.get(question=question, text=a_data['text'])
                            next_q = question_map.get(a_data['next_question'])
                            if next_q:
                                answer.next_question = next_q
                                answer.save()
                        except Answer.DoesNotExist:
                            pass

            for c_data in questionnaire_data.get('conclusions', []):
                Conclusion.objects.create(
                    questionnaire=questionnaire,
                    title=c_data['title'],
                    short_text=c_data['short'],
                    full_text=c_data['full'],
                    pros='\n'.join(c_data.get('pros', [])),
                    cons='\n'.join(c_data.get('cons', [])),
                    success_rate=c_data.get('success_rate', 50),
                    price=c_data.get('price', 0)
                )

            messages.success(request, f'✅ Опросник "{topic}" успешно создан с помощью AI!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)

        except Exception as e:
            logger.error(f"AI generation error: {e}")
            messages.error(request, f'❌ Ошибка при генерации: {str(e)}')
            return redirect('core:admin_dashboard')

    directions = LegalDirection.objects.filter(is_active=True)
    return render(request, 'admin/generate_ai.html', {'directions': directions})


@login_required
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
        is_active=True, questions__isnull=False, conclusions__isnull=False,
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
    return render(request, 'user/select_problem.html', {'directions': directions})


def user_questionnaire(request, q_id):
    """All catalogues use the same server-owned, reload-safe questionnaire UI."""
    questionnaire = get_object_or_404(Questionnaire, id=q_id, is_active=True)
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
        return JsonResponse({'error': 'Оплата пока не подключена. Выберите пакет на странице результата.'}, status=409)
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


def api_test_rules(request):
    """API для тестирования правил AI"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    try:
        data = json.loads(request.body)
        rule_id = data.get('rule_id')
        topic = data.get('topic', '')
        instructions = data.get('instructions', '')

        if not rule_id:
            return JsonResponse({'error': 'ID правила не указан'}, status=400)

        rule = get_object_or_404(AIRules, id=rule_id)

        ai = get_ai_consultant('mock')

        context = {
            'topic': topic,
            'category': rule.rule_type,
            'instructions': instructions
        }

        prompt = rule.get_prompt(context)

        if rule.rule_type == 'questionnaire':
            result = ai.generate_questionnaire(topic, rule.rule_type, instructions)
        elif rule.rule_type == 'consultation':
            result = ai.generate_intermediate_consultation(topic, instructions, '')
        elif rule.rule_type == 'document':
            result = ai.generate_document('claim', {'full_name': topic}, instructions)
        else:
            result = {'message': 'Тест выполнен', 'prompt': prompt}

        return JsonResponse({
            'success': True,
            'rule': {
                'id': rule.id,
                'name': rule.name,
                'type': rule.get_rule_type_display()
            },
            'prompt': prompt,
            'result': result
        })

    except Exception as e:
        logger.error(f"API test rules error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_save_workflow(request):
    """API для сохранения визуального алгоритма с синхронизацией с БД"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        questionnaire_id = data.get('questionnaire_id')
        workflow = data.get('workflow', {})

        questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
        if imported(questionnaire):
            return imported_legacy_error()

        # Сохраняем workflow в JSON поле
        questionnaire.workflow = workflow
        questionnaire.save()

        # ============================================================
        # СИНХРОНИЗАЦИЯ: создаем/обновляем вопросы, ответы, выводы
        # ============================================================

        # 1. Удаляем старые данные (опционально - можно только обновлять)
        # Но лучше обновлять, чтобы не потерять связи с оплатами и сессиями
        # Поэтому будем только добавлять новые и обновлять существующие

        # Получаем существующие вопросы
        existing_questions = {q.order: q for q in Question.objects.filter(questionnaire=questionnaire)}
        existing_conclusions = {c.order: c for c in Conclusion.objects.filter(questionnaire=questionnaire)}

        # Счетчики для новых ID
        question_order = 1
        conclusion_order = 1

        # Словарь для связи node_id -> question_id
        node_to_question = {}
        node_to_conclusion = {}

        # Проходим по узлам
        for node in workflow.get('nodes', []):
            node_type = node.get('type')
            node_id = node.get('id')

            if node_type == 'question':
                # Создаем или обновляем вопрос
                question, created = Question.objects.get_or_create(
                    questionnaire=questionnaire,
                    order=question_order,
                    defaults={
                        'text': node.get('title', 'Вопрос без названия'),
                        'help_text': node.get('text', '')
                    }
                )
                if not created:
                    question.text = node.get('title', 'Вопрос без названия')
                    question.help_text = node.get('text', '')
                    question.save()

                node_to_question[node_id] = question
                question_order += 1

            elif node_type == 'answer':
                # Ответы будут создаваться позже, при обработке связей
                pass

            elif node_type == 'conclusion':
                # Создаем или обновляем вывод
                conclusion, created = Conclusion.objects.get_or_create(
                    questionnaire=questionnaire,
                    order=conclusion_order,
                    defaults={
                        'title': node.get('title', 'Вывод без названия'),
                        'short_text': node.get('text', '')[:200],
                        'full_text': node.get('text', ''),
                        'price': node.get('price', 0),
                        'success_rate': node.get('success_rate', 50)
                    }
                )
                if not created:
                    conclusion.title = node.get('title', 'Вывод без названия')
                    conclusion.short_text = node.get('text', '')[:200]
                    conclusion.full_text = node.get('text', '')
                    conclusion.price = node.get('price', 0)
                    conclusion.success_rate = node.get('success_rate', 50)
                    conclusion.save()

                node_to_conclusion[node_id] = conclusion
                conclusion_order += 1

        # 2. Обрабатываем связи (connections)
        # Сначала создаем все ответы для вопросов
        answer_map = {}

        for conn in workflow.get('connections', []):
            source_id = conn.get('source')
            target_id = conn.get('target')

            source_node = next((n for n in workflow['nodes'] if n['id'] == source_id), None)
            target_node = next((n for n in workflow['nodes'] if n['id'] == target_id), None)

            if not source_node or not target_node:
                continue

            # Если источник - вопрос, а цель - ответ
            if source_node['type'] == 'question' and target_node['type'] == 'answer':
                question = node_to_question.get(source_id)
                if question:
                    # Создаем ответ
                    answer_text = target_node.get('title', 'Вариант ответа')
                    intermediate = target_node.get('text', '')

                    answer, created = Answer.objects.get_or_create(
                        question=question,
                        text=answer_text,
                        defaults={
                            'intermediate_text': intermediate,
                            'is_final': False,
                            'order': question.answers.count() + 1
                        }
                    )
                    if not created:
                        answer.intermediate_text = intermediate
                        answer.save()

                    answer_map[target_id] = answer

            # Если источник - ответ, а цель - вывод
            elif source_node['type'] == 'answer' and target_node['type'] == 'conclusion':
                answer = answer_map.get(source_id)
                conclusion = node_to_conclusion.get(target_id)

                if answer and conclusion:
                    # Связываем ответ с выводом
                    AnswerConclusion.objects.update_or_create(
                        answer=answer,
                        defaults={'conclusion': conclusion}
                    )
                    # Помечаем ответ как финальный
                    answer.is_final = True
                    answer.save()

            # Если источник - ответ, а цель - вопрос (переход к следующему вопросу)
            elif source_node['type'] == 'answer' and target_node['type'] == 'question':
                answer = answer_map.get(source_id)
                next_question = node_to_question.get(target_id)

                if answer and next_question:
                    answer.next_question = next_question
                    answer.is_final = False
                    answer.save()

        return JsonResponse({'success': True, 'message': 'Алгоритм сохранен и синхронизирован с БД'})

    except Exception as e:
        logger.error(f"Save workflow error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def visual_editor(request, q_id):
    """Визуальный редактор алгоритмов"""
    questionnaire = get_object_or_404(Questionnaire, id=q_id)
    if imported(questionnaire):
        return imported_editor_redirect(questionnaire)
    return render(request, 'admin/visual_editor.html', {
        'questionnaire': questionnaire
    })

@login_required
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

@login_required
def api_sync_workflow(request):
    """API для синхронизации визуального редактора с БД"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        questionnaire_id = data.get('questionnaire_id')
        workflow = data.get('workflow', {})

        logger.info(f"Sync workflow for questionnaire {questionnaire_id}")
        logger.info(f"Nodes: {len(workflow.get('nodes', []))}")
        logger.info(f"Connections: {len(workflow.get('connections', []))}")

        questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
        if imported(questionnaire):
            return imported_legacy_error()

        # Проверяем, есть ли данные
        if not workflow.get('nodes'):
            return JsonResponse({
                'success': False,
                'error': 'Нет узлов для синхронизации. Сначала создайте блоки.'
            }, status=400)

        # Очищаем старые данные
        Question.objects.filter(questionnaire=questionnaire).delete()
        Answer.objects.filter(question__questionnaire=questionnaire).delete()
        Conclusion.objects.filter(questionnaire=questionnaire).delete()
        AnswerConclusion.objects.filter(conclusion__questionnaire=questionnaire).delete()

        # Создаем заново из workflow
        node_to_question = {}
        node_to_conclusion = {}
        answer_map = {}

        question_order = 1
        conclusion_order = 1

        # Проходим по узлам
        for node in workflow.get('nodes', []):
            node_type = node.get('type')
            node_id = node.get('id')

            if node_type == 'question':
                question = Question.objects.create(
                    questionnaire=questionnaire,
                    order=question_order,
                    text=node.get('title', 'Вопрос без названия'),
                    help_text=node.get('text', '')
                )
                node_to_question[node_id] = question
                question_order += 1
                logger.info(f"Created question: {question.text}")

            elif node_type == 'conclusion':
                conclusion = Conclusion.objects.create(
                    questionnaire=questionnaire,
                    order=conclusion_order,
                    title=node.get('title', 'Вывод без названия'),
                    short_text=node.get('text', '')[:200] if node.get('text') else '',
                    full_text=node.get('text', ''),
                    price=node.get('price', 0),
                    success_rate=node.get('success_rate', 50)
                )
                node_to_conclusion[node_id] = conclusion
                conclusion_order += 1
                logger.info(f"Created conclusion: {conclusion.title}")

        # Обрабатываем связи
        for conn in workflow.get('connections', []):
            source_id = conn.get('source')
            target_id = conn.get('target')

            source_node = next((n for n in workflow['nodes'] if n['id'] == source_id), None)
            target_node = next((n for n in workflow['nodes'] if n['id'] == target_id), None)

            if not source_node or not target_node:
                logger.warning(f"Node not found: {source_id} -> {target_id}")
                continue

            logger.info(f"Processing connection: {source_node['type']} -> {target_node['type']}")

            # Если источник - вопрос, а цель - ответ
            if source_node['type'] == 'question' and target_node['type'] == 'answer':
                question = node_to_question.get(source_id)
                if question:
                    answer = Answer.objects.create(
                        question=question,
                        text=target_node.get('title', 'Вариант ответа'),
                        intermediate_text=target_node.get('text', ''),
                        is_final=False,
                        order=question.answers.count() + 1
                    )
                    answer_map[target_id] = answer
                    logger.info(f"Created answer: {answer.text}")

            # Если источник - ответ, а цель - вывод
            elif source_node['type'] == 'answer' and target_node['type'] == 'conclusion':
                answer = answer_map.get(source_id)
                conclusion = node_to_conclusion.get(target_id)
                if answer and conclusion:
                    AnswerConclusion.objects.create(answer=answer, conclusion=conclusion)
                    answer.is_final = True
                    answer.save()
                    logger.info(f"Linked answer {answer.text} -> conclusion {conclusion.title}")

            # Если источник - ответ, а цель - вопрос (переход к следующему вопросу)
            elif source_node['type'] == 'answer' and target_node['type'] == 'question':
                answer = answer_map.get(source_id)
                next_question = node_to_question.get(target_id)
                if answer and next_question:
                    answer.next_question = next_question
                    answer.is_final = False
                    answer.save()
                    logger.info(f"Linked answer {answer.text} -> next question {next_question.text}")

        # Сохраняем workflow в JSON поле
        questionnaire.workflow = workflow
        questionnaire.save()

        return JsonResponse({
            'success': True,
            'message': f'Синхронизировано: {len(workflow.get("nodes", []))} узлов, {len(workflow.get("connections", []))} связей'
        })

    except Exception as e:
        logger.error(f"Sync workflow error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
