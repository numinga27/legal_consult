def generate(self) -> bytes:
    """Генерирует PDF с подставленными данными"""
    try:
        data = self._prepare_data()
        html_content = self._render_html(data)
        
        logger.info(f"📄 HTML для PDF (первые 500 символов): {html_content[:500]}...")
        
        # Добавляем правильную кодировку и шрифты для кириллицы
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{ 
                    font-family: 'DejaVu Sans', 'Arial', sans-serif; 
                    font-size: 12pt; 
                    margin: 40px;
                    color: #1a1a2e;
                }}
                h1 {{ 
                    color: #1a1a2e; 
                    font-size: 18pt; 
                    text-align: center; 
                    margin-bottom: 30px;
                }}
                .header {{ 
                    text-align: right; 
                    margin-bottom: 30px;
                }}
                .content {{ 
                    line-height: 1.8;
                }}
                .footer {{ 
                    margin-top: 50px; 
                    text-align: right;
                }}
                p {{ 
                    margin: 5px 0;
                }}
                .document-title {{ 
                    font-size: 20pt; 
                    font-weight: bold; 
                    text-align: center; 
                    margin: 30px 0;
                }}
                .field-label {{ 
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        buffer = io.BytesIO()
        
        # Создаем PDF с правильной кодировкой
        pisa_status = pisa.CreatePDF(
            full_html,
            dest=buffer,
            encoding='utf-8',
            link_callback=None
        )
        
        if pisa_status.err:
            logger.error(f"❌ Ошибка при создании PDF: {pisa_status.err}")
            raise Exception(f"Ошибка при создании PDF: {pisa_status.err}")
        
        pdf_bytes = buffer.getvalue()
        logger.info(f"✅ PDF создан, размер: {len(pdf_bytes)} байт")
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ PDF generation error: {e}")
        raise