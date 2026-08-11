#!/usr/bin/env python
"""
Скрипт для создания тестовых данных.
Запуск: python create_data.py
"""

import os
import sys
import django

# Устанавливаем настройки Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')

# Инициализируем Django
django.setup()

from core.models import (
    LegalDirection, Questionnaire, Question, Answer, 
    Conclusion, AnswerConclusion
)

def create_test_data():
    """Создает тестовые данные для проекта"""
    print("=" * 50)
    print("СОЗДАНИЕ ТЕСТОВЫХ ДАННЫХ")
    print("=" * 50)
    
    # 1. Создаем юридическое направление
    direction, created = LegalDirection.objects.get_or_create(
        name='Семейное право',
        defaults={
            'description': 'Вопросы брака, развода, алиментов, опеки и наследства',
            'icon': 'heart'
        }
    )
    if created:
        print(f'✅ Создано направление: {direction.name}')
    else:
        print(f'ℹ️ Направление уже существует: {direction.name}')
    
    # 2. Создаем опросник
    questionnaire, created = Questionnaire.objects.get_or_create(
        direction=direction,
        name='Развод и раздел имущества',
        defaults={
            'description': 'Поможем разобраться с разводом и разделом совместно нажитого имущества',
            'is_active': True
        }
    )
    if created:
        print(f'✅ Создан опросник: {questionnaire.name}')
    else:
        print(f'ℹ️ Опросник уже существует: {questionnaire.name}')
    
    # 3. Создаем вопросы
    # Вопрос 1
    q1, created = Question.objects.get_or_create(
        questionnaire=questionnaire,
        order=1,
        defaults={
            'text': 'Вы состоите в официальном браке?',
            'help_text': 'Официальный брак зарегистрирован в ЗАГСе'
        }
    )
    if created:
        print(f'✅ Создан вопрос 1: {q1.text}')
    
    # Вопрос 2
    q2, created = Question.objects.get_or_create(
        questionnaire=questionnaire,
        order=2,
        defaults={
            'text': 'У вас есть совместно нажитое имущество?',
            'help_text': 'Имущество, приобретенное во время брака'
        }
    )
    if created:
        print(f'✅ Создан вопрос 2: {q2.text}')
    
    # 4. Создаем ответы на вопрос 1
    a1_yes, created = Answer.objects.get_or_create(
        question=q1,
        text='Да',
        defaults={
            'intermediate_text': 'Вы состоите в официальном браке. Это важный фактор для определения прав на совместно нажитое имущество.',
            'is_final': False,
            'order': 1
        }
    )
    if created:
        print(f'✅ Создан ответ: "Да" на вопрос 1')
    
    a1_no, created = Answer.objects.get_or_create(
        question=q1,
        text='Нет',
        defaults={
            'intermediate_text': 'Вы не состоите в официальном браке. Раздел имущества возможен только в случае признания брака недействительным.',
            'is_final': False,
            'order': 2
        }
    )
    if created:
        print(f'✅ Создан ответ: "Нет" на вопрос 1')
    
    # 5. Создаем ответы на вопрос 2
    a2_yes, created = Answer.objects.get_or_create(
        question=q2,
        text='Да, есть',
        defaults={
            'intermediate_text': 'Совместно нажитое имущество подлежит разделу в судебном порядке. Каждый из супругов имеет право на половину.',
            'is_final': True,
            'order': 1
        }
    )
    if created:
        print(f'✅ Создан ответ: "Да, есть" на вопрос 2')
    
    a2_no, created = Answer.objects.get_or_create(
        question=q2,
        text='Нет',
        defaults={
            'intermediate_text': 'Если совместно нажитого имущества нет, раздел имущества не требуется. Бракоразводный процесс проходит упрощенно.',
            'is_final': True,
            'order': 2
        }
    )
    if created:
        print(f'✅ Создан ответ: "Нет" на вопрос 2')
    
    # 6. Связываем ответы с вопросами (логика перехода)
    a1_yes.next_question = q2
    a1_yes.save()
    print(f'✅ Связь: Ответ "Да" → Вопрос 2')
    
    a1_no.is_final = True
    a1_no.save()
    print(f'✅ Связь: Ответ "Нет" → Вывод (завершение)')
    
    # 7. Создаем выводы
    conclusion1, created = Conclusion.objects.get_or_create(
        questionnaire=questionnaire,
        order=1,
        defaults={
            'title': 'Развод с разделом имущества',
            'short_text': 'Вы можете расторгнуть брак и разделить совместно нажитое имущество в судебном порядке. Для этого необходимо подать исковое заявление.',
            'full_text': 'Полная юридическая консультация:\n\n1. Для расторжения брака с разделом имущества необходимо подать исковое заявление в суд по месту жительства ответчика.\n\n2. К иску необходимо приложить:\n   - Свидетельство о браке\n   - Свидетельства о рождении детей (при наличии)\n   - Документы на имущество (свидетельства о праве собственности, договоры)\n   - Квитанция об оплате госпошлины\n\n3. Срок рассмотрения дела: до 2 месяцев.\n\n4. Государственная пошлина: 600 рублей.',
            'pros': '✓ Вы имеете право на раздел имущества\n✓ Имущество будет разделено справедливо\n✓ Суд защитит ваши права',
            'cons': '✗ Процесс может занять до 2-3 месяцев\n✗ Требуется оплата госпошлины\n✗ Может потребоваться помощь юриста',
            'success_rate': 85,
            'price': 1990.00
        }
    )
    if created:
        print(f'✅ Создан вывод 1: {conclusion1.title}')
    
    conclusion2, created = Conclusion.objects.get_or_create(
        questionnaire=questionnaire,
        order=2,
        defaults={
            'title': 'Развод без раздела имущества',
            'short_text': 'Вы можете расторгнуть брак без раздела имущества через ЗАГС или суд (упрощенная процедура).',
            'full_text': 'Полная юридическая консультация:\n\n1. Для расторжения брака без раздела имущества можно обратиться в ЗАГС (при обоюдном согласии) или в суд.\n\n2. Необходимые документы:\n   - Заявление о расторжении брака\n   - Свидетельство о браке\n   - Паспорта супругов\n   - Квитанция об оплате госпошлины\n\n3. Срок рассмотрения: 1 месяц в ЗАГСе.\n\n4. Государственная пошлина: 650 рублей.',
            'pros': '✓ Быстрая процедура\n✓ Минимальные затраты\n✓ Не требуется судебное разбирательство',
            'cons': '✗ Нет раздела имущества\n✗ Требуется обоюдное согласие\n✗ Нет раздела долгов',
            'success_rate': 95,
            'price': 990.00
        }
    )
    if created:
        print(f'✅ Создан вывод 2: {conclusion2.title}')
    
    # 8. Связываем ответы с выводами
    link1, created = AnswerConclusion.objects.get_or_create(
        answer=a2_yes,
        defaults={'conclusion': conclusion1}
    )
    if created:
        print(f'✅ Связь: Ответ "Да, есть" → Вывод 1')
    
    link2, created = AnswerConclusion.objects.get_or_create(
        answer=a2_no,
        defaults={'conclusion': conclusion2}
    )
    if created:
        print(f'✅ Связь: Ответ "Нет" → Вывод 2')
    
    # 9. Создаем вывод для ответа "Нет" на вопрос 1
    conclusion3, created = Conclusion.objects.get_or_create(
        questionnaire=questionnaire,
        order=3,
        defaults={
            'title': 'Не требуется развод',
            'short_text': 'Вы не состоите в официальном браке, поэтому процедура развода не требуется.',
            'full_text': 'Юридическая консультация:\n\nВы не состоите в официальном браке, зарегистрированном в ЗАГСе. В соответствии с Семейным кодексом РФ, развод требуется только для лиц, состоящих в официальном браке.\n\nЕсли у вас есть общие дети или совместно нажитое имущество, вы можете:\n1. Заключить соглашение о разделе имущества\n2. Обратиться в суд для установления отцовства\n3. Взыскать алименты на содержание детей',
            'pros': '✓ Не требуется бракоразводный процесс\n✓ Экономия времени и средств',
            'cons': '✗ Нет прав на раздел имущества как супруг\n✗ Требуется установление отцовства для детей',
            'success_rate': 100,
            'price': 0
        }
    )
    if created:
        print(f'✅ Создан вывод 3: {conclusion3.title}')
    
    # Связываем ответ "Нет" с выводом 3
    link3, created = AnswerConclusion.objects.get_or_create(
        answer=a1_no,
        defaults={'conclusion': conclusion3}
    )
    if created:
        print(f'✅ Связь: Ответ "Нет" (вопрос 1) → Вывод 3')
    
    # 10. Итоговая статистика
    print("\n" + "=" * 50)
    print("СТАТИСТИКА СОЗДАННЫХ ДАННЫХ")
    print("=" * 50)
    print(f"📁 Направлений: {LegalDirection.objects.count()}")
    print(f"📋 Опросников: {Questionnaire.objects.count()}")
    print(f"❓ Вопросов: {Question.objects.count()}")
    print(f"💬 Ответов: {Answer.objects.count()}")
    print(f"📄 Выводов: {Conclusion.objects.count()}")
    print(f"🔗 Связей ответ-вывод: {AnswerConclusion.objects.count()}")
    
    print("\n" + "=" * 50)
    print("✅ ТЕСТОВЫЕ ДАННЫЕ УСПЕШНО СОЗДАНЫ!")
    print("=" * 50)
    
    print("\n🌐 Запустите сервер: python manage.py runserver")
    print("🔗 Откройте в браузере: http://127.0.0.1:8000/")
    print("👤 Админ-панель: http://127.0.0.1:8000/admin-login/")

if __name__ == '__main__':
    try:
        create_test_data()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()