from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
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

logger = logging.getLogger(__name__)


# ============ АДМИН-ПАНЕЛЬ ============
from django.contrib.auth import login, authenticate, logout
from django.shortcuts import redirect
import logging

logger = logging.getLogger(__name__)

def admin_login(request):
    """Страница входа в админ-панель"""
    # Если пользователь уже авторизован - перенаправляем
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('core:admin_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Аутентификация
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            # Вход пользователя
            login(request, user)
            
            # ПРИНУДИТЕЛЬНОЕ сохранение сессии
            request.session.save()
            
            # Создаем ответ с редиректом
            response = redirect('core:admin_dashboard')
            
            # Устанавливаем COOKIE с сессией вручную
            response.set_cookie(
                'sessionid',
                request.session.session_key,
                max_age=604800,  # 7 дней
                path='/',
                domain=None,  # Использует текущий домен
                secure=False,
                httponly=True,
                samesite='Lax'
            )
            
            # Также устанавливаем CSRF cookie
            response.set_cookie(
                'csrftoken',
                request.META.get('CSRF_COOKIE', ''),
                max_age=604800,
                path='/',
                httponly=False,
                samesite='Lax'
            )
            
            logger.info(f"User {username} logged in successfully. Session: {request.session.session_key}")
            
            # Возвращаем ответ с куками
            return response
        else:
            messages.error(request, 'Неверный логин или пароль, или у вас нет прав администратора')
            logger.warning(f"Failed login attempt for user: {username}")
    
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
    questionnaire_id = question.questionnaire.id
    question.delete()
    messages.success(request, 'Вопрос удален!')
    return redirect('core:admin_questionnaire', q_id=questionnaire_id)


@login_required
def admin_delete_answer(request, a_id):
    """Удаление ответа"""
    answer = get_object_or_404(Answer, id=a_id)
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
    """Страница выбора юридической проблемы"""
    directions = LegalDirection.objects.prefetch_related('questionnaires').all()
    
    if not directions.exists():
        direction = LegalDirection.objects.create(
            name='Тестовое направление',
            description='Для проверки работы сервиса',
            icon='balance-scale'
        )
        questionnaire = Questionnaire.objects.create(
            direction=direction,
            name='Тестовый опросник',
            description='Проверка работы',
            is_active=True
        )
        question = Question.objects.create(
            questionnaire=questionnaire,
            order=1,
            text='Это тестовый вопрос?'
        )
        answer = Answer.objects.create(
            question=question,
            text='Да',
            intermediate_text='Вы выбрали "Да"',
            is_final=True
        )
        conclusion = Conclusion.objects.create(
            questionnaire=questionnaire,
            order=1,
            title='Тестовый вывод',
            short_text='Это тестовый вывод. Все работает!',
            full_text='Полная консультация для теста.',
            success_rate=100,
            price=0
        )
        AnswerConclusion.objects.create(answer=answer, conclusion=conclusion)
        directions = LegalDirection.objects.prefetch_related('questionnaires').all()
    
    return render(request, 'user/select_problem.html', {'directions': directions})


def user_questionnaire(request, q_id):
    """Страница прохождения опросника"""
    questionnaire = get_object_or_404(Questionnaire, id=q_id, is_active=True)
    
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key
    
    user_session = UserSession.objects.filter(
        session_key=session_key,
        questionnaire=questionnaire,
        completed=False
    ).first()
    
    if not user_session:
        user_session = UserSession.objects.create(
            session_key=session_key,
            questionnaire=questionnaire,
            completed=False,
            answers_history=[]
        )
    
    first_question = Question.objects.filter(questionnaire=questionnaire).order_by('order').first()
    
    if not first_question:
        messages.error(request, 'В этом опроснике нет вопросов')
        return redirect('core:user_select_problem')
    
    current_question = user_session.current_question or first_question
    
    context = {
        'questionnaire': questionnaire,
        'question': current_question,
        'session_id': user_session.id,
        'total_questions': Question.objects.filter(questionnaire=questionnaire).count(),
    }
    return render(request, 'user/questionnaire.html', context)


def user_result(request, conclusion_id):
    """Страница с результатом и генерацией документа"""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    
    session_key = request.session.session_key
    user_session = UserSession.objects.filter(
        session_key=session_key,
        conclusion=conclusion
    ).first()
    
    user_data = {}
    if request.GET.get('full_name'):
        user_data = {
            'full_name': request.GET.get('full_name'),
            'address': request.GET.get('address', ''),
            'phone': request.GET.get('phone', ''),
            'email': request.GET.get('email', ''),
            'additional_info': request.GET.get('additional_info', '')
        }
    
    generated_doc = None
    has_document = False
    if user_session:
        generated_doc = GeneratedDocument.objects.filter(
            user_session=user_session,
            conclusion=conclusion,
            status='ready'
        ).first()
        has_document = bool(generated_doc and generated_doc.pdf_file)
    
    context = {
        'conclusion': conclusion,
        'user_data': user_data,
        'generated_doc': generated_doc,
        'has_document': has_document,
    }
    return render(request, 'user/result.html', context)


def user_payment(request, conclusion_id):
    """Страница оплаты"""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        session_key = request.session.session_key
        
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        user_session = UserSession.objects.filter(session_key=session_key).last()
        
        payment = Payment.objects.create(
            session=user_session,
            conclusion=conclusion,
            amount=conclusion.price,
            status='pending',
            email=email or 'no-email@example.com'
        )
        
        payment.status = 'paid'
        payment.paid_at = timezone.now()
        payment.save()
        
        if user_session:
            user_data = {}
            if request.POST.get('full_name'):
                user_data = {
                    'full_name': request.POST.get('full_name'),
                    'address': request.POST.get('address', ''),
                    'phone': request.POST.get('phone', ''),
                    'email': email,
                }
                generate_document_for_user(user_session, conclusion, user_data)
        
        messages.success(request, 'Оплата успешно произведена! Консультация отправлена на вашу почту.')
        return redirect('core:payment_success', payment_id=payment.id)
    
    return render(request, 'user/payment.html', {'conclusion': conclusion})


def payment_success(request, payment_id):
    """Страница успешной оплаты"""
    payment = get_object_or_404(Payment, id=payment_id)
    return render(request, 'user/payment_success.html', {'payment': payment})


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

@csrf_exempt
def api_get_next_question(request):
    """API для получения следующего вопроса"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        answer_id = data.get('answer_id')
        session_id = data.get('session_id')
        
        answer = get_object_or_404(Answer, id=answer_id)
        user_session = get_object_or_404(UserSession, id=session_id)
        
        history = user_session.answers_history or []
        history.append({
            'question_id': answer.question.id,
            'answer_id': answer.id,
            'answer_text': answer.text,
            'timestamp': timezone.now().isoformat()
        })
        user_session.answers_history = history
        
        response_data = {
            'intermediate_text': answer.intermediate_text,
        }
        
        if answer.next_question:
            next_q = answer.next_question
            user_session.current_question = next_q
            user_session.save()
            
            response_data['next_question'] = {
                'id': next_q.id,
                'text': next_q.text,
                'answers': [
                    {
                        'id': a.id,
                        'text': a.text,
                        'is_final': a.is_final
                    } for a in next_q.answers.all().order_by('order')
                ]
            }
        else:
            answer_conclusion = AnswerConclusion.objects.filter(answer=answer).first()
            user_session.completed = True
            
            if answer_conclusion:
                user_session.conclusion = answer_conclusion.conclusion
                user_session.save()
                response_data['conclusion_id'] = answer_conclusion.conclusion.id
                response_data['conclusion_title'] = answer_conclusion.conclusion.title
            else:
                user_session.save()
                response_data['conclusion_id'] = None
                response_data['error'] = 'Нет вывода для этого ответа'
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in get_next_question: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


def api_questionnaire_data(request, q_id):
    """API для получения данных опросника"""
    try:
        questionnaire = get_object_or_404(Questionnaire, id=q_id)
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
    """API для проверки ответа и получения следующего вопроса или вывода"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        data = json.loads(request.body)
        answer_id = data.get('answer_id')
        session_id = data.get('session_id')
        
        if not answer_id:
            return JsonResponse({'error': 'ID ответа не указан'}, status=400)
        
        answer = get_object_or_404(Answer, id=answer_id)
        
        if session_id:
            try:
                user_session = UserSession.objects.get(id=session_id)
            except UserSession.DoesNotExist:
                session_key = request.session.session_key
                if not session_key:
                    request.session.create()
                    session_key = request.session.session_key
                
                user_session = UserSession.objects.create(
                    session_key=session_key,
                    questionnaire=answer.question.questionnaire,
                    current_question=answer.question,
                    completed=False,
                    answers_history=[]
                )
        else:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            
            user_session = UserSession.objects.create(
                session_key=session_key,
                questionnaire=answer.question.questionnaire,
                current_question=answer.question,
                completed=False,
                answers_history=[]
            )
        
        history = user_session.answers_history or []
        history.append({
            'question_id': answer.question.id,
            'answer_id': answer.id,
            'answer_text': answer.text,
            'timestamp': timezone.now().isoformat()
        })
        user_session.answers_history = history
        
        response_data = {
            'intermediate_text': answer.intermediate_text,
            'success': True
        }
        
        if answer.next_question:
            next_q = answer.next_question
            user_session.current_question = next_q
            user_session.save()
            
            response_data['next_question'] = {
                'id': next_q.id,
                'text': next_q.text,
                'help_text': next_q.help_text,
                'answers': [
                    {
                        'id': a.id,
                        'text': a.text,
                        'is_final': a.is_final
                    } for a in next_q.answers.all().order_by('order')
                ]
            }
        else:
            answer_conclusion = AnswerConclusion.objects.filter(answer=answer).first()
            
            if answer_conclusion:
                user_session.completed = True
                user_session.conclusion = answer_conclusion.conclusion
                user_session.save()
                
                response_data['conclusion_id'] = answer_conclusion.conclusion.id
                response_data['conclusion'] = {
                    'id': answer_conclusion.conclusion.id,
                    'title': answer_conclusion.conclusion.title,
                    'short_text': answer_conclusion.conclusion.short_text
                }
            else:
                default_conclusion = Conclusion.objects.filter(
                    questionnaire=answer.question.questionnaire
                ).first()
                
                if default_conclusion:
                    user_session.completed = True
                    user_session.conclusion = default_conclusion
                    user_session.save()
                    
                    response_data['conclusion_id'] = default_conclusion.id
                    response_data['conclusion'] = {
                        'id': default_conclusion.id,
                        'title': default_conclusion.title,
                        'short_text': default_conclusion.short_text
                    }
                else:
                    user_session.completed = True
                    user_session.save()
                    response_data['error'] = 'Нет вывода для этого ответа'
                    response_data['conclusion_id'] = None
        
        return JsonResponse(response_data)
        
    except Answer.DoesNotExist:
        return JsonResponse({'error': 'Ответ не найден'}, status=404)
    except Exception as e:
        logger.error(f"API check answer error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


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
    """API для генерации юридического документа"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        data = json.loads(request.body)
        conclusion_id = data.get('conclusion_id')
        user_data = data.get('user_data', {})
        
        if not conclusion_id:
            return JsonResponse({'error': 'ID вывода не указан'}, status=400)
        
        conclusion = get_object_or_404(Conclusion, id=conclusion_id)
        
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        user_session = UserSession.objects.filter(
            session_key=session_key,
            conclusion=conclusion
        ).first()
        
        if not user_session:
            user_session = UserSession.objects.create(
                session_key=session_key,
                questionnaire=conclusion.questionnaire,
                conclusion=conclusion,
                completed=True,
                answers_history=[]
            )
        
        doc = generate_document_for_user(user_session, conclusion, user_data)
        
        if doc and doc.pdf_file:
            return JsonResponse({
                'success': True,
                'document_id': doc.id,
                'pdf_url': doc.pdf_file.url,
                'content_text': doc.content_text,
                'message': 'Документ успешно сгенерирован'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Не удалось сгенерировать документ'
            }, status=500)
        
    except Conclusion.DoesNotExist:
        return JsonResponse({'error': 'Вывод не найден'}, status=404)
    except Exception as e:
        logger.error(f"API generate document error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


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
    return render(request, 'admin/visual_editor.html', {
        'questionnaire': questionnaire
    })    

@login_required
def api_load_workflow(request, q_id):
    """API для загрузки сохраненного алгоритма"""
    try:
        questionnaire = get_object_or_404(Questionnaire, id=q_id)
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