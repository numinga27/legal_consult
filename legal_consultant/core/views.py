from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
import json
import logging

from .models import (
    LegalDirection, Questionnaire, Question, Answer, 
    Conclusion, AnswerConclusion, UserSession, Payment
)

logger = logging.getLogger(__name__)

# ============ АДМИН-ПАНЕЛЬ ============

def admin_login(request):
    """Страница входа в админ-панель"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('core:admin_dashboard')
        else:
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
    
    context = {
        'directions': directions,
        'questionnaires': questionnaires,
        'total_sessions': total_sessions,
        'total_payments': total_payments,
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
    
    # Получаем все вопросы для выбора в select
    all_questions = questions
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Добавление вопроса
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
        
        # Добавление ответа
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
        
        # Добавление вывода
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
            
            # Если есть файл документа
            if request.FILES.get('documents'):
                conclusion.documents = request.FILES['documents']
                conclusion.save()
            
            messages.success(request, 'Вывод добавлен!')
            return redirect('core:admin_questionnaire', q_id=questionnaire.id)
        
        # Связь ответа с выводом
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

# ============ ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ ============

def user_select_problem(request):
    """Страница выбора юридической проблемы"""
    directions = LegalDirection.objects.all()
    return render(request, 'user/select_problem.html', {'directions': directions})

def user_questionnaire(request, q_id):
    """Страница прохождения опросника"""
    questionnaire = get_object_or_404(Questionnaire, id=q_id, is_active=True)
    
    # Получаем или создаем сессию пользователя
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key
    
    # Проверяем существующую сессию
    user_session, created = UserSession.objects.get_or_create(
        session_key=session_key,
        questionnaire=questionnaire,
        defaults={'completed': False}
    )
    
    # Если сессия завершена, создаем новую
    if user_session.completed:
        user_session = UserSession.objects.create(
            session_key=session_key,
            questionnaire=questionnaire,
            completed=False
        )
    
    # Получаем первый вопрос
    first_question = Question.objects.filter(questionnaire=questionnaire).order_by('order').first()
    
    if not first_question:
        messages.error(request, 'В этом опроснике нет вопросов')
        return redirect('core:user_select_problem')
    
    # Если есть текущий вопрос в сессии, используем его
    current_question = user_session.current_question or first_question
    
    context = {
        'questionnaire': questionnaire,
        'question': current_question,
        'session_id': user_session.id,
        'total_questions': Question.objects.filter(questionnaire=questionnaire).count(),
    }
    return render(request, 'user/questionnaire.html', context)

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
        
        # Сохраняем ответ в историю
        history = user_session.answers_history or []
        history.append({
            'question_id': answer.question.id,
            'answer_id': answer.id,
            'answer_text': answer.text,
            'timestamp': timezone.now().isoformat()
        })
        user_session.answers_history = history
        
        # Проверяем, ведет ли ответ к следующему вопросу или к выводу
        response_data = {
            'intermediate_text': answer.intermediate_text,
        }
        
        if answer.next_question:
            # Есть следующий вопрос
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
            # Это последний ответ - ищем вывод
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

def user_result(request, conclusion_id):
    """Страница с результатом"""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    return render(request, 'user/result.html', {'conclusion': conclusion})

def user_payment(request, conclusion_id):
    """Страница оплаты"""
    conclusion = get_object_or_404(Conclusion, id=conclusion_id)
    
    if request.method == 'POST':
        email = request.POST.get('email')
        session_key = request.session.session_key
        
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        # Создаем платеж
        payment = Payment.objects.create(
            session=UserSession.objects.filter(session_key=session_key).last(),
            conclusion=conclusion,
            amount=conclusion.price,
            status='pending',
            email=email
        )
        
        # Здесь должна быть интеграция с платежной системой
        # Пока просто имитируем успешную оплату
        payment.status = 'paid'
        payment.paid_at = timezone.now()
        payment.save()
        
        messages.success(request, 'Оплата успешно произведена! Консультация отправлена на вашу почту.')
        return redirect('core:payment_success', payment_id=payment.id)
    
    return render(request, 'user/payment.html', {'conclusion': conclusion})

def payment_success(request, payment_id):
    """Страница успешной оплаты"""
    payment = get_object_or_404(Payment, id=payment_id)
    return render(request, 'user/payment_success.html', {'payment': payment})

# В views.py, функция user_select_problem
def user_select_problem(request):
    """Страница выбора юридической проблемы"""
    directions = LegalDirection.objects.prefetch_related('questionnaires').all()
    
    # Если нет направлений, создаем тестовое
    if not directions.exists():
        # Создаем тестовое направление для демонстрации
        direction = LegalDirection.objects.create(
            name='Тестовое направление',
            description='Для проверки работы сервиса',
            icon='balance-scale'
        )
        # Создаем тестовый опросник
        questionnaire = Questionnaire.objects.create(
            direction=direction,
            name='Тестовый опросник',
            description='Проверка работы',
            is_active=True
        )
        # Создаем тестовый вопрос
        question = Question.objects.create(
            questionnaire=questionnaire,
            order=1,
            text='Это тестовый вопрос?'
        )
        # Создаем тестовый ответ
        answer = Answer.objects.create(
            question=question,
            text='Да',
            intermediate_text='Вы выбрали "Да"',
            is_final=True
        )
        # Создаем тестовый вывод
        conclusion = Conclusion.objects.create(
            questionnaire=questionnaire,
            order=1,
            title='Тестовый вывод',
            short_text='Это тестовый вывод. Все работает!',
            full_text='Полная консультация для теста.',
            success_rate=100,
            price=0
        )
        # Связываем ответ с выводом
        AnswerConclusion.objects.create(answer=answer, conclusion=conclusion)
        
        directions = LegalDirection.objects.prefetch_related('questionnaires').all()
    
    return render(request, 'user/select_problem.html', {'directions': directions})