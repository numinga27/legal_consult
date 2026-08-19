import io
import re
from datetime import datetime
from django.core.files.base import ContentFile
from xhtml2pdf import pisa
import logging

logger = logging.getLogger(__name__)


class PDFGenerator:
    """
    Класс для генерации PDF документов с подстановкой данных пользователя
    """
    
    def __init__(self, template, user_data, conclusion):
        self.template = template
        self.user_data = user_data
        self.conclusion = conclusion
    
    def _prepare_data(self):
        """Подготавливает данные для шаблона с заменой переменных"""
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
        
        # Добавляем все пользовательские данные
        for key, value in self.user_data.items():
            if key not in data:
                data[key] = value
        
        return data
    
    def _render_html(self, data: dict) -> str:
        """Рендерит HTML шаблон с подстановкой данных"""
        if self.template and self.template.html_template:
            html = self.template.html_template
            
            # Заменяем все переменные {{ variable }}
            for key, value in data.items():
                placeholder = f'{{{{{key}}}}}'
                html = html.replace(placeholder, str(value))
            
            # Заменяем [переменные] на данные пользователя
            for key, value in data.items():
                placeholder = f'[{key}]'
                html = html.replace(placeholder, str(value))
            
            return html
        
        # Стандартный шаблон, если нет своего
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }}
                h1 {{ color: #1a1a2e; font-size: 18pt; text-align: center; }}
                .header {{ text-align: right; margin-bottom: 30px; }}
                .content {{ line-height: 1.8; }}
                .footer {{ margin-top: 50px; text-align: right; }}
            </style>
        </head>
        <body>
            <div class="header">
                <p>Дата: {data['current_date']}</p>
                <p><strong>ФИО:</strong> {data['full_name']}</p>
                <p><strong>Адрес:</strong> {data['address']}</p>
                <p><strong>Телефон:</strong> {data['phone']}</p>
                <p><strong>Email:</strong> {data['email']}</p>
            </div>
            
            <h1>ЮРИДИЧЕСКАЯ КОНСУЛЬТАЦИЯ</h1>
            
            <div class="content">
                <h3>{data['conclusion_title']}</h3>
                <p>{data['conclusion_full']}</p>
            </div>
            
            <div class="footer">
                <p>_________________________</p>
                <p><strong>Подпись:</strong> {data['full_name']}</p>
            </div>
        </body>
        </html>
        """
    
    def generate(self) -> bytes:
        """Генерирует PDF с подставленными данными"""
        try:
            data = self._prepare_data()
            html_content = self._render_html(data)
            
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; }}
                    h1 {{ color: #1a1a2e; font-size: 18pt; text-align: center; margin-bottom: 30px; }}
                    h3 {{ color: #1a1a2e; font-size: 14pt; margin-top: 20px; }}
                    .header {{ text-align: right; margin-bottom: 30px; }}
                    .content {{ line-height: 1.8; }}
                    .footer {{ margin-top: 50px; text-align: right; }}
                    p {{ margin: 5px 0; }}
                    .signature {{ margin-top: 30px; }}
                    .field-label {{ font-weight: bold; }}
                    .field-value {{ border-bottom: 1px solid #ccc; padding: 2px 10px; }}
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
            logger.error(f"PDF generation error: {e}")
            raise


def generate_document_for_user(user_session, conclusion, user_data):
    """Генерирует документ с подстановкой данных пользователя"""
    from .models import DocumentTemplate, GeneratedDocument
    
    template = DocumentTemplate.objects.filter(
        conclusion=conclusion,
        is_active=True
    ).first()
    
    if not template:
        template = DocumentTemplate.objects.filter(is_active=True).first()
    
    try:
        generator = PDFGenerator(template, user_data, conclusion)
        pdf_bytes = generator.generate()
        
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=template,
            conclusion=conclusion,
            user_data=user_data,
            content_text=generator._render_html(generator._prepare_data()),
            status='ready'
        )
        
        filename = f"document_{user_session.id}_{conclusion.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc.pdf_file.save(filename, ContentFile(pdf_bytes))
        doc.save()
        
        return doc
        
    except Exception as e:
        logger.error(f"Document generation error: {e}")
        doc = GeneratedDocument.objects.create(
            user_session=user_session,
            template=template,
            conclusion=conclusion,
            user_data=user_data,
            status='failed',
            content_text=str(e)
        )
        return None