"""
Сервис для генерации PDF документов
"""

import os
import re
import io
import json
from datetime import datetime
from django.conf import settings
from django.template import Template, Context
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa
import logging

logger = logging.getLogger(__name__)


class PDFGenerator:
    """
    Класс для генерации PDF документов
    """
    
    def __init__(self, template, user_data, conclusion):
        """
        Инициализация генератора PDF
        
        Args:
            template: Объект DocumentTemplate
            user_data: Dict с данными пользователя
            conclusion: Объект Conclusion
        """
        self.template = template
        self.user_data = user_data
        self.conclusion = conclusion
        self.variables = self._parse_variables()
        
    def _parse_variables(self):
        """Парсит переменные из шаблона"""
        if self.template:
            html = self.template.html_template
            # Находим все переменные вида {{ переменная }}
            pattern = r'{{(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*)}}'
            return re.findall(pattern, html)
        return []
    
    def _prepare_data(self):
        """Подготавливает данные для шаблона"""
        data = {
            'full_name': self.user_data.get('full_name', '[ФИО не указано]'),
            'address': self.user_data.get('address', '[Адрес не указан]'),
            'phone': self.user_data.get('phone', '[Телефон не указан]'),
            'email': self.user_data.get('email', '[Email не указан]'),
            'additional_info': self.user_data.get('additional_info', ''),
            'conclusion_title': self.conclusion.title if self.conclusion else '',
            'conclusion_short': self.conclusion.short_text if self.conclusion else '',
            'conclusion_full': self.conclusion.full_text if self.conclusion else '',
            'current_date': datetime.now().strftime('%d.%m.%Y'),
            'current_year': datetime.now().strftime('%Y'),
        }
        
        # Добавляем дополнительные данные
        for key, value in self.user_data.items():
            if key not in data:
                data[key] = value
        
        return data
    
    def generate_reportlab_pdf(self) -> bytes:
        """
        Генерирует PDF используя ReportLab
        """
        buffer = io.BytesIO()
        
        try:
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )
            
            styles = getSampleStyleSheet()
            
            # Создаем кастомные стили
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                alignment=TA_CENTER,
                spaceAfter=30,
                textColor=colors.darkblue
            )
            
            header_style = ParagraphStyle(
                'CustomHeader',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_RIGHT,
                textColor=colors.grey
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=12,
                leading=16,
                spaceAfter=6
            )
            
            signature_style = ParagraphStyle(
                'Signature',
                parent=styles['Normal'],
                fontSize=12,
                alignment=TA_RIGHT,
                spaceBefore=30
            )
            
            story = []
            
            # Подготавливаем данные
            data = self._prepare_data()
            
            # Если есть HTML шаблон, используем его, иначе генерируем стандартный
            if self.template and self.template.html_template:
                html_content = self._render_html_template(data)
                # Конвертируем HTML в PDF через xhtml2pdf
                return self.generate_xhtml2pdf(html_content)
            
            # Стандартный документ без шаблона
            story.append(Paragraph('ЮРИДИЧЕСКИЙ ДОКУМЕНТ', title_style))
            story.append(Spacer(1, 20))
            
            # Шапка
            header_text = f"Дата: {data['current_date']}"
            story.append(Paragraph(header_text, header_style))
            story.append(Spacer(1, 10))
            
            # Информация о пользователе
            story.append(Paragraph(f"<b>ФИО:</b> {data['full_name']}", normal_style))
            if data.get('address'):
                story.append(Paragraph(f"<b>Адрес:</b> {data['address']}", normal_style))
            if data.get('phone'):
                story.append(Paragraph(f"<b>Телефон:</b> {data['phone']}", normal_style))
            if data.get('email'):
                story.append(Paragraph(f"<b>Email:</b> {data['email']}", normal_style))
            
            story.append(Spacer(1, 20))
            
            # Вывод
            story.append(Paragraph("<b>Документ по вашей ситуации</b>", normal_style))
            story.append(Spacer(1, 10))
            
            if data.get('conclusion_title'):
                story.append(Paragraph(f"<b>{data['conclusion_title']}</b>", normal_style))
                story.append(Spacer(1, 10))
            
            if data.get('conclusion_full'):
                story.append(Paragraph(data['conclusion_full'].replace('\n', '<br/>'), normal_style))
            elif data.get('conclusion_short'):
                story.append(Paragraph(data['conclusion_short'].replace('\n', '<br/>'), normal_style))
            
            # Подпись
            story.append(Spacer(1, 30))
            story.append(Paragraph("_________________________", signature_style))
            story.append(Paragraph(f"Подпись: {data['full_name']}", signature_style))
            
            # Строим PDF
            doc.build(story)
            
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"ReportLab PDF generation error: {e}")
            raise
    
    def _render_html_template(self, data: dict) -> str:
        """Рендерит HTML шаблон с данными"""
        if not self.template:
            return ""
        
        html = self.template.html_template
        
        # Заменяем переменные
        for key, value in data.items():
            placeholder = f'{{{{{key}}}}}'
            html = html.replace(placeholder, str(value))
        
        return html
    
    def generate_xhtml2pdf(self, html_content: str) -> bytes:
        """
        Генерирует PDF из HTML используя xhtml2pdf
        """
        try:
            # Добавляем стили по умолчанию
            css = self.template.css_styles if self.template else ''
            
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    {css}
                    @page {{
                        size: A4;
                        margin: 2cm;
                    }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """
            
            buffer = io.BytesIO()
            pisa_status = pisa.CreatePDF(
                full_html,
                dest=buffer,
                encoding='utf-8'
            )
            
            if pisa_status.err:
                raise Exception(f"Ошибка при создании PDF: {pisa_status.err}")
            
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"XHTML2PDF generation error: {e}")
            # Если не удалось сгенерировать через HTML, используем ReportLab
            return self.generate_reportlab_pdf()
    
    def generate(self) -> bytes:
        """
        Основной метод генерации PDF
        """
        try:
            if self.template and self.template.html_template:
                return self.generate_xhtml2pdf(self._render_html_template(self._prepare_data()))
            else:
                return self.generate_reportlab_pdf()
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            raise


def generate_document_for_user(user_session, conclusion, user_data):
    """
    Генерирует документ для пользователя и сохраняет его
    """
    from .models import DocumentTemplate, GeneratedDocument
    
    # Ищем подходящий шаблон
    template = DocumentTemplate.objects.filter(
        conclusion=conclusion,
        is_active=True
    ).first()
    
    if not template:
        # Если нет шаблона, используем первый активный или создаем стандартный
        template = DocumentTemplate.objects.filter(is_active=True).first()
    
    try:
        # Генерируем PDF
        generator = PDFGenerator(template, user_data, conclusion)
        pdf_bytes = generator.generate()
        
        # Создаем запись в БД
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=template,
            conclusion=conclusion,
            user_data=user_data,
            content_text=generator._render_html_template(generator._prepare_data()) if template else '',
            status='ready'
        )
        
        # Сохраняем PDF файл
        filename = f"document_{user_session.id}_{conclusion.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc.pdf_file.save(filename, ContentFile(pdf_bytes))
        doc.save()
        
        return doc
        
    except Exception as e:
        logger.error(f"Document generation error: {e}")
        # Создаем запись с ошибкой
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=template,
            conclusion=conclusion,
            user_data=user_data,
            status='failed',
            content_text=str(e)
        )
        return None