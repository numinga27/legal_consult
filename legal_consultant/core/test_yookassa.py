import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone
from .models import HelpOrder, LegalDirection, OrderPayment, YooKassaAttempt, PlategaAttempt
from .questionnaire_import import save_package
from .test_import_columns import package
from . import yookassa, platega


@override_settings(PAYMENT_PROVIDER='yookassa', YOOKASSA_ENABLED='1', YOOKASSA_SHOP_ID='123',
                   YOOKASSA_SECRET_KEY='fixture-secret', YOOKASSA_TEST='0', YOOKASSA_RECEIPTS='0', YOOKASSA_RECEIPTS_EXTERNAL='1')
class YooKassaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('payer')
        q, _ = save_package(package(), LegalDirection.objects.create(name='Тест'), activate=True)
        self.order = HelpOrder.objects.create(user=self.user, owner_id=uuid.uuid4(), questionnaire=q,
            fingerprint='a'*64, result_code='3', bundle_index=0, summary={'service_code':'consultation', 'title':'Консультация'},
            private_text='PRIVATE', amount=100, full_name='Test', email='test@example.com', phone='+79000000000')
        self.client.force_login(self.user)
        self.pay = reverse('core:pay_order', args=[self.order.pk])
        self.callback = reverse('core:yookassa_callback')
        self.pid = uuid.uuid4()

    def attempt(self):
        return YooKassaAttempt.objects.create(order=self.order, payment_id=self.pid,
            checkout_url='https://yoomoney.ru/pay', status='pending')

    def remote(self, attempt, status='succeeded', **extra):
        return {'id':str(self.pid), 'amount':{'value':'100.00', 'currency':'RUB'},
            'recipient':{'account_id':'123'}, 'test':False, 'paid':status=='succeeded', 'status':status,
            'metadata':{'order_id':str(self.order.pk),'attempt_id':str(attempt.pk)},
            'confirmation':{'type':'redirect','confirmation_url':'https://yoomoney.ru/pay'}, **extra}

    def notify(self, event='payment.succeeded', **extra):
        return self.client.post(self.callback, {'event':event, 'object':{'id':str(self.pid), **extra}}, content_type='application/json')

    @patch('core.yookassa.api')
    def test_checkout_server_price_and_reuse(self, api):
        def create(method, path, payload=None, idempotence=None):
            attempt=YooKassaAttempt.objects.get()
            return self.remote(attempt,'pending')
        api.side_effect=create
        r=self.client.post(self.pay, {'amount':'1'})
        self.assertRedirects(r,'https://yoomoney.ru/pay',fetch_redirect_response=False)
        attempt=YooKassaAttempt.objects.get()
        self.assertEqual(attempt.request_payload['amount']['value'],'100.00')
        self.assertEqual(api.call_args.args[3],attempt.pk)
        self.client.post(self.pay)
        self.assertEqual(api.call_args.args[0],'GET')
        self.assertEqual(YooKassaAttempt.objects.count(),1)

    @patch('core.yookassa.api')
    def test_timeout_retries_same_payload_and_key_then_recovers_success(self, api):
        api.side_effect=platega.PaymentError('timeout')
        self.client.post(self.pay)
        first=api.call_args.args
        attempt=YooKassaAttempt.objects.get()
        self.assertEqual(attempt.status,'unknown')
        api.side_effect=None
        api.return_value=self.remote(attempt,'succeeded')
        self.client.post(self.pay)
        self.assertEqual(api.call_args_list[-2].args,first)
        self.assertEqual(YooKassaAttempt.objects.count(),1)
        self.assertEqual(OrderPayment.objects.get().status,'paid')

    @patch('core.yookassa.api')
    def test_old_unknown_is_never_retried_after_idempotency_window(self, api):
        attempt=YooKassaAttempt.objects.create(order=self.order,status='unknown',request_payload={'saved':True})
        YooKassaAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now()-timedelta(hours=24))
        self.client.post(self.pay)
        api.assert_not_called()

    @patch('core.yookassa.api')
    def test_untrusted_callbacks_do_not_grant_access(self, api):
        attempt=self.attempt()
        for extra in ({'amount':{'value':'1','currency':'RUB'}}, {'test':True}, {'recipient':{'account_id':'other'}},
                      {'metadata':{'order_id':str(uuid.uuid4()),'attempt_id':str(attempt.pk)}}):
            api.return_value=self.remote(attempt,**extra)
            self.assertEqual(self.notify().status_code,503)
        api.return_value=self.remote(attempt,'pending')
        self.assertEqual(self.notify().status_code,200)
        self.assertFalse(OrderPayment.objects.exists())
        self.assertEqual(self.client.post(self.callback,[],content_type='application/json').status_code,400)

    @patch('core.yookassa.api')
    def test_paid_idempotent_refund_terminal_and_partial_retains_access(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt)
        self.notify();self.notify()
        self.assertEqual(OrderPayment.objects.count(),1)
        detail=reverse('core:help_order',args=[self.order.pk])
        self.assertContains(self.client.get(detail),'PRIVATE')
        api.return_value=self.remote(attempt,refunded_amount={'value':'25.00','currency':'RUB'})
        self.notify('refund.succeeded',payment_id=str(self.pid))
        self.assertEqual(OrderPayment.objects.get().status,'paid')
        api.return_value=self.remote(attempt,refunded_amount={'value':'100.00','currency':'RUB'})
        self.notify('refund.succeeded',payment_id=str(self.pid))
        self.assertEqual(OrderPayment.objects.get().status,'refunded')
        api.return_value=self.remote(attempt)
        self.notify()
        self.assertNotContains(self.client.get(detail),'PRIVATE')

    @patch('core.yookassa.api')
    def test_cancel_new_attempt_and_cross_provider_guard(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt,'canceled')
        self.client.post(self.pay)
        attempt.refresh_from_db();self.assertFalse(attempt.active)
        api.return_value=self.remote(attempt,'pending')
        yookassa.refresh(attempt)
        attempt.refresh_from_db();self.assertFalse(attempt.active)
        PlategaAttempt.objects.create(order=self.order)
        api.reset_mock()
        self.client.post(self.pay)
        api.assert_not_called()

    @patch('core.yookassa.api')
    def test_disabled_ownership_csrf_and_materials(self, api):
        with override_settings(YOOKASSA_ENABLED='0'):
            self.client.post(self.pay)
        self.order.private_text='';self.order.save();self.client.post(self.pay)
        other=Client();other.force_login(get_user_model().objects.create_user('other'))
        self.assertEqual(other.post(self.pay).status_code,404)
        self.assertEqual(Client().post(self.pay).status_code,302)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user)
        self.assertEqual(strict.post(self.pay).status_code,403)
        self.assertEqual(self.client.get(self.pay).status_code,405)
        api.assert_not_called()

    def test_receipt_configuration_and_checkout_allowlist(self):
        with override_settings(YOOKASSA_RECEIPTS_EXTERNAL='0'):
            self.assertFalse(yookassa.enabled())
            with self.assertRaises(platega.PaymentError):yookassa.payload(self.order,uuid.uuid4())
            with override_settings(YOOKASSA_RECEIPTS='1',YOOKASSA_VAT_CODE='1'):
                data=yookassa.payload(self.order,uuid.uuid4())
                self.assertEqual(data['receipt']['customer']['email'],'test@example.com')
                self.assertIs(data['receipt']['internet'], True)
                self.assertEqual(data['receipt']['items'][0]['vat_code'],1)
                with override_settings(YOOKASSA_TAX_SYSTEM_CODE='2'):
                    self.assertEqual(yookassa.payload(self.order,uuid.uuid4())['receipt']['tax_system_code'],2)
        for url in ('https://yoomoney.ru.evil.example/pay','http://yoomoney.ru/pay','https://me@ yoomoney.ru/pay','https://yoomoney.ru:bad/'):
            self.assertFalse(yookassa.safe_checkout(url))

    @patch('core.yookassa.api')
    def test_return_checks_api_and_does_not_trust_query_string(self, api):
        attempt=self.attempt();api.return_value=self.remote(attempt,'pending')
        detail=reverse('core:help_order',args=[self.order.pk])
        self.assertNotContains(self.client.get(detail+'?status=succeeded'),'PRIVATE')
        self.assertFalse(OrderPayment.objects.exists())
        self.client.get(detail)
        self.assertEqual(api.call_count,1)
        YooKassaAttempt.objects.filter(pk=attempt.pk).update(checked_at=None)
        api.return_value=self.remote(attempt)
        self.assertContains(self.client.get(detail),'PRIVATE')

    @patch('core.yookassa.build_opener')
    def test_transport_auth_idempotence_and_sanitized_error(self, build):
        import json
        from urllib.error import URLError
        from urllib.request import HTTPRedirectHandler
        reply=build.return_value.open.return_value.__enter__.return_value
        reply.status=200;reply.read.return_value=b'{"status":"pending"}'
        key=uuid.uuid4()
        self.assertEqual(yookassa.api('POST','/payments',{'value':1},key),{'status':'pending'})
        req=build.return_value.open.call_args.args[0]
        self.assertEqual(req.full_url,'https://api.yookassa.ru/v3/payments')
        self.assertEqual(req.get_header('Idempotence-key'),str(key))
        self.assertTrue(req.get_header('Authorization').startswith('Basic '))
        self.assertIsNone(build.call_args.args[0].redirect_request(None,None,None,None,None,None))
        build.return_value.open.side_effect=URLError('fixture-secret')
        with self.assertRaises(platega.PaymentError) as caught:yookassa.api('GET','/me')
        self.assertNotIn('fixture-secret',str(caught.exception))
