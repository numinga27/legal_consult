#!/usr/bin/env python
"""
Создание шаблона документа
Запуск: python create_template.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.models import DocumentTemplate

def create_template():
    """Создает шаблон документа"""
    
    print("=" * 50)
    print("СОЗДАНИЕ ШАБЛОНА ДОКУМЕНТА")
    print("=" * 50)
    
    # Проверяем, есть ли уже шаблон
    existing = DocumentTemplate.objects.filter(name='Стандартный юридический документ').first()
    if existing:
        print(f"ℹ️ Шаблон уже существует: {existing.name}")
        return
    
    # HTML шаблон
    html_template = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
h1 { color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }
.header { text-align: right; margin-bottom: 30px; }
.content { line-height: 1.8; }
.footer { margin-top: 50px; text-align: right; }
.document-title { font-size: 20pt; font-weight: bold; text-align: center; margin: 30px 0; }
</style>
</head>
<body>
<div class="header">
    <p><strong>Дата:</strong> {{ current_date }}</p>
    <p><strong>ФИО:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
    <p><strong>Email:</strong> {{ email }}</p>
</div>

<div class="document-title">ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ</div>

<div class="content">
    <h3>{{ conclusion_title }}</h3>
    <p>{{ conclusion_full }}</p>
</div>

<div class="footer">
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
</div>
</body>
</html>"""
    
    # Создаем шаблон
    template = DocumentTemplate.objects.create(
        name='Стандартный юридический документ',
        template_type='claim',
        description='Стандартный шаблон юридического документа',
        is_active=True,
        variables=['full_name', 'address', 'phone', 'email', 'conclusion_full', 'current_date'],
        html_template=html_template
    )
    
    print(f"✅ Шаблон создан: {template.name}")
    print(f"   ID: {template.id}")
    print(f"   Переменные: {template.variables}")

if __name__ == '__main__':
    create_template()