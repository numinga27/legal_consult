"""
Middleware для принудительного сохранения сессии
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from django.contrib.sessions.models import Session

logger = logging.getLogger(__name__)


class ForceSessionSaveMiddleware(MiddlewareMixin):
    """
    Принудительно сохраняет сессию после каждого запроса
    """
    
    def process_response(self, request, response):
        # Если пользователь авторизован и есть сессия
        if hasattr(request, 'session') and request.session:
            try:
                # Проверяем, существует ли сессия в БД
                session_key = request.session.session_key
                if session_key:
                    # Обновляем сессию в БД
                    Session.objects.filter(session_key=session_key).update(
                        expire_date=request.session.get_expiry_date()
                    )
            except Exception as e:
                logger.error(f"Error saving session: {e}")
        
        return response