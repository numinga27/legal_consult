"""
Генератор PDF документов с поддержкой кириллицы
"""

import io
import os
from datetime import datetime
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import logging

logger = logging.getLogger(__name__)

# Регистрируем шрифт с поддержкой кириллицы
def register_russian_font():
    """Регистрирует шрифт с поддержкой русского языка"""
    try:
        # Пробуем найти шрифт в разных местах
        font_paths = [
            '/System/Library/Fonts/Supplemental/Arial.ttf',  # Mac
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
            'C:/Windows/Fonts/arial.ttf',  # Windows
            os.path.expanduser('~/.fonts/DejaVuSans.ttf'),  # User fonts
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont('DejaVuSans', path))
                logger.info(f"✅ Шрифт загружен: {path}")
                return 'DejaVuSans'
        
        # Если шрифт не найден - используем стандартный
        logger.warning("⚠️ Шрифт с кириллицей не найден, используется стандартный")
        return 'Helvetica'
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки шрифта: {e}")
        return 'Helvetica'

# Регистрируем шрифт при загрузке
FONT_NAME = register_russian_font()


class PDFGenerator:
    """
    Класс для генерации PDF документов с подстановкой данных пользователя
    """
    
    def __init__(self, template, user_data, conclusion):
        self.template = template
        self.user_data = user_data
        self.conclusion = conclusion
    
    def _prepare_data(self):
        """Подготавливает данные для шаблона"""
        data = {
            'full_name': self.user_data.get('full_name', 'ФИО не указано'),
            'address': self.user_data.get('address', 'Адрес не указан'),
            'phone': self.user_data.get('phone', 'Телефон не указан'),
            'email': self.user_data.get('email', 'Email не указан'),
            'additional_info': self.user_data.get('additional_info', ''),
            'conclusion_title': self.conclusion.title if self.conclusion else '',
            'conclusion_short': self.conclusion.short_text if self.conclusion else '',
            'conclusion_full': self.conclusion.full_text if self.conclusion else '',
            'current_date': datetime.now().strftime('%d.%m.%Y'),
            'current_year': datetime.now().strftime('%Y'),
        }
        
        # Добавляем все пользовательские данные
        for key, value in self.user_data.items():
            if key not in data:
                data[key] = value
        
        logger.info(f"📄 Подготовлены данные для PDF: {data}")
        return data
    
    def generate(self) -> bytes:
        """Генерирует PDF с подставленными данными"""
        try:
            data = self._prepare_data()
            
            # Создаем буфер для PDF
            buffer = io.BytesIO()
            
            # Создаем документ
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )
            
            # Стили с поддержкой русского шрифта
            styles = getSampleStyleSheet()
            
            # Стиль для заголовка
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontName=FONT_NAME,
                fontSize=18,
                alignment=TA_CENTER,
                spaceAfter=30,
                textColor=colors.darkblue
            )
            
            # Стиль для подзаголовка
            subtitle_style = ParagraphStyle(
                'CustomSubtitle',
                parent=styles['Heading2'],
                fontName=FONT_NAME,
                fontSize=14,
                alignment=TA_CENTER,
                spaceAfter=20,
                textColor=colors.darkblue
            )
            
            # Стиль для обычного текста
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=FONT_NAME,
                fontSize=12,
                leading=18,
                spaceAfter=6
            )
            
            # Стиль для шапки
            header_style = ParagraphStyle(
                'CustomHeader',
                parent=styles['Normal'],
                fontName=FONT_NAME,
                fontSize=11,
                alignment=TA_RIGHT,
                spaceAfter=4,
                textColor=colors.grey
            )
            
            # Стиль для подписи
            signature_style = ParagraphStyle(
                'CustomSignature',
                parent=styles['Normal'],
                fontName=FONT_NAME,
                fontSize=12,
                alignment=TA_RIGHT,
                spaceBefore=30
            )
            
            # Стиль для жирного текста
            bold_style = ParagraphStyle(
                'CustomBold',
                parent=styles['Normal'],
                fontName=FONT_NAME,
                fontSize=12,
                leading=18,
                spaceAfter=4
            )
            
            story = []
            
            # ===== ШАПКА =====
            story.append(Paragraph(f"Дата: {data['current_date']}", header_style))
            story.append(Spacer(1, 10))
            
            # Информация о пользователе
            user_info = []
            user_info.append(f"<b>ФИО:</b> {data['full_name']}")
            if data['address']:
                user_info.append(f"<b>Адрес:</b> {data['address']}")
            if data['phone']:
                user_info.append(f"<b>Телефон:</b> {data['phone']}")
            if data['email']:
                user_info.append(f"<b>Email:</b> {data['email']}")
            
            for line in user_info:
                story.append(Paragraph(line, normal_style))
            
            story.append(Spacer(1, 20))
            
            # ===== ЗАГОЛОВОК =====
            story.append(Paragraph("ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ", title_style))
            story.append(Spacer(1, 10))
            
            # ===== ТЕМА =====
            if data['conclusion_title']:
                story.append(Paragraph(data['conclusion_title'], subtitle_style))
                story.append(Spacer(1, 10))
            
            # ===== ОСНОВНОЙ ТЕКСТ =====
            if data['conclusion_full']:
                # Разбиваем текст на абзацы
                paragraphs = data['conclusion_full'].split('\n')
                for p in paragraphs:
                    if p.strip():
                        # Проверяем, является ли строка списком
                        if p.strip().startswith(('1.', '2.', '3.', '4.', '5.', '-', '•')):
                            story.append(Paragraph(p, normal_style))
                        else:
                            story.append(Paragraph(p, normal_style))
            
            story.append(Spacer(1, 30))
            
            # ===== ПОДПИСЬ =====
            story.append(Paragraph("_________________________", signature_style))
            story.append(Paragraph(f"Подпись: {data['full_name']}", signature_style))
            
            # ===== ПРИМЕЧАНИЕ =====
            story.append(Spacer(1, 20))
            note_style = ParagraphStyle(
                'Note',
                parent=styles['Normal'],
                fontName=FONT_NAME,
                fontSize=10,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            story.append(Paragraph("Документ сгенерирован автоматически", note_style))
            
            # Строим PDF
            doc.build(story)
            
            pdf_bytes = buffer.getvalue()
            logger.info(f"✅ PDF создан, размер: {len(pdf_bytes)} байт")
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"❌ PDF generation error: {e}")
            import traceback
            traceback.print_exc()
            raise


def generate_document_for_user(user_session, conclusion, user_data):
    """
    Генерирует документ с подстановкой данных пользователя
    """
    from .models import GeneratedDocument
    
    logger.info(f"📄 generate_document_for_user вызван")
    logger.info(f"📄 Вывод: {conclusion.title} (ID: {conclusion.id})")
    logger.info(f"📄 Данные пользователя: {user_data}")
    
    try:
        generator = PDFGenerator(None, user_data, conclusion)
        pdf_bytes = generator.generate()
        
        # Создаем запись в БД
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=None,
            conclusion=conclusion,
            user_data=user_data,
            content_text=f"Документ для {user_data.get('full_name', 'Пользователь')}",
            status='ready'
        )
        
        # Сохраняем PDF
        filename = f"document_{user_session.id}_{conclusion.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc.pdf_file.save(filename, ContentFile(pdf_bytes))
        doc.save()
        
        logger.info(f"✅ Документ сохранен: {filename}")
        return doc
        
    except Exception as e:
        logger.error(f"❌ Document generation error: {e}")
        import traceback
        traceback.print_exc()
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=None,
            conclusion=conclusion,
            user_data=user_data,
            status='failed',
            content_text=str(e)
        )
        return None