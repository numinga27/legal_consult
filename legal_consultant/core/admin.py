from django.contrib import admin
from django.utils.html import format_html
from .models import (
    LegalDirection, Questionnaire, Question, Answer, 
    Conclusion, AnswerConclusion, UserSession, Payment
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