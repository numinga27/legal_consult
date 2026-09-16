from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from .models import LegalDirection, Questionnaire
from .questionnaire_import import save_package
from .test_questionnaire_import import GRAPH, WORD, word_bytes, example


class OwnerPublicationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('editor', is_staff=True)
        self.client.force_login(self.owner)
        self.direction = LegalDirection.objects.create(name='Тестовый раздел')
        self.dashboard = reverse('core:admin_dashboard')
        self.import_url = reverse('core:import_questionnaire')

    def test_source_to_private_draft_then_publication_and_hide(self):
        response = self.client.post(self.import_url, {
            'action': 'analyze', 'name': 'Новый опросник',
            'graph': SimpleUploadedFile('example.drawio', GRAPH.encode()),
            'word': SimpleUploadedFile('example.docx', word_bytes(WORD)),
        })
        self.assertContains(response, '2. Проверьте переходы и тексты')
        revision = self.client.session['questionnaire_import_revision']
        response = self.client.post(self.import_url, {
            'action': 'save', 'draft_revision': revision, 'reviewed': 'yes',
            'direction': self.direction.id,
        })
        self.assertContains(response, 'Черновик сохранён')
        item = Questionnaire.objects.get(name='Новый опросник')
        url = reverse('core:guided_questionnaire', args=[item.id])
        self.assertEqual(Client().get(url).status_code, 404)
        self.assertContains(self.client.get(url), 'Предпросмотр владельца')
        self.assertContains(self.client.get(self.dashboard), 'Новый опросник')
        publication = {'questionnaire_id': item.id, 'revision': item.workflow['import_digest'], 'action': 'publish'}
        self.client.post(self.dashboard, publication)
        self.assertContains(Client().get(url), 'Есть вопрос?')
        self.client.post(self.dashboard, {**publication, 'action': 'unpublish'})
        self.assertEqual(Client().get(url).status_code, 404)
        self.assertEqual(Questionnaire.objects.count(), 1)
        self.assertEqual(item.questions.count(), 1)

    def test_publication_rejects_invalid_schema_stale_revision_and_inactive_direction(self):
        item, _ = save_package(example(), self.direction)
        data = {'questionnaire_id': item.id, 'revision': 'old', 'action': 'publish'}
        self.client.post(self.dashboard, data)
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        data['revision'] = item.workflow['import_digest']
        self.direction.is_active = False
        self.direction.save()
        self.client.post(self.dashboard, data)
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.direction.is_active = True
        self.direction.save()
        item.workflow['start'] = 'missing'
        item.save()
        self.client.post(self.dashboard, data)
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_owner_tools_are_staff_only_and_publication_requires_csrf(self):
        outsider = Client()
        outsider.force_login(get_user_model().objects.create_user('visitor'))
        routes = ['admin_dashboard', 'import_questionnaire', 'import_guide', 'admin_add_questionnaire', 'admin_generate_ai']
        for route in routes:
            url = reverse('core:' + route)
            self.assertEqual(Client().get(url).status_code, 302)
            self.assertEqual(outsider.get(url).status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(self.dashboard, {'action': 'publish'}).status_code, 403)
        self.assertEqual(self.client.post(self.dashboard, {'questionnaire_id': 'bad'}).status_code, 400)

    def test_new_import_clears_draft_without_changing_saved_questionnaire(self):
        item, _ = save_package(example(), self.direction)
        self.client.get(self.import_url, {'q': item.id})
        self.assertIn('questionnaire_import_draft', self.client.session)
        self.client.post(self.import_url, {'action': 'clear'})
        self.assertNotIn('questionnaire_import_draft', self.client.session)
        self.assertEqual(Questionnaire.objects.get(pk=item.id).workflow['start'], item.workflow['start'])
