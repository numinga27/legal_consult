#!/usr/bin/env python
"""
Скрипт для создания опросников
Запуск: python create_questionnaires_fixed.py
"""

import os
import sys
import django

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.models import (
    LegalDirection, Questionnaire, Question, Answer, 
    Conclusion, AnswerConclusion
)

def create_questionnaires():
    """Создает опросники"""
    
    print("=" * 60)
    print("СОЗДАНИЕ ОПРОСНИКОВ")
    print("=" * 60)
    
    # ============================================================
    # 1. СОЗДАЕМ НАПРАВЛЕНИЯ
    # ============================================================
    
    directions_data = [
        {'name': 'Семейное право', 'icon': 'heart', 'description': 'Брак, развод, алименты, опека'},
        {'name': 'Трудовое право', 'icon': 'briefcase', 'description': 'Трудовые споры, увольнения, зарплата'},
        {'name': 'Жилищное право', 'icon': 'home', 'description': 'Квартирные вопросы, ЖКХ, приватизация'},
        {'name': 'Потребительское право', 'icon': 'shopping-cart', 'description': 'Защита прав потребителей'},
        {'name': 'Автомобильное право', 'icon': 'car', 'description': 'ДТП, ОСАГО, штрафы'},
        {'name': 'Наследственное право', 'icon': 'gavel', 'description': 'Наследство, завещание'},
    ]
    
    directions = {}
    for d in directions_data:
        direction, created = LegalDirection.objects.get_or_create(
            name=d['name'],
            defaults={'icon': d['icon'], 'description': d['description']}
        )
        directions[d['name']] = direction
        if created:
            print(f"✅ Создано направление: {direction.name}")
    
    print(f"\n📋 Всего направлений: {LegalDirection.objects.count()}")
    
    # ============================================================
    # 2. ОПРОСНИК: "Взыскание алиментов"
    # ============================================================
    
    print("\n" + "=" * 50)
    print("Создание опросника: Взыскание алиментов")
    print("=" * 50)
    
    direction = directions['Семейное право']
    
    q = Questionnaire.objects.create(
        direction=direction,
        name='Взыскание алиментов',
        description='Поможем взыскать алименты на ребенка',
        is_active=True
    )
    print(f"✅ Создан опросник: {q.name}")
    
    # Вопрос 1
    q1 = Question.objects.create(
        questionnaire=q,
        order=1,
        text='У вас есть несовершеннолетний ребенок?',
        help_text='Ребенок до 18 лет'
    )
    
    a1_yes = Answer.objects.create(
        question=q1,
        text='Да',
        intermediate_text='Наличие ребенка дает право на взыскание алиментов (ст. 80 СК РФ).',
        is_final=False
    )
    
    a1_no = Answer.objects.create(
        question=q1,
        text='Нет',
        intermediate_text='Алименты взыскиваются только на содержание несовершеннолетних детей или нетрудоспособных членов семьи.',
        is_final=True
    )
    
    # Вопрос 2
    q2 = Question.objects.create(
        questionnaire=q,
        order=2,
        text='Второй родитель платит алименты?',
        help_text='Добровольная оплата или по соглашению'
    )
    
    a2_no = Answer.objects.create(
        question=q2,
        text='Нет, не платит',
        intermediate_text='Можно взыскать алименты в судебном порядке. Подавайте иск о взыскании алиментов.',
        is_final=True
    )
    
    a2_little = Answer.objects.create(
        question=q2,
        text='Платит, но мало',
        intermediate_text='Можно увеличить размер алиментов через суд. Представьте доказательства недостаточности.',
        is_final=True
    )
    
    a2_yes = Answer.objects.create(
        question=q2,
        text='Платит добровольно',
        intermediate_text='Можно заключить нотариальное соглашение об уплате алиментов.',
        is_final=True
    )
    
    # Связываем ответы
    a1_yes.next_question = q2
    a1_yes.save()
    
    # Выводы
    c1 = Conclusion.objects.create(
        questionnaire=q,
        order=1,
        title='Взыскание алиментов в судебном порядке',
        short_text='Вы можете взыскать алименты на ребенка в судебном порядке.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Подайте исковое заявление о взыскании алиментов
   - В суд по месту жительства истца или ответчика
   - Укажите размер алиментов (1/4 дохода на одного ребенка)

2. Приложите документы:
   - Свидетельство о рождении ребенка
   - Свидетельство о браке/разводе
   - Справка о доходах ответчика (если есть)

3. Участвуйте в судебных заседаниях

4. Получите исполнительный лист

Основание: ст. 80-81 СК РФ""",
        pros='✓ Законное основание для получения алиментов\n✓ Судебная защита\n✓ Возможность взыскания задолженности',
        cons='✗ Длительный процесс (1-2 месяца)\n✗ Нужны доказательства доходов\n✗ Возможно обжалование',
        success_rate=90,
        price=2490
    )
    
    c2 = Conclusion.objects.create(
        questionnaire=q,
        order=2,
        title='Увеличение размера алиментов',
        short_text='Вы можете увеличить размер алиментов через суд.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Подайте иск об увеличении размера алиментов
   - В суд по месту жительства ответчика
   - Укажите причины (рост расходов, изменение доходов)

2. Представьте доказательства:
   - Расходы на ребенка
   - Изменение доходов ответчика

3. Получите решение суда

Основание: ст. 83-84 СК РФ""",
        pros='✓ Увеличение суммы алиментов\n✓ Учет инфляции и роста расходов\n✓ Защита прав ребенка',
        cons='✗ Нужны убедительные доказательства\n✗ Сложный процесс',
        success_rate=70,
        price=2990
    )
    
    c3 = Conclusion.objects.create(
        questionnaire=q,
        order=3,
        title='Соглашение об уплате алиментов',
        short_text='Заключите нотариальное соглашение об уплате алиментов.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Договоритесь с другим родителем о размере алиментов
2. Обратитесь к нотариусу
3. Заключите соглашение
4. Получите нотариально заверенный документ

Основание: ст. 99-100 СК РФ""",
        pros='✓ Быстрая процедура\n✓ Гибкие условия\n✓ Нотариальное заверение',
        cons='✗ Требуется добровольное согласие\n✗ Нотариальные расходы',
        success_rate=95,
        price=1990
    )
    
    # Связываем ответы с выводами
    AnswerConclusion.objects.create(answer=a2_no, conclusion=c1)
    AnswerConclusion.objects.create(answer=a2_little, conclusion=c2)
    AnswerConclusion.objects.create(answer=a2_yes, conclusion=c3)
    
    print(f"✅ Создан опросник: {q.name}")
    print(f"   Вопросов: {q.questions.count()}")
    print(f"   Выводов: {q.conclusions.count()}")
    
    # ============================================================
    # 3. ОПРОСНИК: "Приватизация квартиры"
    # ============================================================
    
    print("\n" + "=" * 50)
    print("Создание опросника: Приватизация квартиры")
    print("=" * 50)
    
    direction = directions['Жилищное право']
    
    q = Questionnaire.objects.create(
        direction=direction,
        name='Приватизация квартиры',
        description='Поможем приватизировать квартиру',
        is_active=True
    )
    print(f"✅ Создан опросник: {q.name}")
    
    q1 = Question.objects.create(
        questionnaire=q,
        order=1,
        text='Вы живете в государственной квартире?',
        help_text='Квартира принадлежит государству или муниципалитету'
    )
    
    a1_yes = Answer.objects.create(
        question=q1,
        text='Да',
        intermediate_text='Квартира подлежит приватизации в соответствии с Законом РФ "О приватизации жилищного фонда".',
        is_final=False
    )
    
    a1_no = Answer.objects.create(
        question=q1,
        text='Нет',
        intermediate_text='Если квартира уже в частной собственности, приватизация не требуется.',
        is_final=True
    )
    
    q2 = Question.objects.create(
        questionnaire=q,
        order=2,
        text='Вы уже приватизировали квартиру?',
        help_text='Ранее участвовали в приватизации'
    )
    
    a2_no = Answer.objects.create(
        question=q2,
        text='Нет, не приватизировал',
        intermediate_text='Вы можете приватизировать квартиру бесплатно один раз в жизни.',
        is_final=True
    )
    
    a2_yes = Answer.objects.create(
        question=q2,
        text='Да, приватизировал',
        intermediate_text='Если квартира уже приватизирована, повторная приватизация невозможна.',
        is_final=True
    )
    
    a1_yes.next_question = q2
    a1_yes.save()
    
    c1 = Conclusion.objects.create(
        questionnaire=q,
        order=1,
        title='Приватизация квартиры возможна',
        short_text='Вы можете приватизировать квартиру бесплатно.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Соберите документы:
   - Паспорт
   - Ордер на квартиру
   - Выписка из домовой книги
   - Справка о неиспользовании права приватизации

2. Обратитесь в МФЦ или в управление жилищной политики

3. Подпишите договор приватизации

4. Зарегистрируйте право собственности

Основание: Закон РФ "О приватизации жилищного фонда в РФ" """,
        pros='✓ Бесплатная процедура\n✓ Становление собственником\n✓ Возможность продажи, дарения, залога',
        cons='✗ Сбор документов (занимает время)\n✗ Очереди в МФЦ\n✗ Только один раз в жизни',
        success_rate=95,
        price=1290
    )
    
    c2 = Conclusion.objects.create(
        questionnaire=q,
        order=2,
        title='Приватизация не требуется',
        short_text='Ваша квартира уже приватизирована или вы не живете в государственной квартире.',
        full_text="""Если квартира уже приватизирована, вы являетесь собственником и можете распоряжаться ею по своему усмотрению.

Если вы живете в приватизированной квартире, никаких дополнительных действий не требуется.""",
        pros='✓ Вы уже собственник\n✓ Нет необходимости в процедуре',
        cons='✗ Нет',
        success_rate=100,
        price=0
    )
    
    AnswerConclusion.objects.create(answer=a2_no, conclusion=c1)
    AnswerConclusion.objects.create(answer=a2_yes, conclusion=c2)
    
    print(f"✅ Создан опросник: {q.name}")
    print(f"   Вопросов: {q.questions.count()}")
    print(f"   Выводов: {q.conclusions.count()}")
    
    # ============================================================
    # 4. ОПРОСНИК: "Возврат некачественного товара"
    # ============================================================
    
    print("\n" + "=" * 50)
    print("Создание опросника: Возврат некачественного товара")
    print("=" * 50)
    
    direction = directions['Потребительское право']
    
    q = Questionnaire.objects.create(
        direction=direction,
        name='Возврат некачественного товара',
        description='Поможем вернуть деньги за товар',
        is_active=True
    )
    print(f"✅ Создан опросник: {q.name}")
    
    q1 = Question.objects.create(
        questionnaire=q,
        order=1,
        text='Вы купили некачественный товар?',
        help_text='Товар имеет недостатки, брак или не соответствует описанию'
    )
    
    a1_yes = Answer.objects.create(
        question=q1,
        text='Да',
        intermediate_text='Вы имеете право на возврат товара или обмен в соответствии с Законом "О защите прав потребителей".',
        is_final=False
    )
    
    a1_no = Answer.objects.create(
        question=q1,
        text='Нет',
        intermediate_text='Если товар качественный, возврат возможен только в течение 14 дней (ст. 25 ЗоЗПП).',
        is_final=True
    )
    
    q2 = Question.objects.create(
        questionnaire=q,
        order=2,
        text='Прошло более 14 дней с покупки?',
        help_text='Срок для возврата качественного товара'
    )
    
    a2_yes = Answer.objects.create(
        question=q2,
        text='Да, более 14 дней',
        intermediate_text='Если товар некачественный, вы можете вернуть его в течение всего гарантийного срока (ст. 18 ЗоЗПП).',
        is_final=True
    )
    
    a2_no = Answer.objects.create(
        question=q2,
        text='Нет, менее 14 дней',
        intermediate_text='Вы можете вернуть товар даже без указания причин (ст. 25 ЗоЗПП).',
        is_final=True
    )
    
    a1_yes.next_question = q2
    a1_yes.save()
    
    c1 = Conclusion.objects.create(
        questionnaire=q,
        order=1,
        title='Возврат товара возможен (гарантийный срок)',
        short_text='Вы можете вернуть некачественный товар в течение гарантийного срока.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Напишите претензию в магазин
   - Укажите причину возврата
   - Требуйте возврат денег или обмен товара

2. Приложите документы:
   - Чек (если есть)
   - Гарантийный талон (если есть)

3. Если магазин отказывает - обратитесь в суд

Основание: ст. 18-25 Закона "О защите прав потребителей" """,
        pros='✓ Закон на вашей стороне\n✓ Возврат денег или обмен\n✓ Судебная защита',
        cons='✗ Нужно написать претензию\n✗ Может потребоваться экспертиза\n✗ Судебные расходы',
        success_rate=85,
        price=1490
    )
    
    c2 = Conclusion.objects.create(
        questionnaire=q,
        order=2,
        title='Возврат товара возможен (14 дней)',
        short_text='Вы можете вернуть товар в течение 14 дней без объяснения причин.',
        full_text="""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Обратитесь в магазин с заявлением о возврате
2. Предъявите товар и чек
3. Получите деньги или обменяйте товар

Основание: ст. 25 Закона "О защите прав потребителей" """,
        pros='✓ Быстрая процедура\n✓ Не нужно объяснять причину\n✓ Возврат денег',
        cons='✗ Только 14 дней\n✗ Товар должен быть в товарном виде\n✗ Не для всех товаров',
        success_rate=95,
        price=890
    )
    
    AnswerConclusion.objects.create(answer=a2_yes, conclusion=c1)
    AnswerConclusion.objects.create(answer=a2_no, conclusion=c2)
    
    print(f"✅ Создан опросник: {q.name}")
    print(f"   Вопросов: {q.questions.count()}")
    print(f"   Выводов: {q.conclusions.count()}")
    
    # ============================================================
    # 5. ИТОГОВАЯ СТАТИСТИКА
    # ============================================================
    
    print("\n" + "=" * 50)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 50)
    
    print(f"📁 Направлений: {LegalDirection.objects.count()}")
    print(f"📋 Опросников: {Questionnaire.objects.count()}")
    print(f"❓ Вопросов: {Question.objects.count()}")
    print(f"💬 Ответов: {Answer.objects.count()}")
    print(f"📄 Выводов: {Conclusion.objects.count()}")
    print(f"🔗 Связей: {AnswerConclusion.objects.count()}")
    
    print("\n📋 Список опросников:")
    for q in Questionnaire.objects.all():
        print(f"  - {q.name} ({q.direction.name}) - {q.questions.count()} вопросов, {q.conclusions.count()} выводов")
    
    print("\n" + "=" * 50)
    print("✅ ВСЕ ОПРОСНИКИ УСПЕШНО СОЗДАНЫ!")
    print("=" * 50)

if __name__ == '__main__':
    create_questionnaires()