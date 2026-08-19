#!/usr/bin/env python
"""
Тестирование YandexGPT
Запуск: python test_yandex.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legal_consultant.settings')
django.setup()

from core.ai_integration import get_ai_consultant

def test_yandex():
    """Тестирует YandexGPT"""
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ YANDEXGPT")
    print("=" * 60)
    
    # Создаем AI консультанта с YandexGPT
    print("\n🔄 Создание AI консультанта...")
    ai = get_ai_consultant('yandex')
    print(f"   ✅ AI консультант создан (тип: {ai.api_type})")
    
    print("\n🔄 Отправка запроса к YandexGPT...")
    
    try:
        result = ai.generate_questionnaire(
            topic='Отмена судебного приказа',
            category='family_law',
            instructions='Создай подробный опросник'
        )
        
        print("\n📊 РЕЗУЛЬТАТ:")
        print("-" * 40)
        
        if result and result.get('questions'):
            print(f"✅ YandexGPT работает!")
            print(f"   Вопросов: {len(result['questions'])}")
            print(f"   Выводов: {len(result.get('conclusions', []))}")
            print("\n📋 Пример вопроса:")
            if result['questions']:
                print(f"   {result['questions'][0]['text']}")
                if result['questions'][0].get('answers'):
                    print("   Варианты ответов:")
                    for ans in result['questions'][0]['answers']:
                        print(f"     - {ans['text']}")
        else:
            print("❌ YandexGPT не вернул данные")
            print(f"   Ответ: {result}")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЕН")
    print("=" * 60)

if __name__ == '__main__':
    test_yandex()
