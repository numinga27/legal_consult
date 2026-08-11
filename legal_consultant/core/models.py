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
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

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
    short_text = models.TextField('Краткий вывод (бесплатно)')
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
        unique_together = ['session_key', 'questionnaire']

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
        related_name='payments'
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