import io
import tempfile
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.test import TestCase, override_settings, SimpleTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import LegalDirection, HelpOrder, OrderPayment, QuestionnaireSource, Consultation
from .questionnaire_import import save_package, validate_package
from .test_import_columns import package, GRAPH, table_word
from .test_questionnaire_import import word_bytes
from .scenario_import import read_scenarios
from .payment_views import materials_ready
from . import yookassa

class SelectionTests(TestCase):
    def setUp(self):
        self.p = package()
        self.q, _ = save_package(self.p, LegalDirection.objects.create(name='Test'), activate=True)
        self.user = get_user_model().objects.create_user('buyer', email='test@example.com')
        self.client.force_login(self.user)
        self.guided = reverse('core:guided_questionnaire', args=[self.q.pk])
        self.client.get(self.guided)
        for a in [0, 1]:
            state = self.client.session[f'guided_questionnaire_{self.q.pk}']
            self.client.post(self.guided, {'action':'answer','answer':a,'revision':state['revision']})
        self.select = reverse('core:select_services', args=[self.q.pk])

    def order(self, choices=('0','1')):
        response = self.client.get(self.select, {'services':choices})
        self.assertEqual(response.status_code,200)
        data = {'services':choices,'selection':response.context['selection'],
                'revision':response.context['revision'],'full_name':'Buyer',
                'email':'test@example.com','phone':'+79000000000','amount':'1'}
        self.client.post(self.select,data)
        return HelpOrder.objects.latest('created_at'),data

    def test_multiple_services_one_order_price_and_pdf_access(self):
        order,data = self.order()
        self.assertEqual(order.amount,Decimal('300'))
        self.assertTrue(materials_ready(order))
        self.assertIn('ONLY YES 1',order.private_text)
        self.assertIn('PLAN ONLY',order.private_text)
        self.assertNotIn('ONLY NO 1',order.private_text)
        self.client.post(self.select,data)
        self.assertEqual(HelpOrder.objects.count(),1)
        url=reverse('core:download_order_pdf',args=[order.pk])
        self.assertEqual(self.client.get(url).status_code,404)
        payment=OrderPayment.objects.create(order=order,provider='fixture',transaction_id='fixture',
            status='paid',amount=order.amount,verified_at=timezone.now())
        response=self.client.get(url)
        self.assertEqual(response['Content-Type'],'application/pdf')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
        outsider=get_user_model().objects.create_user('outsider')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.user)
        payment.status='refunded';payment.save()
        self.assertEqual(self.client.get(url).status_code,404)

    def test_tampering_and_missing_material_prevent_payment(self):
        response=self.client.get(self.select,{'services':['0','1']})
        self.client.post(self.select,{'services':['0','2'],'selection':response.context['selection'],
            'revision':response.context['revision'],'full_name':'Buyer','email':'test@example.com','phone':'+79000000000'})
        self.assertEqual(HelpOrder.objects.count(),0)
        order,_=self.order(('0','2'))
        self.assertFalse(materials_ready(order))
        with patch('core.yookassa.create_checkout') as api:
            self.client.post(reverse('core:pay_order',args=[order.pk]))
            api.assert_not_called()
        self.assertEqual(self.client.get(self.select,{'services':['0','0']}).status_code,302)

    @override_settings(YOOKASSA_RECEIPTS='1',YOOKASSA_VAT_CODE='1')
    def test_receipt_contains_each_selected_service(self):
        order,_=self.order()
        payload=yookassa.payload(order,uuid4())
        self.assertEqual(len(payload['receipt']['items']),2)
        self.assertEqual([i['amount']['value'] for i in payload['receipt']['items']],['100.00','200.00'])
        self.assertEqual(payload['amount']['value'],'300.00')

    def test_landing_guest_and_draft_visibility(self):
        self.client.logout()
        url=reverse('core:questionnaire_landing',args=[self.q.pk])
        self.assertContains(self.client.get(url),self.q.name)
        self.assertEqual(self.client.get(self.guided).status_code,200)
        self.q.is_active=False;self.q.save()
        self.assertEqual(self.client.get(url).status_code,404)

class ScenarioTests(SimpleTestCase):
    def test_conflicting_and_empty_scenarios_are_blocked(self):
        checks=read_scenarios(word_bytes(['Вывод 3:','Сценарий 1:','В1-да; В2-нет.',
                                         'Вывод 4:','Сценарий 1:','В1-да; В2-нет.',
                                         'Вывод 6:','Сценарий 1:']))
        p=package();p['scenario_checks']=checks
        errors=validate_package(p)
        self.assertTrue(any('такой же путь' in e for e in errors))
        self.assertTrue(any('путь пустой' in e for e in errors))
        p['scenario_checks']=checks[:1]
        self.assertEqual(validate_package(p),[])

class SourceTests(TestCase):
    def test_original_files_preserved_staff_only_and_linked_to_version(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(PROTECTED_MEDIA_ROOT=directory):
            staff=get_user_model().objects.create_user('admin',is_staff=True)
            self.client.force_login(staff)
            url=reverse('core:import_questionnaire')
            response=self.client.post(url,{'action':'analyze','name':'Import',
                'graph':SimpleUploadedFile('scheme.xml',GRAPH.encode()),
                'word':SimpleUploadedFile('texts.docx',table_word())})
            self.assertEqual(response.status_code,200)
            self.assertEqual(QuestionnaireSource.objects.count(),2)
            source=QuestionnaireSource.objects.get(kind='graph')
            download=reverse('core:download_source',args=[source.pk])
            self.assertEqual(b''.join(self.client.get(download).streaming_content),GRAPH.encode())
            direction=LegalDirection.objects.create(name='Test')
            revision=response.context['draft_revision']
            response=self.client.post(url,{'action':'save','draft_revision':revision,'reviewed':'yes',
                                            'direction':direction.pk})
            q=response.context['saved']
            self.assertIsNotNone(q)
            self.assertEqual(q.source_files.count(),2)
            self.client.get(url,{'q':q.pk})
            self.assertEqual(set(self.client.session['questionnaire_import_sources']),
                             set(q.source_files.values_list('pk',flat=True)))
            self.client.logout()
            self.assertEqual(self.client.get(download).status_code,302)
