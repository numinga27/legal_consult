from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, Client
from django.urls import reverse
from .models import LegalDirection, Questionnaire, Question, Answer, Conclusion, AnswerConclusion, Payment
from .google_docs_import import download_google_doc, GoogleExportRedirects
from .questionnaire_import import ImportProblem
from .test_questionnaire_import import GRAPH, WORD, word_bytes
from django.core.files.uploadedfile import SimpleUploadedFile


class CatalogueRuntimeTests(TestCase):
    def setUp(self):
        self.q = Questionnaire.objects.create(name='Алименты', direction=LegalDirection.objects.create(name='Семья'))
        self.one = Question.objects.create(questionnaire=self.q, order=1, text='Есть ребёнок?')
        self.two = Question.objects.create(questionnaire=self.q, order=2, text='Второй родитель платит?')
        Answer.objects.create(question=self.one, text='Да', next_question=self.two, order=0)
        Answer.objects.create(question=self.one, text='Нет', is_final=True, order=1)
        for i in range(3):
            answer = Answer.objects.create(question=self.two, text=f'Вариант {i}', is_final=True, order=i)
            result = Conclusion.objects.create(questionnaire=self.q, order=i+1, title=f'Итог {i}', short_text=f'Кратко {i}', full_text='Закрытый текст')
            AnswerConclusion.objects.create(answer=answer, conclusion=result)
        self.url = reverse('core:guided_questionnaire', args=[self.q.id])
        self.client.get(reverse('core:user_questionnaire', args=[self.q.id]), follow=True)

    def action(self, action, **data):
        state = self.client.session[f'guided_questionnaire_{self.q.id}']
        return self.client.post(self.url, {'action': action, 'revision': state['revision'], **data}, follow=True)

    def test_second_question_all_answers_and_real_back(self):
        for i in range(3):
            self.action('restart')
            self.assertContains(self.action('answer', answer=0), 'Вопрос 2')
            self.assertContains(self.client.get(self.url), self.two.text)
            self.assertContains(self.action('back'), self.one.text)
            self.action('answer', answer=0)
            response = self.action('answer', answer=i)
            self.assertContains(response, f'Кратко {i}')
            self.assertNotContains(response, 'Закрытый текст')
            self.assertContains(self.action('back'), self.two.text)

    def test_missing_conclusion_never_falls_back_to_first_result(self):
        response = self.action('answer', answer=1)
        self.assertContains(response, 'Для этого ответа пока нет готового разбора')
        self.assertNotContains(response, 'Кратко 0')
        self.assertContains(self.action('back'), self.one.text)

    def test_cycles_stop_and_foreign_sessions_cannot_submit_history(self):
        answer = self.two.answers.first()
        answer.next_question = self.one
        answer.save()
        AnswerConclusion.objects.filter(answer=answer).delete()
        self.action('answer', answer=0)
        self.assertContains(self.action('answer', answer=0), 'Для этого ответа пока нет готового разбора')
        self.assertContains(Client().get(self.url), self.one.text)
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, {'action': 'answer', 'answer': 0, 'revision': 0}).status_code, 403)

    def test_old_payment_and_callbacks_cannot_fake_payments(self):
        result = self.q.conclusions.first()
        self.assertEqual(self.client.post(reverse('core:user_payment', args=[result.id])).status_code, 409)
        for name in ['api_get_next_question', 'api_check_answer', 'api_generate_document']:
            self.assertEqual(self.client.post(reverse('core:' + name), {}).status_code, 409)
        self.assertEqual(Payment.objects.count(), 0)


class GoogleDocsTests(SimpleTestCase):
    def test_only_document_urls_and_google_export_redirects_allowed(self):
        for url in ['http://docs.google.com/document/d/abc', 'https://example.com/document/d/abc',
                    'https://docs.google.com:444/document/d/abc', 'https://user@docs.google.com/document/d/abc',
                    'https://docs.google.com/spreadsheets/d/abc']:
            with self.assertRaises(ImportProblem):
                download_google_doc(url)
        with self.assertRaises(ImportProblem):
            GoogleExportRedirects().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/private')

    @patch('core.google_docs_import.build_opener')
    def test_google_export_and_private_document_errors(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = word_bytes(WORD)
        data = download_google_doc('https://docs.google.com/document/d/abc_123/edit?usp=sharing')
        self.assertEqual(data, word_bytes(WORD))
        self.assertEqual(opener.return_value.open.call_args.args[0].full_url,
                         'https://docs.google.com/document/d/abc_123/export?format=docx')
        response.read.return_value = b'<html>sign in</html>'
        with self.assertRaises(ImportProblem):
            download_google_doc('https://docs.google.com/document/d/abc_123/edit')


class GoogleDocsOwnerTests(TestCase):
    @patch('core.import_views.download_google_doc')
    def test_owner_can_import_drawio_with_google_doc(self, download):
        download.return_value = word_bytes(WORD)
        owner = get_user_model().objects.create_user(username='owner', password='local-test', is_staff=True)
        response = self.client.post(reverse('core:admin_login'), {'username': 'owner', 'password': 'local-test'}, follow=True)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('core:import_questionnaire'), {
            'action': 'analyze', 'name': 'Импорт Google Docs', 'google_doc': 'https://docs.google.com/document/d/abc/edit',
            'graph': SimpleUploadedFile('graph.drawio', GRAPH.encode()),
        })
        self.assertFalse(response.context['errors'])
        self.assertEqual(len(response.context['package']['nodes']), 1)
        self.assertContains(response, 'Ссылка Google Docs')
        self.assertEqual(Client().post(reverse('core:import_questionnaire'), {}).status_code, 302)
