import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class ProtectedDocumentStorage(FileSystemStorage):
    """Store paid files outside MEDIA_ROOT so the web server cannot expose them."""

    @property
    def base_location(self):
        return settings.PROTECTED_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


protected_document_storage = ProtectedDocumentStorage()
