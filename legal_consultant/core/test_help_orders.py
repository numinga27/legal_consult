from django.test import TestCase, Client
from django.urls import reverse

from .models import HelpOrder, LegalDirection, Payment
from .questionnaire_import import save_package
from .test_questionnaire_import import example


class HelpOrdersTests(TestCase):
    def setUp(self):
        self.questionnaire, _ = save_package(example(), LegalDirection.objects.create(name='Суд'), activate=True)
        self.guided = reverse('core:guided_questionnaire', args=[self.questionnaire.id])
        self.selection = reverse('core:select_help', args=[self.questionnaire.id, 0])
        self.client.get(self.guided)

    def complete(self):
        state = self.client.session[f'guided_questionnaire_{self.questionnaire.id}']
        return self.client.post(self.guided, {'action': 'answer', 'answer': 1, 'revision': state['revision']}, follow=True)

    def fields(self, response):
        return {'full_name': 'Тестовый Покупатель', 'email': 'test@example.com', 'phone': '+7 900 000-00-00',
                'selection': response.context['selection'], 'revision': response.context['revision']}

    def test_cannot_select_before_result_or_without_a_price(self):
        self.assertRedirects(self.client.get(self.selection), self.guided)
        self.complete()
        self.questionnaire.workflow['offer_prices'][0] = ''
        self.questionnaire.save()
        self.assertEqual(self.client.get(self.selection).status_code, 404)

    def test_all_bundles_create_private_unpaid_orders_at_server_prices(self):
        self.complete()
        for index, price in enumerate(['298', '498', '697']):
            url = reverse('core:select_help', args=[self.questionnaire.id, index])
            response = self.client.get(url)
            fields = {**self.fields(response), 'amount': '1', 'result_code': 'evil', 'status': 'paid'}
            response = self.client.post(url, fields, follow=True)
            self.assertContains(response, 'Заказ сохранён')
            order = HelpOrder.objects.get(bundle_index=index)
            self.assertEqual(str(order.amount), price + '.00')
            self.assertEqual(order.result_code, '1')
            self.assertNotIn('full_text', order.summary)
            self.assertContains(response, 'Не оплачен.')
            self.assertEqual(Client().get(reverse('core:help_order', args=[order.id])).status_code, 404)
            self.client.post(url, fields, follow=True)
            self.assertEqual(HelpOrder.objects.filter(bundle_index=index).count(), 1)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertNotContains(Client().get(reverse('core:help_orders')), 'test@example.com')

    def test_invalid_fields_csrf_and_stale_selection_do_not_create_orders(self):
        self.complete()
        response = self.client.get(self.selection)
        fields = self.fields(response)
        invalid = {**fields, 'email': 'invalid', 'phone': 'letters'}
        self.assertContains(self.client.post(self.selection, invalid), 'Введите правильный адрес электронной почты')
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf.post(self.selection, fields).status_code, 403)
        # Changing the questionnaire result in another tab invalidates the form.
        state = self.client.session[f'guided_questionnaire_{self.questionnaire.id}']
        self.client.post(self.guided, {'action': 'restart', 'revision': state['revision']})
        self.assertRedirects(self.client.post(self.selection, fields), self.guided)
        self.assertEqual(HelpOrder.objects.count(), 0)

    def test_changed_price_invalidates_form_and_order_snapshot_is_stable(self):
        self.complete()
        fields = self.fields(self.client.get(self.selection))
        self.questionnaire.workflow['offer_prices'][0] = '400'
        self.questionnaire.save()
        self.assertRedirects(self.client.post(self.selection, fields), self.guided)
        self.assertEqual(HelpOrder.objects.count(), 0)
        fields = self.fields(self.client.get(self.selection))
        self.client.post(self.selection, fields)
        order = HelpOrder.objects.get()
        self.questionnaire.workflow['offer_prices'][0] = '500'
        self.questionnaire.save()
        order.refresh_from_db()
        self.assertEqual(str(order.amount), '400.00')
