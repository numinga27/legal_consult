"""Fetch a reader-accessible Google document as DOCX, never arbitrary URLs."""
import re
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import URLError

from .questionnaire_import import ImportProblem, MAX_BYTES


class GoogleExportRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urlparse(newurl)
        host = url.hostname or ''
        if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
                or not (host == 'docs.google.com' or host == 'googleusercontent.com' or host.endswith('.googleusercontent.com'))):
            raise ImportProblem('Google перенаправил экспорт на неподдерживаемый адрес. Скачайте документ как .docx.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_google_doc(link):
    try:
        url = urlparse(link.strip())
        match = re.fullmatch(r'/document/d/([A-Za-z0-9_-]+)(?:/[^?#]*)?', url.path)
        if (url.scheme != 'https' or url.hostname != 'docs.google.com' or url.username or url.password
                or url.port not in (None, 443) or not match):
            raise ValueError
    except ValueError:
        raise ImportProblem('Вставьте ссылку вида https://docs.google.com/document/d/…/edit.')
    export = f'https://docs.google.com/document/d/{match[1]}/export?format=docx'
    try:
        with build_opener(GoogleExportRedirects()).open(Request(export), timeout=20) as response:
            data = response.read(MAX_BYTES + 1)
    except (URLError, TimeoutError, OSError):
        raise ImportProblem('Не удалось прочитать Google Docs. Проверьте доступ на чтение по ссылке или загрузите экспорт .docx из меню «Файл → Скачать».')
    if len(data) > MAX_BYTES:
        raise ImportProblem('Документ Google Docs превышает 5 МБ.')
    if not data.startswith(b'PK'):
        raise ImportProblem('Google не выдал документ. Нужен доступ на чтение по ссылке; закрытый документ можно скачать как .docx и загрузить сюда.')
    return data
