from django.db import models
from django.utils import timezone

class LegalDirection(models.Model):
    """
    Юридическое направление (например: "Семейное право", "Трудовое право" и т.д.)
    """
    name = models.CharField('Название направления', max_length=200)
    description = models.TextField('Описание', blank=True)
    icon = models.CharField('Иконка (CSS класс)', max_length=50, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    is_active = models.BooleanField('Активно', default=True)

    class Meta:
        verbose_name = 'Юридическое направление'
        verbose_name_plural = 'Юридические направления'
        ordering = ['name']

    def __str__(self):
        return self.name

class Questionnaire(models.Model):
    """
    Опросник для конкретного юридического направления
    """
    direction = models.ForeignKey(
        LegalDirection, 
        on_delete=models.CASCADE, 
        verbose_name='Направление',
        related_name='questionnaires'
    )
    name = models.CharField('Название опросника', max_length=200)
    description = models.TextField('Описание', blank=True)
    is_active = models.BooleanField('Активен', default=True)
    workflow = models.JSONField('Визуальный алгоритм', default=dict, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    views_count = models.PositiveIntegerField('Просмотров', default=0)  # Добавить
    completions_count = models.PositiveIntegerField('Завершений', default=0) 
    class Meta:
        verbose_name = 'Опросник'
        verbose_name_plural = 'Опросники'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.direction.name} - {self.name}"

class Question(models.Model):
    """
    Вопрос в опроснике
    """
    questionnaire = models.ForeignKey(
        Questionnaire, 
        on_delete=models.CASCADE, 
        verbose_name='Опросник',
        related_name='questions'
    )
    order = models.PositiveIntegerField('Порядковый номер')
    text = models.TextField('Текст вопроса')
    help_text = models.TextField('Подсказка', blank=True, help_text='Дополнительная информация к вопросу')
    is_required = models.BooleanField('Обязательный', default=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order']
        unique_together = ['questionnaire', 'order']

    def __str__(self):
        return f"{self.order}. {self.text[:50]}"

class Answer(models.Model):
    """
    Вариант ответа на вопрос
    """
    ANSWER_TYPES = [
        ('single', 'Одиночный выбор'),
        ('multiple', 'Множественный выбор'),
    ]
    
    question = models.ForeignKey(
        Question, 
        on_delete=models.CASCADE, 
        verbose_name='Вопрос',
        related_name='answers'
    )
    text = models.CharField('Текст ответа', max_length=200)
    answer_type = models.CharField('Тип ответа', max_length=10, choices=ANSWER_TYPES, default='single')
    intermediate_text = models.TextField(
        'Промежуточная консультация',
        help_text='Показывается пользователю сразу после выбора ответа'
    )
    next_question = models.ForeignKey(
        Question, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='previous_answers',
        verbose_name='Следующий вопрос'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    is_final = models.BooleanField('Финальный ответ (ведет к выводу)', default=False)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответов'
        ordering = ['order']

    def __str__(self):
        return f"{self.question.order}. {self.text}"

class Conclusion(models.Model):
    """
    Вывод (результат) после прохождения опросника
    """
    questionnaire = models.ForeignKey(
        Questionnaire, 
        on_delete=models.CASCADE, 
        verbose_name='Опросник',
        related_name='conclusions'
    )
    order = models.PositiveIntegerField('Номер вывода')
    title = models.CharField('Заголовок', max_length=200)
    is_paid = models.BooleanField('Только платно', default=False)  # Добавить
    views_count = models.PositiveIntegerField('Просмотров', default=0)  # Добавить
    purchases_count = models.PositiveIntegerField('Покупок', default=0)  # Добавить
    short_text = models.TextField('Краткий вывод (бесплатно)')
    user_data_fields = models.JSONField(
        'Поля для сбора данных',
        default=list,
        blank=True,
        help_text='Список полей, которые нужно заполнить пользователю. Формат: [{"name": "full_name", "label": "ФИО", "type": "text", "required": true}]'
    )
    full_text = models.TextField('Итоговый вывод (платно)')
    pros = models.TextField('Плюсы ситуации', blank=True, help_text='Положительные аспекты для пользователя')
    cons = models.TextField('Минусы ситуации', blank=True, help_text='Негативные аспекты для пользователя')
    success_rate = models.IntegerField('Вероятность успеха', default=50, help_text='От 0 до 100%')
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2, default=0)
    documents = models.FileField(
        'Документы', 
        upload_to='docs/%Y/%m/%d/', 
        blank=True, 
        null=True,
        help_text='Прикрепите файлы документов'
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Вывод'
        verbose_name_plural = 'Выводы'
        ordering = ['order']

    def __str__(self):
        return f"Вывод #{self.order}: {self.title}"

class AnswerConclusion(models.Model):
    """
    Связь между ответом и выводом
    """
    answer = models.OneToOneField(
        Answer, 
        on_delete=models.CASCADE,
        verbose_name='Ответ',
        related_name='conclusion_link'
    )
    conclusion = models.ForeignKey(
        Conclusion, 
        on_delete=models.CASCADE,
        verbose_name='Вывод',
        related_name='answer_links'
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Связь ответа с выводом'
        verbose_name_plural = 'Связи ответов с выводами'

    def __str__(self):
        return f"{self.answer.text} -> {self.conclusion.title}"

class UserSession(models.Model):
    """
    Сессия прохождения опросника пользователем (без регистрации)
    """
    session_key = models.CharField('Ключ сессии', max_length=40, db_index=True)
    questionnaire = models.ForeignKey(
        Questionnaire, 
        on_delete=models.CASCADE,
        verbose_name='Опросник'
    )
    current_question = models.ForeignKey(
        Question, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Текущий вопрос'
    )
    answers_history = models.JSONField('История ответов', default=list)
    completed = models.BooleanField('Завершен', default=False)
    conclusion = models.ForeignKey(
        Conclusion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Полученный вывод'
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Сессия пользователя'
        verbose_name_plural = 'Сессии пользователей'
        # unique_together = ['session_key', 'questionnaire']

    def __str__(self):
        return f"Сессия {self.session_key[:10]} - {self.questionnaire.name}"

class Payment(models.Model):
    """
    Платеж пользователя
    """
    PAYMENT_STATUS = [
        ('pending', 'Ожидание'),
        ('paid', 'Оплачено'),
        ('failed', 'Ошибка'),
        ('refunded', 'Возврат'),
    ]
    
    session = models.ForeignKey(
        UserSession,
        on_delete=models.CASCADE,
        verbose_name='Сессия',
        related_name='payments',
        null=True,
    )
    conclusion = models.ForeignKey(
        Conclusion,
        on_delete=models.CASCADE,
        verbose_name='Вывод'
    )
    amount = models.DecimalField('Сумма', max_digits=10, decimal_places=2)
    status = models.CharField('Статус', max_length=10, choices=PAYMENT_STATUS, default='pending')
    payment_id = models.CharField('ID платежа', max_length=100, blank=True)
    email = models.EmailField('Email для отправки', blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    paid_at = models.DateTimeField('Дата оплаты', null=True, blank=True)

    class Meta:
        verbose_name = 'Платеж'
        verbose_name_plural = 'Платежи'
        ordering = ['-created_at']

    def __str__(self):
        return f"Платеж #{self.id} - {self.status}"


class DocumentTemplate(models.Model):
    """
    Шаблон документа для PDF
    """
    TEMPLATE_TYPES = [
        ('claim', 'Исковое заявление'),
        ('complaint', 'Жалоба'),
        ('petition', 'Ходатайство'),
        ('statement', 'Заявление'),
        ('agreement', 'Соглашение'),
        ('objection', 'Возражение'),
        ('appeal', 'Апелляционная жалоба'),
        ('letter', 'Письмо'),
        ('other', 'Другое'),
    ]
    
    name = models.CharField('Название шаблона', max_length=200)
    template_type = models.CharField('Тип документа', max_length=20, choices=TEMPLATE_TYPES, default='other')
    description = models.TextField('Описание', blank=True)
    
    # HTML шаблон с переменными в формате {{ переменная }}
    html_template = models.TextField('HTML шаблон', help_text='Используйте {{ full_name }}, {{ address }}, {{ phone }}, {{ email }} и другие переменные')
    
    # CSS стили
    css_styles = models.TextField('CSS стили', blank=True, default='''
        body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
        h1 { color: #1a1a2e; font-size: 18pt; text-align: center; }
        .header { text-align: right; margin-bottom: 30px; }
        .content { line-height: 1.6; }
        .footer { margin-top: 50px; text-align: right; }
        .signature { margin-top: 30px; }
        .variable { color: #007bff; background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }
    ''')
    
    # Переменные, которые использует шаблон
    variables = models.JSONField('Переменные', default=list, help_text='Список переменных, например: ["full_name", "address", "phone"]')
    
    # Связь с выводом (какой вывод использует этот шаблон)
    conclusion = models.ForeignKey(
        Conclusion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Вывод',
        related_name='templates'
    )
    
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Шаблон документа'
        verbose_name_plural = 'Шаблоны документов'
        ordering = ['name']

    def __str__(self):
        return self.name
    
    def get_variable_list(self):
        """Возвращает список переменных из шаблона"""
        import re
        # Ищем все {{ переменные }}
        variables = re.findall(r'{{(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*)}}', self.html_template)
        return [v.strip() for v in variables]


class GeneratedDocument(models.Model):
    """
    Сгенерированный документ для пользователя
    """
    user_session = models.ForeignKey(
        UserSession,
        on_delete=models.CASCADE,
        verbose_name='Сессия пользователя',
        related_name='documents'
    )
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Шаблон'
    )
    conclusion = models.ForeignKey(
        Conclusion,
        on_delete=models.CASCADE,
        verbose_name='Вывод'
    )
    
    # Данные пользователя в момент генерации
    user_data = models.JSONField('Данные пользователя', default=dict)
    
    # Сгенерированный PDF файл
    pdf_file = models.FileField('PDF файл', upload_to='documents/pdfs/%Y/%m/%d/', blank=True, null=True)
    
    # Текст документа (для отображения)
    content_text = models.TextField('Текст документа', blank=True)
    
    status = models.CharField('Статус', max_length=20, default='pending', 
                             choices=[('pending', 'В процессе'), ('ready', 'Готов'), ('failed', 'Ошибка')])
    
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    downloaded_at = models.DateTimeField('Дата скачивания', null=True, blank=True)

    class Meta:
        verbose_name = 'Сгенерированный документ'
        verbose_name_plural = 'Сгенерированные документы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Документ #{self.id} - {self.conclusion.title[:30]}"    

class AIRules(models.Model):
    """
    Свод правил для AI - настраивается администратором
    """
    RULE_TYPES = [
        ('questionnaire', 'Генерация опросников'),
        ('consultation', 'Генерация консультаций'),
        ('document', 'Генерация документов'),
        ('conclusion', 'Генерация выводов'),
        ('general', 'Общие правила'),
    ]
    
    name = models.CharField('Название правила', max_length=200)
    rule_type = models.CharField('Тип правила', max_length=20, choices=RULE_TYPES, default='general')
    description = models.TextField('Описание', blank=True)
    
    rules_text = models.TextField(
        'Свод правил',
        help_text='Инструкция для AI. Используйте {{ topic }}, {{ category }} для подстановки'
    )
    
    prompt_template = models.TextField(
        'Шаблон промпта',
        help_text='Шаблон запроса к AI. Используйте {{ rules }} для вставки правил, {{ topic }} для темы',
        blank=True
    )
    
    examples = models.JSONField(
        'Примеры',
        default=list,
        help_text='Примеры для обучения AI (few-shot)',
        blank=True
    )
    
    variables = models.JSONField('Переменные', default=list, blank=True)
    priority = models.IntegerField('Приоритет', default=0)
    is_active = models.BooleanField('Активно', default=True)
    is_default = models.BooleanField('По умолчанию', default=False)
    
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Правило для AI'
        verbose_name_plural = 'Правила для AI'
        ordering = ['-priority', 'name']

    def __str__(self):
        return f"{self.get_rule_type_display()}: {self.name}"

    def get_rules_with_variables(self, context=None):
        """Возвращает правила с подставленными переменными"""
        text = self.rules_text
        if context:
            for key, value in context.items():
                text = text.replace(f'{{{{ {key} }}}}', str(value))
                text = text.replace(f'{{{{{key}}}}}', str(value))
        return text

    def get_prompt(self, context=None):
        """Возвращает полный промпт с правилами и контекстом"""
        if self.prompt_template:
            prompt = self.prompt_template
            rules = self.get_rules_with_variables(context)
            prompt = prompt.replace('{{ rules }}', rules)
            if context:
                for key, value in context.items():
                    prompt = prompt.replace(f'{{{{ {key} }}}}', str(value))
                    prompt = prompt.replace(f'{{{{{key}}}}}', str(value))
            return prompt
        return self.get_rules_with_variables(context)


class UserDocumentData(models.Model):
    """Данные пользователя для заполнения документов"""
    session = models.ForeignKey(
        UserSession,
        on_delete=models.CASCADE,
        verbose_name='Сессия',
        related_name='document_data'
    )
    conclusion = models.ForeignKey(
        Conclusion,
        on_delete=models.CASCADE,
        verbose_name='Вывод',
        related_name='user_data_entries',
        null=True,
        blank=True
    )
    
    # Данные хранятся в JSON
    data = models.JSONField('Данные пользователя', default=dict)
    
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Данные пользователя'
        verbose_name_plural = 'Данные пользователей'

    def __str__(self):
        return f"Данные пользователя #{self.id}"    