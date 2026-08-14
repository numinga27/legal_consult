from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Админ-панель
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-logout/', views.admin_logout, name='admin_logout'),
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
    path('questionnaire/<int:q_id>/', views.user_questionnaire, name='user_questionnaire'),
    path('api/get-next-question/', views.api_get_next_question, name='api_get_next_question'),
    path('result/<int:conclusion_id>/', views.user_result, name='user_result'),
    path('payment/<int:conclusion_id>/', views.user_payment, name='user_payment'),
    path('payment-success/<int:payment_id>/', views.payment_success, name='payment_success'),
]