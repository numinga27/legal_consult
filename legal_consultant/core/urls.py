from django.urls import path
from . import views
from . import import_views, guided_views, help_views, owner_views
from .health import health

app_name = 'core'

urlpatterns = [
    path('healthz/', health, name='health'),
    path('guided/<int:q_id>/help/<int:bundle_index>/', help_views.select_help, name='select_help'),
    path('help/orders/', help_views.help_orders, name='help_orders'),
    path('help/orders/<uuid:order_id>/', help_views.help_order, name='help_order'),
    path('admin-import/', import_views.import_questionnaire, name='import_questionnaire'),
    path('admin-import/guide/', owner_views.import_guide, name='import_guide'),
    path('guided/<int:q_id>/', guided_views.guided_questionnaire, name='guided_questionnaire'),
    # Админ-панель
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-dashboard/', owner_views.owner_dashboard, name='admin_dashboard'),
    path('admin-logout/', views.admin_logout, name='admin_logout'),
    path('api/sync-workflow/', views.api_sync_workflow, name='api_sync_workflow'),
    path('api/load-workflow/<int:q_id>/', views.api_load_workflow, name='api_load_workflow'),
    path('visual-editor/<int:q_id>/', views.visual_editor, name='visual_editor'),
    path('api/save-workflow/', views.api_save_workflow, name='api_save_workflow'),
    path('admin-questionnaire/<int:q_id>/', views.admin_questionnaire, name='admin_questionnaire'),
    path('admin-questionnaire-add/', views.admin_add_questionnaire, name='admin_add_questionnaire'),
    path('admin-question-delete/<int:q_id>/', views.admin_delete_question, name='admin_delete_question'),
    path('admin-answer-delete/<int:a_id>/', views.admin_delete_answer, name='admin_delete_answer'),
    path('api/questionnaire/<int:q_id>/', views.api_questionnaire_data, name='api_questionnaire_data'),
    path('api/check-answer/', views.api_check_answer, name='api_check_answer'),
    # Пользовательская часть
    path('admin-test-rules/', views.admin_test_rules, name='admin_test_rules'),
    path('api/test-rules/', views.api_test_rules, name='api_test_rules'),
    path('admin-generate-ai/', views.admin_generate_with_ai, name='admin_generate_ai'),
    path('', views.user_select_problem, name='user_select_problem'),
    path('api/generate-document/', views.api_generate_document, name='api_generate_document'),
    path('questionnaire/<int:q_id>/', views.user_questionnaire, name='user_questionnaire'),
    path('api/get-next-question/', views.api_get_next_question, name='api_get_next_question'),
    path('result/<int:conclusion_id>/', views.user_result, name='user_result'),
    path('payment/<int:conclusion_id>/', views.user_payment, name='user_payment'),
    path('payment-success/<int:payment_id>/', views.payment_success, name='payment_success'),
]
