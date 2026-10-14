"""One-time recovery on the replacement server, after migrating the saved DB.

Run through manage.py shell with this file on stdin. Never use on an existing
production installation. Credentials stay in the private runtime directory.
"""
import json
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from core.models import LegalDirection, Questionnaire, DocumentTemplate, ConclusionDocument
from core.questionnaire_import import save_package

runtime = Path('/home/numinga/.config/legal-consult')
marker = runtime / 'recovery-2026-10-14.json'
if marker.exists():
    raise SystemExit('Recovery already applied; refusing to overwrite restored data.')

with transaction.atomic():
    direction, _ = LegalDirection.objects.get_or_create(name='Судебные приказы и взыскание')
    package = json.loads((settings.BASE_DIR / 'core/import_examples/court_order.json').read_text(encoding='utf-8'))
    questionnaire, created = save_package(package, direction, activate=True)
    # Keep clearly labelled seed experiments available only to the owner.
    drafts = list(Questionnaire.objects.filter(name__in=['Тестовый опросник', 'kfjdesc (AI)']).values_list('id', flat=True))
    Questionnaire.objects.filter(id__in=drafts).update(is_active=False)
    users = get_user_model()
    # A sanitized seed has no users. Defensively retire any historical staff
    # rather than carrying old credentials into this new installation.
    retired_staff = list(users.objects.filter(is_staff=True).values_list('id', flat=True))
    users.objects.filter(id__in=retired_staff).update(is_active=False)
    password = secrets.token_urlsafe(24)
    owner = users.objects.create_superuser(username='recovery-owner', password=password)
    credentials = runtime / 'recovery-admin.txt'
    fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        output.write('Login: recovery-owner\nPassword: ' + password + '\n')
    report = {
        'source': 'Catalogue-only export of local snapshot dated 2026-09-10; no users, payments or sessions',
        'court_order_id': questionnaire.id,
        'court_order_imported': created,
        'questionnaires': Questionnaire.objects.count(),
        'seed_experiments_kept_as_drafts': drafts,
        'embedded_templates': DocumentTemplate.objects.count(),
        'uploaded_document_sets': ConclusionDocument.objects.count(),
        'retired_staff_ids': retired_staff,
        'owner_id': owner.id,
        'missing': ['Post-snapshot production changes', 'Uploaded DOCX/PDF files', 'Old production runtime secrets'],
    }
marker.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
marker.chmod(0o600)
print(json.dumps(report, ensure_ascii=False))
print('Admin credentials stored only in the private runtime directory.')
