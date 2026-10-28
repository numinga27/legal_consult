import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from .models import HelpOrder, LegalDirection, OrderPayment, PlategaAttempt
from .questionnaire_import import save_package
from .test_import_columns import package
from . import platega


@override_settings(PLATEGA_ENABLED='1', PLATEGA_MERCHANT_ID='test-merchant', PLATEGA_SECRET='test-secret')
class PlategaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('payer')
        self.q, _ = save_package(package(), LegalDirection.objects.create(name='Тест'), activate=True)
        self.order = HelpOrder.objects.create(user=self.user, owner_id=uuid.uuid4(), questionnaire=self.q,
            fingerprint='f' * 64, result_code='3', bundle_index=0,
            summary={'service_code':'consultation'}, private_text='PRIVATE', amount=100,
            full_name='Test', email='test@example.com', phone='+79000000000')
        self.client.force_login(self.user)
        self.pay = reverse('core:pay_order', args=[self.order.pk])
        self.callback = reverse('core:platega_callback')
        self.pid = uuid.uuid4()

    def attempt(self):
        return PlategaAttempt.objects.create(order=self.order, transaction_id=self.pid,
            checkout_url='https://pay.platega.io/?id=test', status='PENDING')

    def remote(self, attempt, status='CONFIRMED', **extra):
        return {'id':str(self.pid), 'paymentDetails':{'amount':100, 'currency':'RUB'},
                'payload':str(attempt.pk), 'status':status, **extra}

    def callback_post(self, **extra):
        return self.client.post(self.callback, {'id':str(self.pid),'amount':100,'currency':'RUB','status':'CONFIRMED',**extra},
            content_type='application/json', HTTP_X_MERCHANTID='test-merchant', HTTP_X_SECRET='test-secret')

    @patch('core.platega.api')
    def test_create_server_amount_and_reuse_not_duplicate(self, api):
        api.return_value={'transactionId':str(self.pid), 'url':'https://pay.platega.io/?id=test','status':'PENDING'}
        response=self.client.post(self.pay, {'amount':1})
        self.assertRedirects(response,'https://pay.platega.io/?id=test',fetch_redirect_response=False)
        attempt=PlategaAttempt.objects.get()
        self.assertEqual(api.call_args.args[2]['paymentDetails']['amount'],100)
        api.return_value=self.remote(attempt,'PENDING')
        self.client.post(self.pay)
        self.assertEqual(PlategaAttempt.objects.count(),1)
        self.assertEqual(api.call_args.args[0],'GET')
        self.assertFalse(OrderPayment.objects.exists())

    @patch('core.platega.api')
    def test_timeout_never_blindly_creates_second_invoice(self, api):
        api.side_effect=platega.PaymentError('timeout')
        self.client.post(self.pay);self.client.post(self.pay)
        self.assertEqual(api.call_count,1)
        self.assertEqual(PlategaAttempt.objects.get().status,'UNKNOWN')

    @patch('core.platega.api')
    def test_forged_or_wrong_amount_does_not_grant_access(self, api):
        attempt=self.attempt()
        self.assertEqual(self.client.post(self.callback, {}, content_type='application/json').status_code,403)
        self.assertEqual(self.callback_post(amount=1).status_code,400)
        api.assert_not_called()
        api.return_value=self.remote(attempt,paymentDetails={'amount':1,'currency':'RUB'})
        self.assertEqual(self.callback_post().status_code,503)
        api.return_value=self.remote(attempt,payload='another-order')
        self.assertEqual(self.callback_post().status_code,503)
        self.assertFalse(OrderPayment.objects.exists())

    @patch('core.platega.api')
    def test_confirmation_idempotent_and_refund_cannot_reopen(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt)
        self.assertEqual(self.callback_post().status_code,200)
        self.assertEqual(self.callback_post().status_code,200)
        self.assertEqual(OrderPayment.objects.count(),1)
        detail=reverse('core:help_order',args=[self.order.pk])
        self.assertContains(self.client.get(detail),'PRIVATE')
        api.return_value=self.remote(attempt,'CHARGEBACKED');self.callback_post()
        api.return_value=self.remote(attempt,'CONFIRMED');self.callback_post()
        self.assertEqual(OrderPayment.objects.get().status,'refunded')
        self.assertNotContains(self.client.get(detail),'PRIVATE')

    @patch('core.platega.api')
    def test_pending_and_return_url_cannot_unlock_materials(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt,'PENDING')
        self.callback_post()
        self.client.get(reverse('core:help_order',args=[self.order.pk])+'?status=CONFIRMED')
        self.assertFalse(OrderPayment.objects.exists())

    @patch('core.platega.api')
    def test_cancellation_allows_new_explicit_attempt(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt,'CANCELED')
        self.client.post(self.pay)
        self.assertFalse(PlategaAttempt.objects.get().active)
        api.return_value={'transactionId':str(uuid.uuid4()),'url':'https://pay.platega.io/?id=new','status':'PENDING'}
        self.client.post(self.pay)
        self.assertEqual(PlategaAttempt.objects.count(),2)

    @patch('core.platega.api')
    def test_disabled_guest_other_user_empty_material_and_csrf(self, api):
        with override_settings(PLATEGA_ENABLED='0'):
            self.client.post(self.pay)
        self.order.private_text='';self.order.save();self.client.post(self.pay)
        other=Client();other.force_login(get_user_model().objects.create_user('other'))
        self.assertEqual(other.post(self.pay).status_code,404)
        self.assertEqual(Client().post(self.pay).status_code,302)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user)
        self.assertEqual(strict.post(self.pay).status_code,403)
        self.assertEqual(self.client.get(self.pay).status_code,405)
        api.assert_not_called()

    @patch('core.platega.api')
    def test_untrusted_checkout_url_rejected(self, api):
        api.return_value={'transactionId':str(self.pid),'url':'https://evil.example/','status':'PENDING'}
        self.client.post(self.pay)
        self.assertEqual(PlategaAttempt.objects.get().status,'UNKNOWN')
        self.assertFalse(OrderPayment.objects.exists())

    @patch('core.platega.api')
    def test_dispute_holds_access_and_partial_refund_preserves_it(self, api):
        attempt = self.attempt()
        detail = reverse('core:help_order', args=[self.order.pk])
        api.return_value = self.remote(attempt, 'CONFIRMED')
        self.callback_post()
        api.return_value = self.remote(attempt, 'DISPUTED')
        self.assertEqual(self.callback_post().status_code, 200)
        self.assertEqual(OrderPayment.objects.get().status, 'held')
        self.assertNotContains(self.client.get(detail), 'PRIVATE')
        api.return_value = self.remote(attempt, 'PARTIALLY_REFUNDED')
        self.assertEqual(self.callback_post().status_code, 200)
        self.assertContains(self.client.get(detail), 'PRIVATE')

    @patch('core.platega.api')
    def test_duplicate_provider_id_does_not_bind_another_order(self, api):
        self.attempt()
        other_order = HelpOrder.objects.get(pk=self.order.pk)
        other_order.pk = uuid.uuid4()
        other_order.fingerprint = 'b' * 64
        other_order.save(force_insert=True)
        api.return_value = {'transactionId': str(self.pid), 'url': 'https://pay.platega.io/?id=test', 'status': 'PENDING'}
        with self.assertRaises(platega.PaymentError):
            platega.create_checkout(other_order)
        self.assertEqual(PlategaAttempt.objects.get(order=other_order).status, 'UNKNOWN')
        self.assertFalse(OrderPayment.objects.exists())
