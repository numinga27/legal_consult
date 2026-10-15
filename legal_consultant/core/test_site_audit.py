import json
from copy import deepcopy
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from .models import LegalDirection, Questionnaire, Question, Conclusion, ConclusionDocument
from .questionnaire_import import ImportProblem, save_package
from .test_questionnaire_import import example


class SiteAuditRegressionTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('audit-editor', is_staff=True)
        self.client.force_login(self.owner)
        self.direction = LegalDirection.objects.create(name='Раздел')
        self.q = Questionnaire.objects.create(name='Черновик', direction=self.direction, is_active=False)
        self.editor = reverse('core:admin_questionnaire', args=[self.q.pk])
        self.workflow = {'nodes': [
            {'id': 'start', 'type': 'start', 'title': 'Начало'},
            {'id': 'q', 'type': 'question', 'title': 'Вопрос?'},
            {'id': 'a1', 'type': 'answer', 'title': 'Да'},
            {'id': 'a2', 'type': 'answer', 'title': 'Нет'},
            {'id': 'c', 'type': 'conclusion', 'title': 'Вывод', 'text': 'Полный текст. ' * 40, 'price': 100, 'success_rate': 50},
        ], 'connections': [
            {'source': 'a1', 'target': 'c'}, {'source': 'a2', 'target': 'c'},
            {'source': 'q', 'target': 'a1'}, {'source': 'q', 'target': 'a2'},
            {'source': 'start', 'target': 'q'},
        ]}

    def save_visual(self, workflow=None, route='api_save_workflow'):
        return self.client.post(reverse('core:' + route), json.dumps({'questionnaire_id': self.q.pk, 'workflow': workflow or self.workflow}), content_type='application/json')

    def test_visual_edges_are_order_independent_and_text_is_not_truncated(self):
        self.assertEqual(self.save_visual().status_code, 200)
        self.assertEqual(self.q.questions.get().answers.count(), 2)
        self.assertEqual(self.q.conclusions.get().answer_links.count(), 2)
        self.assertEqual(self.q.conclusions.get().short_text, self.workflow['nodes'][-1]['text'])
        self.assertEqual(self.save_visual(route='api_sync_workflow').status_code, 200)
        self.assertEqual(self.q.questions.count(), 1)

    def test_invalid_visual_graph_never_destroys_existing_draft(self):
        self.assertEqual(self.save_visual().status_code, 200)
        old_ids = list(self.q.questions.values_list('pk', flat=True))
        broken = deepcopy(self.workflow)
        broken['connections'][0]['target'] = 'missing'
        self.assertEqual(self.save_visual(broken, route='api_sync_workflow').status_code, 400)
        self.assertEqual(list(self.q.questions.values_list('pk', flat=True)), old_ids)
        self.q.refresh_from_db()
        self.assertEqual(self.q.workflow, self.workflow)

    def test_visual_rebuild_cannot_destroy_published_content_or_documents(self):
        self.assertEqual(self.save_visual().status_code, 200)
        self.q.is_active = True
        self.q.save()
        self.assertEqual(self.save_visual().status_code, 400)
        self.q.is_active = False
        self.q.save()
        result = self.q.conclusions.get()
        doc = ConclusionDocument.objects.create(conclusion=result, title='Материал', docx_file='missing.docx', pdf_file='missing.pdf')
        self.assertEqual(self.save_visual(route='api_sync_workflow').status_code, 400)
        self.assertTrue(Conclusion.objects.filter(pk=result.pk).exists())
        self.assertTrue(ConclusionDocument.objects.filter(pk=doc.pk).exists())

    def test_add_question_after_deleted_order_and_invalid_result(self):
        first = Question.objects.create(questionnaire=self.q, order=1, text='Первый')
        Question.objects.create(questionnaire=self.q, order=2, text='Второй')
        first.delete()
        self.assertEqual(self.client.post(self.editor, {'action': 'add_question', 'question_text': 'Третий'}).status_code, 302)
        self.assertEqual(self.q.questions.get(text='Третий').order, 3)
        self.client.post(self.editor, {'action': 'add_question', 'question_text': ' '})
        self.assertEqual(self.q.questions.count(), 2)
        response = self.client.post(self.editor, {'action': 'add_conclusion', 'title': 'Вывод', 'short_text': 'Кратко', 'full_text': 'Полностью', 'success_rate': 'not-a-number', 'price': '-1'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.q.conclusions.count(), 0)

    def test_private_api_and_mock_generation_are_not_public_tools(self):
        api = reverse('core:api_questionnaire_data', args=[self.q.pk])
        self.assertEqual(Client().get(api).status_code, 302)
        outsider = Client()
        outsider.force_login(get_user_model().objects.create_user('reader'))
        self.assertEqual(outsider.get(api).status_code, 403)
        self.assertEqual(outsider.post(reverse('core:api_test_rules')).status_code, 403)
        before = Questionnaire.objects.count()
        response = self.client.post(reverse('core:admin_generate_ai'), {'topic': 'Test'}, follow=True)
        self.assertContains(response, 'Генерация ИИ не подключена')
        self.assertEqual(Questionnaire.objects.count(), before)

    def test_disabled_direction_cannot_be_published_through_import(self):
        self.direction.is_active = False
        self.direction.save()
        with self.assertRaises(ImportProblem):
            save_package(example(), self.direction, activate=True)

    def test_public_result_uses_individual_services_without_changing_source(self):
        q, _ = save_package(example(), self.direction, activate=True)
        url = reverse('core:guided_questionnaire', args=[q.pk])
        self.client.get(url)
        state = self.client.session[f'guided_questionnaire_{q.pk}']
        response = self.client.post(url, {'action': 'answer', 'answer': 1, 'revision': state['revision']}, follow=True)
        self.assertContains(response, 'Выберите одну или несколько нужных вам услуг ниже.')
        self.assertNotContains(response, 'пакетных решений')
        q.refresh_from_db()
        self.assertIn('пакетных решений', q.workflow['conclusions']['1']['short_text'])

    def test_owner_catalogue_exposes_incomplete_routes(self):
        Question.objects.create(questionnaire=self.q, order=1, text='Вопрос без ответов')
        self.assertContains(self.client.get(reverse('core:admin_dashboard')), 'незаполненные или ошибочные переходы')
