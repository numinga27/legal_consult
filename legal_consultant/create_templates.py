#!/usr/bin/env python
"""
Скрипт для создания шаблонов документов
Запуск: python create_templates.py
"""

import os
import sys
import django

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.models import DocumentTemplate

def create_templates():
    """Создает шаблоны документов"""
    
    print("=" * 50)
    print("СОЗДАНИЕ ШАБЛОНОВ ДОКУМЕНТОВ")
    print("=" * 50)
    
    # Удаляем старые шаблоны (опционально)
    # DocumentTemplate.objects.all().delete()
    # print("🗑️ Старые шаблоны удалены")
    
    templates_data = [
        {
            'name': 'Стандартное исковое заявление',
            'template_type': 'claim',
            'description': 'Стандартный шаблон искового заявления для суда',
            'is_active': True,
            'variables': ['full_name', 'address', 'phone', 'email', 'conclusion_full', 'current_date'],
            'html_template': """<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<style>
  body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
  h1 { color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }
  .header { text-align: right; margin-bottom: 30px; }
  .content { line-height: 1.8; }
  .footer { margin-top: 50px; text-align: right; }
</style>
</head>
<body>
  <div class='header'>
    <p><strong>В [Название суда]</strong></p>
    <p>Адрес: [Адрес суда]</p>
    <p><br></p>
    <p><strong>Истец:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
    <p><strong>Email:</strong> {{ email }}</p>
  </div>

  <h1>ИСКОВОЕ ЗАЯВЛЕНИЕ</h1>

  <div class='content'>
    <p>{{ conclusion_full }}</p>
    
    <p>На основании вышеизложенного, в соответствии со статьей [номер статьи] ГК РФ,</p>
    
    <p><strong>ПРОШУ:</strong></p>
    <ol>
      <li>[Требование 1]</li>
      <li>[Требование 2]</li>
    </ol>
  </div>

  <div class='footer'>
    <p>Дата: {{ current_date }}</p>
    <p><br></p>
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
  </div>
</body>
</html>"""
        },
        {
            'name': 'Стандартная жалоба',
            'template_type': 'complaint',
            'description': 'Шаблон жалобы в вышестоящий орган',
            'is_active': True,
            'variables': ['full_name', 'address', 'phone', 'email', 'conclusion_full', 'current_date'],
            'html_template': """<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<style>
  body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
  h1 { color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }
  .header { text-align: right; margin-bottom: 30px; }
  .content { line-height: 1.8; }
  .footer { margin-top: 50px; text-align: right; }
</style>
</head>
<body>
  <div class='header'>
    <p><strong>В [Название органа]</strong></p>
    <p>Адрес: [Адрес органа]</p>
    <p><br></p>
    <p><strong>От:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
    <p><strong>Email:</strong> {{ email }}</p>
  </div>

  <h1>ЖАЛОБА</h1>

  <div class='content'>
    <p>{{ conclusion_full }}</p>
    
    <p>На основании статьи [номер статьи],</p>
    
    <p><strong>ПРОШУ:</strong></p>
    <ol>
      <li>[Требование]</li>
    </ol>
  </div>

  <div class='footer'>
    <p>Дата: {{ current_date }}</p>
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
  </div>
</body>
</html>"""
        },
        {
            'name': 'Стандартное ходатайство',
            'template_type': 'petition',
            'description': 'Шаблон ходатайства в суд',
            'is_active': True,
            'variables': ['full_name', 'address', 'phone', 'conclusion_full', 'current_date'],
            'html_template': """<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<style>
  body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
  h1 { color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }
  .header { text-align: right; margin-bottom: 30px; }
  .content { line-height: 1.8; }
  .footer { margin-top: 50px; text-align: right; }
</style>
</head>
<body>
  <div class='header'>
    <p><strong>В [Название суда]</strong></p>
    <p>Судья: [ФИО судьи]</p>
    <p><br></p>
    <p><strong>Заявитель:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
  </div>

  <h1>ХОДАТАЙСТВО</h1>

  <div class='content'>
    <p>{{ conclusion_full }}</p>
    
    <p><strong>ПРОШУ:</strong></p>
    <ol>
      <li>[Требование]</li>
    </ol>
  </div>

  <div class='footer'>
    <p>Дата: {{ current_date }}</p>
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
  </div>
</body>
</html>"""
        },
        {
            'name': 'Заявление в ЗАГС',
            'template_type': 'statement',
            'description': 'Шаблон заявления в ЗАГС',
            'is_active': True,
            'variables': ['full_name', 'address', 'phone', 'conclusion_full', 'current_date'],
            'html_template': """<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<style>
  body { font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }
  h1 { color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }
  .header { margin-bottom: 30px; }
  .content { line-height: 1.8; }
  .footer { margin-top: 50px; text-align: right; }
</style>
</head>
<body>
  <div class='header'>
    <p><strong>В ЗАГС [Название]</strong></p>
    <p>Адрес: [Адрес ЗАГСа]</p>
    <p><br></p>
    <p><strong>От:</strong> {{ full_name }}</p>
    <p><strong>Адрес:</strong> {{ address }}</p>
    <p><strong>Телефон:</strong> {{ phone }}</p>
  </div>

  <h1>ЗАЯВЛЕНИЕ</h1>

  <div class='content'>
    <p>{{ conclusion_full }}</p>
    
    <p><strong>ПРОШУ:</strong></p>
    <ol>
      <li>[Требование]</li>
    </ol>
  </div>

  <div class='footer'>
    <p>Дата: {{ current_date }}</p>
    <p>_________________________</p>
    <p><strong>Подпись:</strong> {{ full_name }}</p>
  </div>
</body>
</html>"""
        }
    ]
    
    created_count = 0
    for template_data in templates_data:
        # Проверяем, существует ли уже такой шаблон
        existing = DocumentTemplate.objects.filter(name=template_data['name']).first()
        if existing:
            print(f"ℹ️ Шаблон '{template_data['name']}' уже существует, пропускаем")
            continue
        
        # Создаем шаблон
        template = DocumentTemplate.objects.create(
            name=template_data['name'],
            template_type=template_data['template_type'],
            description=template_data['description'],
            html_template=template_data['html_template'],
            variables=template_data['variables'],
            is_active=template_data['is_active']
        )
        created_count += 1
        print(f"✅ Создан шаблон: {template.name}")
    
    print("\n" + "=" * 50)
    print(f"🎉 СОЗДАНО {created_count} НОВЫХ ШАБЛОНОВ")
    print("=" * 50)
    
    # Показываем все шаблоны
    all_templates = DocumentTemplate.objects.all()
    print(f"\n📋 Всего шаблонов в БД: {all_templates.count()}")
    for t in all_templates:
        print(f"  - {t.name} ({t.template_type}) - Активен: {t.is_active}")

if __name__ == '__main__':
    try:
        create_templates()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()