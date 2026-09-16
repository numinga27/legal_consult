from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Consultation, CustomerAccount, HelpOrder, LegalDirection, OrderPayment
from .questionnaire_import import save_package
from .test_questionnaire_import import example


@override_settings(SESSION_COOKIE_SECURE=True)
class CustomerAccountTests(TestCase):
    password = 'Test-account-only-57!'

    def setUp(self):
        self.package = example()
        self.package['conclusions']['1']['full_text'] = 'PRIVATE MATERIAL ONLY AFTER VERIFIED PAYMENT'
        self.q, _ = save_package(self.package, LegalDirection.objects.create(name='Суд'), activate=True)
        self.guided = reverse('core:guided_questionnaire', args=[self.q.pk])
        self.register = reverse('core:account_register')
        self.login = reverse('core:account_login')

    def complete(self, client=None):
        client = client or self.client
        client.get(self.guided, secure=True)
        state = client.session[f'guided_questionnaire_{self.q.pk}']
        return client.post(self.guided, {'action': 'answer', 'answer': 1, 'revision': state['revision']}, secure=True, follow=True)

    def signup(self, email='Owner@Example.COM', client=None):
        return (client or self.client).post(self.register, {'email': email, 'password': self.password,
            'password_confirm': self.password, 'is_staff': 'true'}, secure=True, follow=True)

    def order(self):
        selection = reverse('core:select_help', args=[self.q.pk, 0])
        form = self.client.get(selection, secure=True)
        self.client.post(selection, {'selection': form.context['selection'], 'revision': form.context['revision'],
            'full_name': 'Test Customer', 'email': 'owner@example.com', 'phone': '+7 900 000 00 00',
            'status': 'paid', 'amount': '1'}, secure=True)
        return HelpOrder.objects.latest('created_at')

    def test_guest_registration_claims_only_session_records_and_survives_new_device(self):
        self.complete()
        item = Consultation.objects.get()
        order = self.order()
        response = self.signup()
        self.assertContains(response, self.q.name)
        account = CustomerAccount.objects.get()
        self.assertEqual(account.email, 'owner@example.com')
        self.assertFalse(account.user.is_staff)
        item.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(item.user_id, account.user_id)
        self.assertEqual(order.user_id, account.user_id)
        other_device = Client()
        self.assertRedirects(other_device.post(self.login, {'email': 'OWNER@example.com', 'password': self.password}, secure=True), reverse('core:help_orders'))
        response = other_device.get(reverse('core:consultation_detail', args=[item.pk]), secure=True)
        self.assertContains(response, self.package['nodes'][self.package['start']]['text'])
        self.assertNotContains(response, item.private_text)
        self.assertEqual(other_device.get(reverse('core:help_order', args=[order.pk]), secure=True).status_code, 200)

    def test_same_email_on_unrelated_guest_order_does_not_grant_ownership(self):
        self.complete()
        foreign_order = self.order()
        outsider = Client()
        self.signup(client=outsider)
        foreign_order.refresh_from_db()
        self.assertIsNone(foreign_order.user_id)
        self.assertEqual(outsider.get(reverse('core:help_order', args=[foreign_order.pk]), secure=True).status_code, 404)
        self.assertEqual(outsider.get(reverse('core:consultation_detail', args=[foreign_order.consultation_id]), secure=True).status_code, 404)

    def test_result_is_immutable_reload_deduplicates_restart_creates_new_attempt(self):
        self.signup()
        self.complete()
        item = Consultation.objects.get()
        self.client.get(self.guided, secure=True)
        self.assertEqual(Consultation.objects.count(), 1)
        self.client.post(self.guided, {'action': 'restart'}, secure=True)
        self.complete()
        self.assertEqual(Consultation.objects.count(), 2)
        self.q.workflow['conclusions']['1']['title'] = 'Changed later'
        self.q.save()
        item.refresh_from_db()
        self.assertNotEqual(item.result_title, 'Changed later')

    def test_paid_materials_require_verified_amount_and_owner_and_revoke_on_refund(self):
        self.signup(); self.complete()
        order = self.order()
        url = reverse('core:help_order', args=[order.pk])
        self.assertNotContains(self.client.get(url, secure=True), order.private_text)
        confirmation = OrderPayment.objects.create(order=order, provider='test-provider', transaction_id='test-transaction',
            status='paid', amount=Decimal('1'), verified_at=timezone.now())
        self.assertNotContains(self.client.get(url, secure=True), order.private_text)
        confirmation.amount = order.amount; confirmation.save()
        self.assertContains(self.client.get(url, secure=True), order.private_text)
        foreign = Client(); self.signup('other@example.com', client=foreign)
        self.assertEqual(foreign.get(url, secure=True).status_code, 404)
        confirmation.status = 'refunded'; confirmation.save()
        self.assertNotContains(self.client.get(url, secure=True), order.private_text)
        self.assertContains(self.client.get(url, secure=True), 'Возврат')

    def test_duplicate_email_password_validation_csrf_and_login_failure(self):
        self.signup()
        self.client.post(reverse('core:account_logout'), secure=True)
        response = self.signup('owner@example.com')
        self.assertContains(response, 'Не удалось создать аккаунт')
        self.assertEqual(CustomerAccount.objects.count(), 1)
        self.assertContains(self.client.post(self.register, {'email': 'new@example.com', 'password': '123', 'password_confirm': '123'}, secure=True), 'слишком короткий')
        self.assertContains(self.client.post(self.login, {'email': 'owner@example.com', 'password': 'wrong'}, secure=True), 'Не удалось войти')
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.register, {'email': 'test@example.com'}, secure=True).status_code, 403)
        self.assertEqual(self.client.get(reverse('core:account_logout'), secure=True).status_code, 405)

    def test_logout_removes_session_access_and_completed_history_is_private(self):
        self.signup(); self.complete()
        item = Consultation.objects.get()
        self.client.post(reverse('core:account_logout'), secure=True)
        self.assertNotContains(self.client.get(reverse('core:help_orders'), secure=True), item.result_title)
        self.assertRedirects(self.client.get(reverse('core:consultation_detail', args=[item.pk]), secure=True), self.login, fetch_redirect_response=False)

    def test_password_entry_is_disabled_on_unencrypted_production_connection(self):
        response = self.client.get(self.register)
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'type="password"', status_code=503)

    def test_login_rate_limit_is_shared_by_independent_sessions(self):
        for _ in range(10):
            Client().post(self.login, {'email': 'limited@example.com', 'password': 'wrong'}, secure=True)
        self.assertContains(Client().post(self.login, {'email': 'limited@example.com', 'password': 'wrong'}, secure=True), 'Слишком много попыток')

    def test_existing_admin_can_login_by_unique_email_without_new_privileges(self):
        user = get_user_model().objects.create_user('old-owner', email='staff@example.com', password=self.password, is_staff=True)
        self.assertRedirects(self.client.post(self.login, {'email': 'STAFF@example.com', 'password': self.password}, secure=True), reverse('core:help_orders'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
