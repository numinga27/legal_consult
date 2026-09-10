from django.test import TestCase
from django.urls import reverse
from .models import LegalDirection, Questionnaire, Question, Conclusion


class HomePageTests(TestCase):
    def test_available_topics_come_first_without_per_direction_queries(self):
        LegalDirection.objects.create(name='А — пока без опросов')
        direction = LegalDirection.objects.create(name='Я — есть опрос')
        questionnaire = Questionnaire.objects.create(direction=direction, name='Начать')
        Question.objects.create(questionnaire=questionnaire, order=1, text='Вопрос')
        Conclusion.objects.create(questionnaire=questionnaire, order=1, title='Вывод')
        with self.assertNumQueries(2):
            response = self.client.get(reverse('core:user_select_problem'))
        self.assertLess(response.content.index('Я — есть опрос'.encode()),
                        response.content.index('А — пока без опросов'.encode()))

    def test_empty_catalogue_does_not_create_demo_content(self):
        response = self.client.get(reverse('core:user_select_problem'))
        self.assertContains(response, 'Готовим первые темы')
        self.assertEqual(LegalDirection.objects.count(), 0)
        self.assertEqual(Questionnaire.objects.count(), 0)

    def test_only_active_nonempty_questionnaires_are_linked(self):
        direction = LegalDirection.objects.create(name='Автомобиль')
        ready = Questionnaire.objects.create(direction=direction, name='ДТП и ОСАГО')
        Question.objects.create(questionnaire=ready, order=1, text='Вопрос')
        Conclusion.objects.create(questionnaire=ready, order=1, title='Вывод')
        empty = Questionnaire.objects.create(direction=direction, name='Пустой опрос')
        draft = Questionnaire.objects.create(direction=direction, name='Черновик', is_active=False)
        Question.objects.create(questionnaire=draft, order=1, text='Вопрос')
        Conclusion.objects.create(questionnaire=draft, order=1, title='Вывод')
        LegalDirection.objects.create(name='Скрытое направление', is_active=False)
        response = self.client.get(reverse('core:user_select_problem'))
        self.assertContains(response, reverse('core:user_questionnaire', args=[ready.id]))
        self.assertNotContains(response, reverse('core:user_questionnaire', args=[empty.id]))
        self.assertNotContains(response, reverse('core:user_questionnaire', args=[draft.id]))
        self.assertNotContains(response, 'Скрытое направление')

    def test_unavailable_direction_explains_state_and_text_is_escaped(self):
        LegalDirection.objects.create(name='<script>alert(1)</script>')
        response = self.client.get(reverse('core:user_select_problem'))
        self.assertContains(response, 'Опросы по этой теме готовятся')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
