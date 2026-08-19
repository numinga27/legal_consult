#!/usr/bin/env python
"""
Добавление полей для сбора данных пользователя
Запуск: python manage.py runscript add_user_fields
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.models import Conclusion

def add_user_fields():
    """Добавляет поля для сбора данных ко всем выводам"""
    
    conclusions = Conclusion.objects.all()
    
    # Стандартные поля для всех выводов
    default_fields = [
        {"name": "full_name", "label": "ФИО", "type": "text", "required": True},
        {"name": "address", "label": "Адрес", "type": "text", "required": False},
        {"name": "phone", "label": "Телефон", "type": "tel", "required": False},
        {"name": "email", "label": "Email", "type": "email", "required": True},
    ]
    
    for conclusion in conclusions:
        if not conclusion.user_data_fields:
            conclusion.user_data_fields = default_fields
            conclusion.save()
            print(f"✅ Добавлены поля для вывода: {conclusion.title}")
        else:
            print(f"ℹ️ Поля уже есть для: {conclusion.title}")

if __name__ == '__main__':
    add_user_fields()