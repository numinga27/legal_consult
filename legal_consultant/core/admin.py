from django.contrib import admin
from django.utils.html import format_html
from .models import (
    LegalDirection, Questionnaire, Question, Answer, 
    Conclusion, AnswerConclusion, UserSession, Payment,
    DocumentTemplate, GeneratedDocument, AIRules  # AIRules должен быть здесь один раз
)


@admin.register(LegalDirection)
class LegalDirectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'description_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Описание'


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ['name', 'direction', 'is_active', 'questions_count', 'created_at']
    list_filter = ['direction', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    def questions_count(self, obj):
        return obj.questions.count()
    questions_count.short_description = 'Количество вопросов'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['order', 'text_preview', 'questionnaire', 'answers_count', 'created_at']
    list_filter = ['questionnaire', 'created_at']
    search_fields = ['text']
    readonly_fields = ['created_at']
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Вопрос'
    
    def answers_count(self, obj):
        return obj.answers.count()
    answers_count.short_description = 'Вариантов ответа'


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 1
    fields = ['text', 'answer_type', 'intermediate_text', 'next_question', 'order', 'is_final']
    raw_id_fields = ['next_question']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['text', 'question', 'answer_type', 'next_question_preview', 'is_final']
    list_filter = ['answer_type', 'is_final', 'question__questionnaire']
    search_fields = ['text', 'intermediate_text']
    raw_id_fields = ['question', 'next_question']
    
    def next_question_preview(self, obj):
        if obj.next_question:
            return f"Вопрос {obj.next_question.order}"
        if obj.is_final:
            return "→ Вывод"
        return "-"
    next_question_preview.short_description = 'Следующий вопрос'


@admin.register(Conclusion)
class ConclusionAdmin(admin.ModelAdmin):
    list_display = ['order', 'title', 'questionnaire', 'price', 'success_rate', 'created_at']
    list_filter = ['questionnaire', 'created_at']
    search_fields = ['title', 'short_text', 'full_text']
    readonly_fields = ['created_at']
    fieldsets = (
        # ... существующие поля ...
        ('Сбор данных пользователя', {
            'fields': ('user_data_fields',),
            'description': 'Укажите поля, которые пользователь должен заполнить. Формат JSON: [{"name": "full_name", "label": "ФИО", "type": "text", "required": true}]'
        }),
    )
    
    def document_link(self, obj):
        if obj.documents:
            return format_html('<a href="{}" target="_blank">Скачать</a>', obj.documents.url)
        return "Нет документа"
    document_link.short_description = 'Документ'


@admin.register(AnswerConclusion)
class AnswerConclusionAdmin(admin.ModelAdmin):
    list_display = ['answer', 'conclusion', 'created_at']
    list_filter = ['conclusion__questionnaire']
    raw_id_fields = ['answer', 'conclusion']


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'questionnaire', 'completed', 'current_question', 'updated_at']
    list_filter = ['completed', 'questionnaire', 'created_at']
    readonly_fields = ['session_key', 'created_at', 'updated_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'conclusion', 'amount', 'status', 'email', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['email', 'payment_id']
    readonly_fields = ['created_at']


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'template_type', 'is_active', 'created_at']
    list_filter = ['template_type', 'is_active']
    search_fields = ['name', 'description']
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'template_type', 'description', 'is_active')
        }),
        ('Шаблон документа', {
            'fields': ('html_template', 'css_styles'),
            'description': 'Используйте переменные в формате {{ variable_name }}'
        }),
        ('Переменные', {
            'fields': ('variables', 'conclusion'),
            'description': 'Переменные определяются автоматически из шаблона'
        }),
    )
    readonly_fields = ['created_at', 'updated_at']
    
    def save_model(self, request, obj, form, change):
        import re
        variables = re.findall(r'{{(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*)}}', obj.html_template)
        obj.variables = [v.strip() for v in variables]
        super().save_model(request, obj, form, change)


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'conclusion', 'status', 'created_at', 'downloaded_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at', 'downloaded_at', 'pdf_file']
    fields = ['user_session', 'template', 'conclusion', 'user_data', 'pdf_file', 'content_text', 'status', 'downloaded_at']


# ============ ПРАВИЛА ДЛЯ AI ============
# РЕГИСТРИРУЕМ ТОЛЬКО ОДИН РАЗ!

@admin.register(AIRules)
class AIRulesAdmin(admin.ModelAdmin):
    list_display = ['name', 'rule_type', 'is_active', 'is_default', 'priority', 'created_at']
    list_filter = ['rule_type', 'is_active', 'is_default']
    search_fields = ['name', 'description', 'rules_text']
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'rule_type', 'description', 'priority', 'is_active', 'is_default')
        }),
        ('Правила для AI', {
            'fields': ('rules_text', 'prompt_template'),
            'description': 'Инструкция для AI. Используйте переменные: {{ topic }}, {{ category }}, {{ instructions }}'
        }),
        ('Примеры и переменные', {
            'fields': ('examples', 'variables'),
            'description': 'Примеры для few-shot обучения и список используемых переменных'
        }),
    )
    readonly_fields = ['created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        if obj.is_default:
            AIRules.objects.filter(is_default=True).exclude(pk=obj.pk).update(is_default=False)
        super().save_model(request, obj, form, change)