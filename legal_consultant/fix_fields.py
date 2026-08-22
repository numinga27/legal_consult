#!/usr/bin/env python
"""
Принудительное добавление полей для всех выводов
Запуск: python force_fix_fields.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.models import Conclusion

def force_fix():
    print("ПРИНУДИТЕЛЬНОЕ ДОБАВЛЕНИЕ ПОЛЕЙ")
    print("=" * 50)
    
    default_fields = [
        {"name": "full_name", "label": "ФИО", "type": "text", "required": True},
        {"name": "address", "label": "Адрес", "type": "text", "required": False},
        {"name": "phone", "label": "Телефон", "type": "tel", "required": False},
        {"name": "email", "label": "Email", "type": "email", "required": True}
    ]
    
    for c in Conclusion.objects.all():
        # Принудительно обновляем поля
        c.user_data_fields = default_fields
        c.save()
        print(f"[OK] Обновлен: {c.title}")
    
    print("=" * 50)
    print("ГОТОВО!")

if __name__ == '__main__':
    force_fix()