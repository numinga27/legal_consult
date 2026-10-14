"""Recovery readback, executed with production Django settings on the server.
Never prints passwords, cookies, tokens, or user records.
"""
import json
import re
from pathlib import Path
import requests
from core.models import Questionnaire, DocumentTemplate, ConclusionDocument
from core.questionnaire_runtime import runtime_package
from core.questionnaire_import import FORMAT, validate_package

catalogue = []
for q in Questionnaire.objects.all():
    try:
        package = runtime_package(q)
        if package.get('format') == FORMAT:
            errors = validate_package(package)
        else:
            errors = [f'Unavailable target in question {key}'
                      for key, node in package['nodes'].items()
                      if any(answer['target'] == 'unavailable' for answer in node['answers'])]
    except Exception as error:
        errors = [type(error).__name__]
    catalogue.append({'id': q.id, 'name': q.name, 'active': q.is_active,
                      'questions': q.questions.count(), 'conclusions': q.conclusions.count(),
                      'graph_errors': errors})
print(json.dumps({'catalogue': catalogue, 'templates': DocumentTemplate.objects.count(),
                  'uploaded_document_sets': ConclusionDocument.objects.count()}, ensure_ascii=False))

base = 'https://176.53.224.200'
with requests.Session() as client:
    for path in ['/', '/healthz/', '/admin-login/', '/account/login/', '/account/register/',
                 '/requisites/', '/static/css/home.css', '/static/fonts/Inter.ttf', '/guided/10/']:
        response = client.get(base + path, timeout=15)
        assert response.status_code == 200, (path, response.status_code)
        print('HTTPS 200', path)
    response = client.get(base + '/admin-login/', timeout=15)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text).group(1)
    credentials = dict(line.split(': ', 1) for line in Path('/home/numinga/.config/legal-consult/recovery-admin.txt').read_text().splitlines())
    response = client.post(base + '/admin-login/', data={
        'csrfmiddlewaretoken': csrf, 'username': credentials['Login'], 'password': credentials['Password'],
    }, headers={'Referer': base + '/admin-login/'}, timeout=15)
    assert response.status_code == 200 and response.url.endswith('/admin-dashboard/'), 'Owner login failed'
    print('OWNER LOGIN VERIFIED')
    for path in ['/admin-import/', '/admin-import/guide/', '/admin-import/?questionnaire=10']:
        response = client.get(base + path, timeout=15)
        assert response.status_code == 200, (path, response.status_code)
        print('OWNER PAGE 200', path)
    client.get(base + '/admin-logout/', timeout=15)
print('RECOVERY READBACK PASSED')
