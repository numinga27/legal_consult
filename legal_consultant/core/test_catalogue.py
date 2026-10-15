from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from .models import LegalDirection, Questionnaire, QuestionnaireRun, HelpOrder, Question, Answer, Conclusion, AnswerConclusion
from .questionnaire_import import prepare_import, save_package
from .test_questionnaire_import import GRAPH, WORD, word_bytes


class CatalogueTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('owner', is_staff=True)
        self.client.force_login(self.owner)
        self.direction = LegalDirection.objects.create(name='Семейное право')
        self.q, _ = save_package(prepare_import(GRAPH.encode(), word_bytes(WORD), 'Судебный приказ'), self.direction, activate=True)
        self.url = reverse('core:admin_dashboard')

    def test_pagination_search_and_filters_cover_entire_catalogue(self):
        for i in range(24):
            Questionnaire.objects.create(name=f'Опросник {i:02}', direction=self.direction, is_active=False)
        first = self.client.get(self.url)
        self.assertEqual(len(first.context['questionnaires']), 10)
        second = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(second.context['questionnaires']), 10)
        self.assertFalse(set(q.pk for q in first.context['questionnaires']) & set(q.pk for q in second.context['questionnaires']))
        self.assertEqual(len(self.client.get(self.url, {'page': 3}).context['questionnaires']), 5)
        found = self.client.get(self.url, {'q': 'сУдЕбНыЙ', 'kind': 'import', 'direction': self.direction.pk})
        self.assertEqual([q.pk for q in found.context['questionnaires']], [self.q.pk])
        manual = self.client.get(self.url, {'kind': 'manual', 'q': 'опросник', 'page': 2})
        self.assertEqual(manual.context['page_obj'].paginator.count, 24)
        self.assertContains(manual, 'kind=manual')
        self.assertEqual(self.client.get(self.url, {'q': '['}).context['page_obj'].paginator.count, 0)

    def test_archive_restore_publish_and_preview(self):
        public = Client()
        entry = reverse('core:user_questionnaire', args=[self.q.pk])
        guided = reverse('core:guided_questionnaire', args=[self.q.pk])
        self.client.post(self.url, {'action': 'archive', 'questionnaire_id': self.q.pk})
        self.q.refresh_from_db()
        self.assertTrue(self.q.is_archived)
        self.assertFalse(self.q.is_active)
        self.assertEqual(self.client.get(self.url).context['page_obj'].paginator.count, 0)
        self.assertEqual(self.client.get(self.url, {'status': 'archive'}).context['page_obj'].paginator.count, 1)
        for url in [entry, guided]:
            self.assertEqual(public.get(url).status_code, 404)
            self.assertEqual(self.client.get(url, follow=True).status_code, 200)
        self.assertNotContains(public.get('/'), self.q.name)
        save_package({k: v for k, v in self.q.workflow.items() if k != 'import_digest'}, self.direction, activate=True)
        self.q.refresh_from_db()
        self.assertFalse(self.q.is_active)
        self.client.post(self.url, {'action': 'restore', 'questionnaire_id': self.q.pk})
        self.q.refresh_from_db()
        self.assertFalse(self.q.is_archived)
        self.assertFalse(self.q.is_active)
        self.client.post(self.url, {'action': 'publish', 'questionnaire_id': self.q.pk, 'revision': self.q.workflow['import_digest']})
        self.assertEqual(public.get(guided).status_code, 200)

    def test_create_edit_metadata_and_manual_publication(self):
        url = reverse('core:questionnaire_create')
        self.client.post(url, {'name': ' ', 'direction': self.direction.pk})
        self.assertEqual(Questionnaire.objects.count(), 1)
        self.client.post(url, {'name': 'Вручную', 'direction': self.direction.pk})
        item = Questionnaire.objects.get(name='Вручную')
        self.assertFalse(item.is_active)
        self.client.post(self.url, {'questionnaire_id': item.pk, 'action': 'publish'})
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        question = Question.objects.create(questionnaire=item, order=1, text='Вопрос?')
        conclusion = Conclusion.objects.create(questionnaire=item, order=1, title='Вывод', short_text='Результат', full_text='Текст')
        for text in ['Да', 'Нет']:
            answer = Answer.objects.create(question=question, text=text, intermediate_text='', is_final=True)
            AnswerConclusion.objects.create(answer=answer, conclusion=conclusion)
        self.client.post(self.url, {'questionnaire_id': item.pk, 'action': 'publish'})
        item.refresh_from_db()
        self.assertTrue(item.is_active)
        other = LegalDirection.objects.create(name='Новый раздел')
        edit = reverse('core:questionnaire_settings', args=[self.q.pk])
        self.client.post(edit, {'name': 'Новое название', 'direction': other.pk, 'description': 'Описание'})
        self.q.refresh_from_db()
        self.assertEqual(self.q.name, self.q.workflow['name'])
        self.assertEqual(self.q.direction_id, other.pk)
        self.assertEqual(Questionnaire.objects.count(), 2)

    def test_deletion_requires_exact_confirmation_and_preserves_orders(self):
        url = reverse('core:questionnaire_delete', args=[self.q.pk])
        self.client.get(url)
        self.client.post(url, {'confirm_name': 'wrong'})
        self.assertTrue(Questionnaire.objects.filter(pk=self.q.pk).exists())
        order = HelpOrder.objects.create(owner_id=uuid4(), questionnaire=self.q, result_code='1', bundle_index=0,
            fingerprint='test-order', summary={}, amount=298, full_name='Test', email='test@example.com', phone='1234567890')
        self.assertContains(self.client.post(url, {'confirm_name': self.q.name}), 'есть заказы или платежи')
        self.assertTrue(HelpOrder.objects.filter(pk=order.pk).exists())
        empty = Questionnaire.objects.create(name='Удаляемый черновик', direction=self.direction, is_active=False)
        self.client.post(reverse('core:questionnaire_delete', args=[empty.pk]), {'confirm_name': empty.name})
        self.assertFalse(Questionnaire.objects.filter(pk=empty.pk).exists())

    def test_manual_content_edits_are_scoped_and_deletes_require_post(self):
        manual = Questionnaire.objects.create(name='Ручной', direction=self.direction, is_active=False)
        question = Question.objects.create(questionnaire=manual, order=1, text='Было')
        answer = Answer.objects.create(question=question, text='Да', intermediate_text='')
        edit = reverse('core:questionnaire_content_edit', args=[manual.pk, 'question', question.pk])
        self.client.post(edit, {'text': 'Стало', 'help_text': 'Подсказка'})
        question.refresh_from_db()
        self.assertEqual(question.text, 'Стало')
        edit_answer = reverse('core:questionnaire_content_edit', args=[manual.pk, 'answer', answer.pk])
        foreign = self.q.questions.first()
        self.client.post(edit_answer, {'text': 'Другой ответ', 'intermediate_text': '', 'next_question': foreign.pk})
        answer.refresh_from_db()
        self.assertEqual(answer.text, 'Да')
        self.assertEqual(self.client.get(reverse('core:questionnaire_content_edit', args=[manual.pk, 'question', foreign.pk])).status_code, 404)
        delete = reverse('core:admin_delete_answer', args=[answer.pk])
        self.assertEqual(self.client.get(delete).status_code, 405)
        self.assertTrue(Answer.objects.filter(pk=answer.pk).exists())

    def test_stats_count_attempts_not_refreshes_and_skip_staff(self):
        url = reverse('core:guided_questionnaire', args=[self.q.pk])
        self.client.get(url)
        self.assertEqual(QuestionnaireRun.objects.count(), 0)
        visitor = Client()
        visitor.get(url)
        visitor.get(url)
        self.assertEqual(QuestionnaireRun.objects.count(), 1)
        state = visitor.session[f'guided_questionnaire_{self.q.pk}']
        visitor.post(url, {'action': 'answer', 'answer': 0, 'revision': state['revision']}, follow=True)
        visitor.get(url)
        self.assertEqual(QuestionnaireRun.objects.filter(completed_at__isnull=False).count(), 1)
        state = visitor.session[f'guided_questionnaire_{self.q.pk}']
        visitor.post(url, {'action': 'back', 'revision': state['revision']}, follow=True)
        state = visitor.session[f'guided_questionnaire_{self.q.pk}']
        visitor.post(url, {'action': 'answer', 'answer': 1, 'revision': state['revision']}, follow=True)
        self.assertEqual(QuestionnaireRun.objects.filter(completed_at__isnull=False).count(), 1)
        visitor.post(url, {'action': 'restart'}, follow=True)
        item = self.client.get(self.url).context['questionnaires'][0]
        self.assertEqual((item.starts, item.finishes, item.completion_rate), (2, 1, 50))

    def test_owner_actions_require_staff_and_csrf(self):
        outsider = Client()
        outsider.force_login(get_user_model().objects.create_user('visitor'))
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        urls = [self.url, reverse('core:questionnaire_create'), reverse('core:questionnaire_settings', args=[self.q.pk]), reverse('core:questionnaire_delete', args=[self.q.pk])]
        for url in urls:
            self.assertEqual(outsider.get(url).status_code, 403)
            self.assertEqual(outsider.post(url).status_code, 403)
            self.assertEqual(strict.post(url).status_code, 403)

    def test_account_identity_is_visible_on_home_and_questionnaire(self):
        visitor = Client()
        visitor.force_login(get_user_model().objects.create_user('opaque-id', email='person@example.com'))
        for url in ['/', reverse('core:guided_questionnaire', args=[self.q.pk])]:
            self.assertContains(visitor.get(url), 'person@example.com')
            self.assertNotContains(Client().get(url), 'person@example.com')
        self.assertContains(self.client.get(self.url), 'Вы вошли как')
