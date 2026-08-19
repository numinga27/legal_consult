"""
Интеграция с AI API (OpenAI, YandexGPT, Mock)
Поддерживает правила от администратора для настройки поведения AI
"""

import json
import re
import logging
import random
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


class AIConsultant:
    """
    Класс для работы с AI с поддержкой YandexGPT, OpenAI и Mock
    """
    
    def __init__(self, api_type: str = 'mock', api_key: Optional[str] = None):
        """
        Инициализация AI консультанта
        
        Args:
            api_type: 'openai', 'yandex', 'mock'
            api_key: API ключ для сервиса
        """
        self.api_type = api_type
        self.api_key = api_key or getattr(settings, 'YANDEX_API_KEY', None) or getattr(settings, 'OPENAI_API_KEY', None)
        self.folder_id = getattr(settings, 'YANDEX_FOLDER_ID', None)
        
        # Настройки провайдеров
        self.providers = {
            'openai': {
                'url': 'https://api.openai.com/v1/chat/completions',
                'model': getattr(settings, 'OPENAI_MODEL', 'gpt-4-turbo-preview'),
                'headers': {'Authorization': f'Bearer {self.api_key}'}
            },
            'yandex': {
                'url': 'https://llm.api.cloud.yandex.net/v2/inference',
                'model': getattr(settings, 'YANDEX_MODEL', 'yandexgpt-lite'),
                'headers': {
                    'Authorization': f'Api-Key {self.api_key}',
                    'x-folder-id': self.folder_id,
                    'Content-Type': 'application/json'
                }
            },
            'mock': {
                'url': None,
                'model': 'mock',
                'headers': {}
            }
        }
        
        # База знаний для мок-режима
        self.mock_knowledge_base = self._init_mock_knowledge_base()
    
    def _init_mock_knowledge_base(self) -> Dict[str, Any]:
        """Инициализирует базу знаний для мок-режима"""
        return {
            'судебный приказ': {
                'questions': [
                    {
                        'id': 1,
                        'text': 'Вы получили судебный приказ?',
                        'help_text': 'Проверьте почту или узнайте в суде',
                        'answers': [
                            {
                                'text': 'Да',
                                'next_question': 2,
                                'intermediate': 'Судебный приказ - это упрощенное судебное решение. Важно проверить сроки обжалования. Срок для подачи возражений составляет 10 дней с момента получения приказа (ст. 129 ГПК РФ).',
                                'is_final': False
                            },
                            {
                                'text': 'Нет',
                                'next_question': None,
                                'intermediate': 'Если судебный приказ не получен, процедура отмены не требуется. Возможно, вы имеете в виду другой документ.',
                                'is_final': True
                            }
                        ]
                    },
                    {
                        'id': 2,
                        'text': 'Пропущен ли срок для подачи возражений?',
                        'help_text': 'Срок составляет 10 дней с момента получения приказа',
                        'answers': [
                            {
                                'text': 'Да, пропущен',
                                'next_question': 3,
                                'intermediate': 'Пропуск срока - серьезное препятствие, но можно подать ходатайство о восстановлении срока при наличии уважительных причин (ст. 112 ГПК РФ).',
                                'is_final': False
                            },
                            {
                                'text': 'Нет, не пропущен',
                                'next_question': None,
                                'intermediate': 'У вас есть право подать возражения в установленный законом срок. Рекомендуем не откладывать и подать возражения как можно скорее.',
                                'is_final': True
                            }
                        ]
                    },
                    {
                        'id': 3,
                        'text': 'Есть ли уважительные причины для восстановления срока?',
                        'help_text': 'Болезнь, командировка, неполучение приказа и др.',
                        'answers': [
                            {
                                'text': 'Да, есть',
                                'next_question': None,
                                'intermediate': 'При наличии уважительных причин срок может быть восстановлен судом. Необходимо подать ходатайство о восстановлении срока вместе с возражениями.',
                                'is_final': True
                            },
                            {
                                'text': 'Нет, нет',
                                'next_question': None,
                                'intermediate': 'Без уважительных причин восстановление срока невозможно. Рекомендуем обратиться к юристу для оценки иных вариантов защиты.',
                                'is_final': True
                            }
                        ]
                    }
                ],
                'conclusions': [
                    {
                        'id': 1,
                        'title': 'Отмена судебного приказа возможна',
                        'short': 'Вы можете отменить судебный приказ, подав возражения в 10-дневный срок с момента получения.',
                        'full': """ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Подготовьте возражения на судебный приказ
   - Укажите причины несогласия с приказом
   - Приложите подтверждающие документы

2. Соберите необходимые документы:
   - Копия судебного приказа
   - Документы, подтверждающие вашу позицию
   - Доверенность (если через представителя)

3. Подайте возражения в суд:
   - В суд, который вынес приказ
   - Лично, по почте или через электронную подачу

4. Дождитесь рассмотрения (5-10 дней)

Основание: ст. 129 ГПК РФ - отмена судебного приказа""",
                        'pros': [
                            '✓ Вы можете защитить свои права в упрощенном порядке',
                            '✓ Процедура не требует уплаты госпошлины',
                            '✓ Возможно восстановление срока при уважительных причинах'
                        ],
                        'cons': [
                            '✗ Строгие сроки - всего 10 дней',
                            '✗ Нужны убедительные доказательства',
                            '✗ Может потребоваться помощь юриста'
                        ],
                        'success_rate': 85,
                        'price': 1990,
                        'documents': ['Возражение на судебный приказ.docx', 'Ходатайство о восстановлении срока.docx']
                    },
                    {
                        'id': 2,
                        'title': 'Отмена судебного приказа невозможна (срок пропущен)',
                        'short': 'Срок для подачи возражений пропущен без уважительных причин. Отмена судебного приказа невозможна.',
                        'full': """К сожалению, без уважительных причин восстановление срока невозможно.

АЛЬТЕРНАТИВНЫЕ ВАРИАНТЫ:
1. Обжаловать приказ в кассационном порядке
2. Подать новый иск с другими основаниями
3. Урегулировать вопрос добровольно с взыскателем
4. Обратиться к юристу для оценки перспектив

Рекомендация: не откладывайте обращение к специалисту, так как сроки могут быть упущены.""",
                        'pros': [
                            '✓ Можно обжаловать в кассации'
                        ],
                        'cons': [
                            '✗ Процесс займет больше времени',
                            '✗ Нужен профессиональный юрист',
                            '✗ Дополнительные судебные расходы'
                        ],
                        'success_rate': 15,
                        'price': 0,
                        'documents': ['Кассационная жалоба.docx']
                    },
                    {
                        'id': 3,
                        'title': 'Отмена судебного приказа возможна (восстановление срока)',
                        'short': 'Вы можете восстановить срок и подать возражения на судебный приказ.',
                        'full': """ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Подготовьте ходатайство о восстановлении срока
   - Укажите уважительные причины
   - Приложите подтверждающие документы

2. Подготовьте возражения на судебный приказ
   - Укажите основания несогласия
   - Приложите доказательства

3. Подайте документы в суд
   - Вместе с ходатайством и возражениями
   - В суд, вынесший приказ

4. Дождитесь решения суда

Основание: ст. 112 ГПК РФ - восстановление процессуальных сроков""",
                        'pros': [
                            '✓ Есть реальный шанс восстановить срок',
                            '✓ Возможно защитить свои права',
                            '✓ Суд рассматривает уважительные причины'
                        ],
                        'cons': [
                            '✗ Нужны убедительные доказательства причин',
                            '✗ Суд может отказать в восстановлении',
                            '✗ Требуется юридическая грамотность'
                        ],
                        'success_rate': 70,
                        'price': 2490,
                        'documents': ['Ходатайство о восстановлении срока.docx', 'Возражения на судебный приказ.docx']
                    }
                ]
            },
            'развод': {
                'questions': [
                    {
                        'id': 1,
                        'text': 'Вы состоите в официальном браке?',
                        'help_text': 'Официальный брак, зарегистрированный в ЗАГСе',
                        'answers': [
                            {
                                'text': 'Да',
                                'next_question': 2,
                                'intermediate': 'Официальный брак дает права на раздел имущества (ст. 34 СК РФ) и алименты (ст. 80 СК РФ).',
                                'is_final': False
                            },
                            {
                                'text': 'Нет',
                                'next_question': None,
                                'intermediate': 'Развод не требуется, так как вы не состояли в официальном браке. Однако возможно установление отцовства и взыскание алиментов.',
                                'is_final': True
                            }
                        ]
                    },
                    {
                        'id': 2,
                        'text': 'У вас есть совместно нажитое имущество?',
                        'help_text': 'Имущество, приобретенное во время брака',
                        'answers': [
                            {
                                'text': 'Да, есть',
                                'next_question': 3,
                                'intermediate': 'Совместно нажитое имущество делится между супругами поровну (ст. 39 СК РФ), если иное не предусмотрено брачным договором.',
                                'is_final': False
                            },
                            {
                                'text': 'Нет',
                                'next_question': None,
                                'intermediate': 'Если совместно нажитого имущества нет, раздел не требуется. Бракоразводный процесс проходит упрощенно.',
                                'is_final': True
                            }
                        ]
                    },
                    {
                        'id': 3,
                        'text': 'Есть ли спор о разделе имущества?',
                        'help_text': 'Спор означает, что вы не можете договориться мирно',
                        'answers': [
                            {
                                'text': 'Да, есть спор',
                                'next_question': None,
                                'intermediate': 'Спор о разделе имущества решается в судебном порядке. Рекомендуем обратиться к юристу для составления иска.',
                                'is_final': True
                            },
                            {
                                'text': 'Нет, договорились',
                                'next_question': None,
                                'intermediate': 'Можно заключить мировое соглашение или брачный договор, что значительно упростит процедуру.',
                                'is_final': True
                            }
                        ]
                    }
                ],
                'conclusions': [
                    {
                        'id': 1,
                        'title': 'Развод с разделом имущества (судебный порядок)',
                        'short': 'Расторжение брака с разделом имущества в судебном порядке. Срок рассмотрения: 1-3 месяца.',
                        'full': """ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Подайте исковое заявление о разводе и разделе имущества
   - В суд по месту жительства ответчика
   - Укажите все имущество, подлежащее разделу

2. Приложите необходимые документы:
   - Свидетельство о браке
   - Свидетельства о рождении детей (при наличии)
   - Документы на имущество
   - Квитанция об оплате госпошлины

3. Участвуйте в судебных заседаниях
   - Представляйте доказательства
   - Заявляйте ходатайства

4. Получите решение суда

Основание: ст. 21-24 СК РФ, ст. 34-39 СК РФ""",
                        'pros': [
                            '✓ Четкое разделение имущества по закону',
                            '✓ Защита прав каждого супруга',
                            '✓ Возможность оспорить решение'
                        ],
                        'cons': [
                            '✗ Длительный процесс (1-3 месяца)',
                            '✗ Оплата госпошлины',
                            '✗ Может потребоваться юрист'
                        ],
                        'success_rate': 80,
                        'price': 2990,
                        'documents': ['Исковое заявление о разводе и разделе имущества.docx', 'Соглашение о разделе имущества.docx']
                    },
                    {
                        'id': 2,
                        'title': 'Развод без раздела имущества (упрощенный)',
                        'short': 'Упрощенный развод при отсутствии спора об имуществе. Срок: 1 месяц.',
                        'full': """ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. При обоюдном согласии - подайте заявление в ЗАГС
   - Заявление по форме №9 или №10
   - Паспорта супругов
   - Свидетельство о браке
   - Квитанция об оплате госпошлины

2. При отсутствии согласия - подайте иск в суд
   - Заявление о расторжении брака
   - Документы по списку

3. Получите решение

Основание: ст. 19-20 СК РФ""",
                        'pros': [
                            '✓ Быстрая процедура (до 1 месяца)',
                            '✓ Минимальные затраты',
                            '✓ Не требуется судебное разбирательство'
                        ],
                        'cons': [
                            '✗ Требуется обоюдное согласие',
                            '✗ Нет раздела имущества',
                            '✗ Вопросы детей решаются отдельно'
                        ],
                        'success_rate': 95,
                        'price': 1490,
                        'documents': ['Заявление о расторжении брака.docx']
                    },
                    {
                        'id': 3,
                        'title': 'Развод с разделом имущества (добровольное соглашение)',
                        'short': 'Развод с добровольным соглашением о разделе имущества. Быстро и без суда.',
                        'full': """ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Заключите соглашение о разделе имущества
   - Добровольное соглашение
   - Нотариальное удостоверение (по желанию)

2. Подайте заявление о разводе в ЗАГС
   - С приложением соглашения

3. Получите свидетельство о разводе

Основание: ст. 40-44 СК РФ""",
                        'pros': [
                            '✓ Быстрая процедура',
                            '✓ Гибкие условия раздела',
                            '✓ Экономия на судебных расходах'
                        ],
                        'cons': [
                            '✗ Требуется добровольное согласие',
                            '✗ Нотариальные расходы'
                        ],
                        'success_rate': 90,
                        'price': 1990,
                        'documents': ['Соглашение о разделе имущества.docx', 'Брачный договор.docx']
                    }
                ]
            }
        }
    
    def _get_rules(self, rule_type: str = 'general') -> Optional[Any]:
        """Получает активные правила для заданного типа"""
        try:
            from .models import AIRules
            rule = AIRules.objects.filter(
                rule_type=rule_type,
                is_active=True,
                is_default=True
            ).first()
            if not rule:
                rule = AIRules.objects.filter(
                    rule_type=rule_type,
                    is_active=True
                ).order_by('-priority').first()
            return rule
        except Exception as e:
            logger.error(f"Error getting rules: {e}")
            return None
    
    def _get_prompt_with_rules(self, rule_type: str, context: Dict[str, Any]) -> str:
        """Формирует промпт с использованием правил"""
        try:
            rule = self._get_rules(rule_type)
            if rule:
                return rule.get_prompt(context)
        except Exception as e:
            logger.error(f"Error getting prompt with rules: {e}")
        return self._get_default_prompt(rule_type, context)
    
    def _get_default_prompt(self, rule_type: str, context: Dict[str, Any]) -> str:
        """Стандартный промпт, если правила не найдены"""
        if rule_type == 'questionnaire':
            return f"""
Ты - профессиональный юрист-консультант с 20-летним опытом. Создай юридический опросник.

Тема: {context.get('topic', '')}
Категория: {context.get('category', '')}
Дополнительные инструкции: {context.get('instructions', '')}

ТРЕБОВАНИЯ:
1. 3-5 вопросов с вариантами ответов
2. К каждому ответу - промежуточная консультация
3. 2-3 вывода с кратким и полным текстом
4. Список документов для каждого вывода

Верни ответ в формате JSON.
"""
        elif rule_type == 'consultation':
            return f"""
Дай краткую юридическую консультацию.

Вопрос: {context.get('question', '')}
Ответ: {context.get('answer', '')}
Контекст: {context.get('context', '')}

Требования:
- 1-3 предложения
- Объясни важность
- Ссылка на закон (опционально)
"""
        elif rule_type == 'document':
            return f"""
Составь юридический документ.

Тип: {context.get('document_type', '')}
Данные: {context.get('user_data', '')}
Вывод: {context.get('conclusion', '')}

Требования:
1. Правильная структура
2. Ссылки на законы
3. Места для заполнения [в квадратных скобках]
"""
        else:
            return "Создай юридическую консультацию на основе предоставленных данных."
    
    def _call_ai_api(self, prompt: str, system_prompt: str = '') -> str:
        """
        Вызов AI API с поддержкой разных провайдеров
        """
        if self.api_type == 'openai' and self.api_key:
            return self._call_openai(prompt, system_prompt)
        elif self.api_type == 'yandex' and self.api_key:
            return self._call_yandex(prompt, system_prompt)
        else:
            logger.info(f"Using mock mode for AI request")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
    
    def _call_openai(self, prompt: str, system_prompt: str = '') -> str:
        """
        Вызов OpenAI API
        """
        try:
            import openai
            openai.api_key = self.api_key
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({"role": "system", "content": "Ты профессиональный юрист-консультант с 20-летним опытом."})
            
            messages.append({"role": "user", "content": prompt})
            
            response = openai.ChatCompletion.create(
                model=self.providers['openai']['model'],
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                timeout=30
            )
            return response.choices[0].message.content
        except ImportError:
            logger.error("OpenAI library not installed. Run: pip install openai")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
    
    def _call_yandex(self, prompt: str, system_prompt: str = '') -> str:
        """
        Вызов YandexGPT API
        """
        try:
            import requests
            
            # Формируем сообщения
            messages = []
            if system_prompt:
                messages.append({
                    "role": "system",
                    "text": system_prompt
                })
            else:
                messages.append({
                    "role": "system",
                    "text": "Ты профессиональный юрист-консультант с 20-летним опытом. Отвечай на русском языке."
                })
            
            messages.append({
                "role": "user",
                "text": prompt
            })
            
            # Заголовки
            headers = self.providers['yandex']['headers']
            
            # Тело запроса
            data = {
                "model": self.providers['yandex']['model'],
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 2000
            }
            
            # Если есть folder_id, добавляем его
            if self.folder_id:
                data["folder_id"] = self.folder_id
            
            # Отправляем запрос
            response = requests.post(
                self.providers['yandex']['url'],
                headers=headers,
                json=data,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Извлекаем текст ответа
            if 'result' in result and 'alternatives' in result['result']:
                return result['result']['alternatives'][0]['message']['text']
            else:
                logger.error(f"Unexpected YandexGPT response: {result}")
                return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
                
        except ImportError:
            logger.error("Requests library not installed. Run: pip install requests")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
        except requests.exceptions.RequestException as e:
            logger.error(f"YandexGPT API request error: {e}")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
        except Exception as e:
            logger.error(f"YandexGPT API error: {e}")
            return json.dumps(self._generate_mock_questionnaire('тест', 'general'))
    
    def generate_questionnaire(self, topic: str, category: str, 
                               instructions: str = '') -> Dict[str, Any]:
        """
        Генерирует полный опросник по теме
        
        Args:
            topic: Тема опросника
            category: Категория
            instructions: Дополнительные инструкции
        
        Returns:
            Dict с вопросами, ответами и выводами
        """
        logger.info(f"Генерация опросника для темы: {topic}")
        
        # Проверяем, есть ли в базе знаний (для мок-режима)
        topic_lower = topic.lower()
        for key in self.mock_knowledge_base:
            if key in topic_lower:
                return self.mock_knowledge_base[key]
        
        context = {
            'topic': topic,
            'category': category,
            'instructions': instructions
        }
        
        # Если мок-режим - возвращаем из базы знаний
        if self.api_type == 'mock':
            return self._generate_mock_questionnaire(topic, category)
        
        # Для реальных API - отправляем запрос
        prompt = self._get_prompt_with_rules('questionnaire', context)
        system_prompt = "Ты профессиональный юрист-консультант с 20-летним опытом. Отвечай на русском языке. Возвращай ответ строго в формате JSON."
        response = self._call_ai_api(prompt, system_prompt)
        return self._parse_ai_response(response)
    
    def _generate_mock_questionnaire(self, topic: str, category: str) -> Dict[str, Any]:
        """Генерирует базовый мок-опросник, если тема не найдена в базе знаний"""
        return {
            'questions': [
                {
                    'id': 1,
                    'text': f'Какая у вас юридическая проблема?',
                    'help_text': 'Опишите кратко вашу ситуацию',
                    'answers': [
                        {
                            'text': 'Это моя проблема',
                            'next_question': None,
                            'intermediate': 'Мы поможем вам разобраться. На основе вашего ответа мы подготовим консультацию.',
                            'is_final': True
                        },
                        {
                            'text': 'Это не моя проблема',
                            'next_question': None,
                            'intermediate': 'Выберите другую тему из списка на главной странице.',
                            'is_final': True
                        }
                    ]
                }
            ],
            'conclusions': [
                {
                    'id': 1,
                    'title': f'Консультация по теме: {topic}',
                    'short': f'Краткий вывод по вашей ситуации.',
                    'full': f"""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Обратитесь к юристу для детальной консультации
2. Соберите все необходимые документы
3. Следуйте полученным рекомендациям

По вашей проблеме: {topic}

Рекомендуем не откладывать решение вопроса, так как сроки могут быть ограничены.""",
                    'pros': ['Индивидуальный подход', 'Профессиональная помощь'],
                    'cons': ['Требуется уточнение деталей', 'Возможны дополнительные расходы'],
                    'success_rate': 70,
                    'price': 1490,
                    'documents': ['Юридическая консультация.docx']
                }
            ]
        }
    
    def generate_intermediate_consultation(self, question: str, answer: str, 
                                           context: str = '') -> str:
        """
        Генерирует промежуточную консультацию для ответа
        
        Args:
            question: Текст вопроса
            answer: Текст ответа
            context: Дополнительный контекст
        
        Returns:
            Текст промежуточной консультации
        """
        logger.info(f"Генерация промежуточной консультации для: {answer}")
        
        if self.api_type == 'mock':
            return self._mock_intermediate_consultation(question, answer)
        
        context_data = {
            'question': question,
            'answer': answer,
            'context': context
        }
        
        prompt = self._get_prompt_with_rules('consultation', context_data)
        response = self._call_ai_api(prompt)
        return self._extract_text(response)
    
    def _mock_intermediate_consultation(self, question: str, answer: str) -> str:
        """Мок-генерация промежуточной консультации"""
        templates = [
            f"Вы выбрали вариант '{answer}'. Это важный фактор для решения вашей юридической проблемы. Данный ответ определяет дальнейшую стратегию защиты ваших прав.",
            f"Ваш ответ '{answer}' показывает, что в вашей ситуации есть ключевые нюансы, требующие внимания. Рекомендуем обратить внимание на документы, подтверждающие вашу позицию.",
            f"На основе вашего ответа '{answer}' можно сделать предварительный вывод о вашем положении. Это влияет на выбор оптимального способа защиты ваших прав.",
            f"Фактор, обозначенный вами как '{answer}', является определяющим для дальнейшего юридического анализа. Учтите это при сборе документов.",
        ]
        return random.choice(templates)
    
    def generate_full_conclusion(self, answers: List[Dict], problem: str) -> Dict[str, Any]:
        """
        Генерирует полный вывод на основе ответов пользователя
        
        Args:
            answers: Список ответов пользователя
            problem: Описание проблемы
        
        Returns:
            Dict с выводом
        """
        logger.info(f"Генерация полного вывода на основе {len(answers)} ответов")
        
        if self.api_type == 'mock':
            return self._mock_conclusion(answers, problem)
        
        context = {
            'answers': json.dumps(answers, ensure_ascii=False),
            'problem': problem
        }
        
        prompt = self._get_prompt_with_rules('conclusion', context)
        response = self._call_ai_api(prompt)
        return self._parse_conclusion_response(response)
    
    def _mock_conclusion(self, answers: List[Dict], problem: str) -> Dict[str, Any]:
        """Мок-генерация вывода"""
        answer_text = "\n".join([
            f"Вопрос: {a.get('question', '')}\nОтвет: {a.get('answer', '')}"
            for a in answers
        ])
        
        return {
            'title': 'Юридический вывод по вашей ситуации',
            'short': 'На основе предоставленных ответов сформирован предварительный вывод. Для получения полной консультации обратитесь к юристу.',
            'full': f"""ПОШАГОВЫЙ ПЛАН ДЕЙСТВИЙ:

1. Проанализируйте полученную информацию
2. Соберите следующие документы:
   - Паспорт
   - Документы по делу
   - Другие подтверждающие документы

3. Обратитесь к юристу для детальной консультации
4. Следуйте полученным рекомендациям

По вашей проблеме: {problem}

Ваши ответы:
{answer_text}""",
            'pros': ['Есть возможность защитить свои права', 'Закон предоставляет инструменты защиты'],
            'cons': ['Требуется профессиональная помощь', 'Возможны судебные расходы'],
            'success_rate': 75,
            'documents': ['Образец документа.docx', 'Список необходимых документов.docx']
        }
    
    
    def generate_document(self, document_type: str, user_data: Dict[str, Any],
                         conclusion_text: str) -> Dict[str, Any]:
        """
        Генерирует юридический документ
        
        Args:
            document_type: Тип документа
            user_data: Данные пользователя
            conclusion_text: Текст вывода
        
        Returns:
            Dict с документом
        """
        logger.info(f"Генерация документа типа: {document_type}")
        
        if self.api_type == 'mock':
            return self._mock_document(document_type, user_data)
        
        context = {
            'document_type': document_type,
            'user_data': json.dumps(user_data, ensure_ascii=False),
            'conclusion': conclusion_text
        }
        
        prompt = self._get_prompt_with_rules('document', context)
        response = self._call_ai_api(prompt)
        return self._parse_document_response(response)
    
    def _mock_document(self, document_type: str, user_data: Dict) -> Dict[str, Any]:
        """Генерирует мок-документ"""
        templates = {
            'claim': '''В [Название суда]
Адрес: [Адрес суда]

Истец: {full_name}
Адрес: {address}
Телефон: {phone}
Email: {email}

Ответчик: [ФИО ответчика]
Адрес: [Адрес ответчика]

ИСКОВОЕ ЗАЯВЛЕНИЕ

[Описание ситуации]

На основании ст. [номер статьи] ГК РФ,

ПРОШУ:
1. [Требование 1]
2. [Требование 2]

Приложения:
1. Копия искового заявления
2. Квитанция об оплате госпошлины
3. Копии документов

Дата: {current_date}
Подпись: ______________
''',
            'complaint': '''[Название органа]
Адрес: [Адрес органа]

От: {full_name}
Адрес: {address}
Телефон: {phone}
Email: {email}

ЖАЛОБА

[Описание нарушения]

На основании ст. [номер статьи],

ПРОШУ:
1. [Требование]

Дата: {current_date}
Подпись: ______________
''',
            'statement': '''[Название органа]
Адрес: [Адрес органа]

От: {full_name}
Адрес: {address}
Телефон: {phone}
Email: {email}

ЗАЯВЛЕНИЕ

Прошу [описание просьбы]

Основание: [основание]

Приложения:
1. [Документ 1]
2. [Документ 2]

Дата: {current_date}
Подпись: ______________
'''
        }
        
        # Получаем шаблон
        template = templates.get(document_type, templates['statement'])
        
        # Заполняем данные пользователя
        data = {
            'full_name': user_data.get('full_name', '[ФИО не указано]'),
            'address': user_data.get('address', '[Адрес не указан]'),
            'phone': user_data.get('phone', '[Телефон не указан]'),
            'email': user_data.get('email', '[Email не указан]'),
            'current_date': datetime.now().strftime('%d.%m.%Y')
        }
        
        for key, value in data.items():
            template = template.replace(f'{{{key}}}', str(value))
        
        return {
            'title': f'{document_type}.docx',
            'content': template,
            'type': document_type
        }
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ от AI в JSON"""
        try:
            # Пытаемся найти JSON в ответе
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            return self._generate_mock_questionnaire('тест', 'general')
    
    def _extract_text(self, response: str) -> str:
        """Извлекает текст из ответа AI"""
        if isinstance(response, dict):
            return response.get('text', str(response))
        return str(response)
    
    def _parse_document_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ от AI для документа"""
        try:
            if isinstance(response, dict):
                return response
            return json.loads(response)
        except:
            return self._mock_document('claim', {})
    
    def _parse_conclusion_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ от AI для вывода"""
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse conclusion response: {e}")
            return self._mock_conclusion([], '')


# ============================================================
# ФАБРИКА ДЛЯ СОЗДАНИЯ AI КОНСУЛЬТАНТА
# ============================================================

def get_ai_consultant(api_type: str = 'mock', api_key: Optional[str] = None) -> AIConsultant:
    """
    Фабрика для создания AI консультанта
    
    Args:
        api_type: 'openai', 'yandex', 'mock'
        api_key: API ключ для сервиса
    
    Returns:
        AIConsultant: Экземпляр AI консультанта
    """
    return AIConsultant(api_type=api_type, api_key=api_key)