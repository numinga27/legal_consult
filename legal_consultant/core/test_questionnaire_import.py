import base64
from copy import deepcopy
import html
import io
import json
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile
import zlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, SimpleTestCase
from django.urls import reverse

from .models import LegalDirection, Questionnaire, Question, Answer, Conclusion, Payment
from .questionnaire_import import FORMAT, ImportProblem, prepare_import, save_package, validate_package
from .guided_views import position


def example():
    return json.loads((Path(__file__).parent / 'import_examples/court_order.json').read_text(encoding='utf-8'))


def word_bytes(lines):
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    xml += ''.join('<w:p><w:r><w:t>' + html.escape(line) + '</w:t></w:r></w:p>' for line in lines)
    xml += '</w:body></w:document>'
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return output.getvalue()


GRAPH = '''<mxGraphModel><root>
<mxCell id="q" vertex="1" value="В1"/>
<mxCell id="c1" vertex="1" value="Вывод 1: Один"/>
<mxCell id="c2" vertex="1" value="Вывод 2: Два"/>
<mxCell id="e1" edge="1" source="q" target="c1" value="Да"/>
<mxCell id="e2" edge="1" source="q" target="c2" value="Нет"/>
</root></mxGraphModel>'''
WORD = ['В1: Есть вопрос?', 'А) Да', 'Объяснение да.', 'Б) Нет', 'Объяснение нет.',
        'Вывод 1: Один', 'Бесплатно один.', '99', '199', '299', 'Платно один.',
        'Вывод 2: Два', 'Бесплатно два.', '199', '299', '399', 'Платно два.']


class SourceParserTests(SimpleTestCase):
    def test_plain_html_and_compressed_drawio(self):
        compressed = zlib.compress(quote(GRAPH).encode())[2:-4]
        formats = [GRAPH.encode(),
                   ('<html><div data-mxgraph="' + html.escape(json.dumps({'xml': GRAPH}), quote=True) + '"></div></html>').encode(),
                   ('<mxfile><diagram>' + base64.b64encode(compressed).decode() + '</diagram></mxfile>').encode()]
        for graph in formats:
            with self.subTest(graph=graph[:20]):
                package = prepare_import(graph, word_bytes(WORD), 'Пример')
                self.assertEqual(validate_package(package), [])
                self.assertEqual(package['nodes']['q']['answers'][0]['intermediate_text'], 'Объяснение да.')
                self.assertEqual(package['conclusions']['1']['short_text'], 'Бесплатно один.')
                self.assertEqual(package['conclusions']['1']['full_text'], 'Платно один.')

    def test_missing_edge_does_not_guess_a_result(self):
        graph = GRAPH.replace('target="c2"', '')
        package = prepare_import(graph.encode(), word_bytes(WORD), 'Пример')
        self.assertTrue(validate_package(package))
        self.assertEqual(package['nodes']['q']['answers'][1]['target'], '')

    def test_invalid_bundle_prices_are_rejected(self):
        for prices in [None, [], ['298', '498'], ['-1', '0', 'foo'], ['1.5', '2', '3'], [298, 498, 697]]:
            package = example()
            package['offer_prices'] = prices
            self.assertTrue(validate_package(package), prices)

    def test_conflicting_arrows_require_explicit_resolution(self):
        graph = GRAPH.replace('</root>', '<mxCell id="e3" edge="1" source="q" target="c2" value="Да"/></root>')
        package = prepare_import(graph.encode(), word_bytes(WORD), 'Пример')
        self.assertTrue(validate_package(package))
        self.assertEqual(package['nodes']['q']['answers'][0]['target'], '')

    def test_malformed_start_and_reserved_ids_fail_validation(self):
        package = example()
        package['start'] = []
        self.assertTrue(validate_package(package))
        package = example()
        package['nodes']['result:invalid'] = deepcopy(package['nodes'][package['start']])
        self.assertTrue(validate_package(package))

    def test_invalid_xml_zip_and_duplicate_word_headers(self):
        for graph in [b'<!DOCTYPE x [<!ENTITY a "hello">]><x/>', b'broken', b'<mxfile><diagram>a</diagram><diagram>b</diagram></mxfile>']:
            with self.assertRaises(ImportProblem):
                prepare_import(graph, word_bytes(WORD), 'Пример')
        with self.assertRaises(ImportProblem):
            prepare_import(GRAPH.encode(), b'not a docx', 'Пример')
        with self.assertRaises(ImportProblem):
            prepare_import(GRAPH.encode(), word_bytes(WORD + ['В1: Повтор']), 'Пример')

    def test_cycles_unreachable_results_and_long_titles_rejected(self):
        package = example()
        package['nodes'][package['start']]['answers'][0]['target'] = package['start']
        self.assertTrue(any('цикл' in error for error in validate_package(package)))
        package = example()
        package['conclusions']['extra'] = deepcopy(package['conclusions']['1'])
        self.assertTrue(any('недостижим' in error for error in validate_package(package)))
        package['conclusions']['extra']['title'] = 'x' * 201
        self.assertTrue(validate_package(package))


def all_paths(package, node=None, history=None):
    node = package['start'] if node is None else node
    history = [] if history is None else history
    if node.startswith('result:'):
        yield history, node[7:]
        return
    for i, answer in enumerate(package['nodes'][node]['answers']):
        yield from all_paths(package, answer['target'], history + [{'node': node, 'answer': i}])


def source_expected_result(package, history):
    """Independent outcome matrix transcribed from the two owner documents."""
    values = {package['nodes'][step['node']]['code']: step['answer'] == 0 for step in history}
    if not values['1'] or (values['2'] and not values['2.1']):
        return '1'
    if values['2']:
        if not values['7']:
            return '5' if values['6'] else '8'
        if values['7.1']:
            if not values['7.3']:
                return '2.3'
            if not values['8']:
                return '2.2'
            return '2' if values['8.1'] else '2.1'
        if values['6']:
            return '3' if values['7.2'] else '4'
        return '6' if values['7.2'] else '7'
    if values['3']:
        if values['4']:
            return '9' if values['6'] else '10'
        return '11' if values['6'] else '12'
    if values['4']:
        return '13' if values['6'] else '14'
    return '15'


class ImportedQuestionnaireTests(TestCase):
    def setUp(self):
        self.package = example()
        self.direction = LegalDirection.objects.create(name='Суд и взыскание')
        self.questionnaire, _ = save_package(self.package, self.direction, activate=True)
        self.url = reverse('core:guided_questionnaire', args=[self.questionnaire.id])

    def post_action(self, action, **fields):
        state = self.client.session[f'guided_questionnaire_{self.questionnaire.id}']
        return self.client.post(self.url, {'action': action, 'revision': state['revision'], **fields}, follow=True)

    def post_import(self, fields):
        return self.client.post(reverse('core:import_questionnaire'), {
            'draft_revision': self.client.session.get('questionnaire_import_revision'), **fields})

    def test_every_path_advances_directly_and_matches_source_matrix(self):
        reached = set()
        for history, expected in all_paths(self.package):
            self.assertEqual(expected, source_expected_result(self.package, history))
            self.assertEqual(position(self.package, history), 'result:' + expected)
            self.client.get(self.url)
            self.post_action('restart')
            for step in history:
                before = self.client.get(self.url)
                self.assertEqual(before.context['node'], self.package['nodes'][step['node']])
                self.assertIsNone(before.context['result'])
                self.assertNotContains(before, 'Что это значит для вас')
                for answer in self.package['nodes'][step['node']]['answers']:
                    if answer['intermediate_text']:
                        self.assertNotContains(before, answer['intermediate_text'].split('\n\n')[0])
                response = self.post_action('answer', answer=step['answer'])
                self.assertNotContains(response, 'Продолжить')
                self.assertNotContains(response, 'Что это значит для вас')
            self.assertEqual(response.context['result']['title'], self.package['conclusions'][expected]['title'])
            self.assertContains(response, 'Краткий вывод:')
            self.assertContains(response, 'Получить помощь', count=3)
            self.assertEqual([offer['price'] for offer in response.context['offers']], ['298', '498', '697'])
            self.assertNotIn('full_text', response.context['result'])
            self.assertNotContains(response, self.package['conclusions'][expected]['full_text'].split('\n\n')[0])
            reached.add(expected)
        self.assertEqual(reached, set(self.package['conclusions']))
        self.assertEqual(Payment.objects.count(), 0)

    def test_reload_back_change_answer_and_stale_post(self):
        self.client.get(self.url)
        self.post_action('answer', answer=0)
        self.assertEqual(self.client.get(self.url).context['node']['code'], '2')
        self.post_action('back')
        self.assertEqual(self.client.get(self.url).context['node']['code'], '1')
        self.post_action('answer', answer=1)
        self.assertIsNotNone(self.client.get(self.url).context['result'])
        response = self.client.post(self.url, {'action': 'answer', 'answer': 0, 'revision': 0}, follow=True)
        self.assertIsNotNone(response.context['result'])
        self.post_action('back')
        self.assertEqual(self.client.get(self.url).context['node']['code'], '1')

    def test_completed_result_can_restart_from_an_old_tab(self):
        self.client.get(self.url)
        self.post_action('answer', answer=1)
        response = self.client.get(self.url)
        self.assertContains(response, 'Пройти опрос заново')
        self.assertLess(response.content.index('Краткий вывод:'.encode()),
                        response.content.index('Пройти опрос заново'.encode()))
        response = self.client.post(self.url, {'action': 'restart', 'revision': 0}, follow=True)
        self.assertIsNone(response.context['result'])
        self.assertEqual(response.context['node']['code'], '1')
        self.assertEqual(response.context['state']['history'], [])
        self.assertEqual(self.client.get(self.url).context['node']['code'], '1')

    def test_catalogue_reentry_restarts_completed_but_keeps_unfinished_progress(self):
        entry = reverse('core:user_questionnaire', args=[self.questionnaire.id])
        self.client.get(entry, follow=True)
        self.post_action('answer', answer=0)
        response = self.client.get(entry, follow=True)
        self.assertEqual(response.context['node']['code'], '2')
        self.post_action('restart')
        self.post_action('answer', answer=1)
        response = self.client.get(entry, follow=True)
        self.assertEqual(response.context['node']['code'], '1')
        self.assertIsNone(response.context['result'])

    def test_import_idempotent_versioned_and_invalid_is_atomic(self):
        self.assertFalse(save_package(self.package, self.direction)[1])
        self.assertEqual(Questionnaire.objects.count(), 1)
        changed = deepcopy(self.package)
        changed['name'] += ' v2'
        item, created = save_package(changed, self.direction)
        self.assertTrue(created)
        self.assertFalse(item.is_active)
        changed['nodes'][changed['start']]['answers'][0]['target'] = 'missing'
        with self.assertRaises(ImportProblem):
            save_package(changed, self.direction)
        self.assertEqual(Questionnaire.objects.count(), 2)

    def test_old_explanation_session_advances_once_and_stale_continue_is_safe(self):
        for choice in [0, 1]:
            with self.subTest(choice=choice):
                session = self.client.session
                key = f'guided_questionnaire_{self.questionnaire.id}'
                session[key] = {'history': [], 'pending': choice, 'revision': 5}
                session.save()
                response = self.client.post(self.url, {'action': 'continue', 'revision': 5}, follow=True)
                self.assertEqual(response.context['state']['history'], [{'node': self.package['start'], 'answer': choice}])
                self.assertIsNone(response.context['state']['pending'])
                self.assertEqual(response.context['state']['revision'], 6)
                self.assertEqual(self.client.get(self.url).context['state'], response.context['state'])
                if choice == 0:
                    self.assertEqual(response.context['node']['code'], '2')
                else:
                    self.assertIsNotNone(response.context['result'])

    def test_another_import_uses_direct_answers_without_special_profile(self):
        package = prepare_import(GRAPH.encode(), word_bytes(WORD), 'Другой алгоритм')
        item, _ = save_package(package, self.direction, activate=True)
        url = reverse('core:guided_questionnaire', args=[item.id])
        response = self.client.get(url)
        self.assertNotContains(response, 'Объяснение да.')
        response = self.client.post(url, {'action': 'answer', 'answer': 0, 'revision': 0}, follow=True)
        self.assertContains(response, 'Бесплатно один.')
        self.assertNotContains(response, 'Платно один.')
        self.assertNotContains(response, 'Объяснение да.')
        self.assertContains(response, 'Цена уточняется', count=3)

    def test_reference_result_has_exact_bundles_without_creating_a_payment(self):
        self.client.get(self.url)
        response = self.post_action('answer', answer=1)
        self.assertContains(response, 'Судебный приказ можно отменить с вероятностью 100%!')
        self.assertContains(response, 'Причина: срок в 10 дней на обжалование приказа не пропущен.')
        for text in ['Правовая оценка ситуации', 'Документальное сопровождение', 'Максимальная помощь', '298 ₽', '498 ₽', '697 ₽']:
            self.assertContains(response, text, count=1)
        self.assertEqual([list(offer['services']) for offer in response.context['offers']], [
            ['Консультация', 'Пошаговый план действий'],
            ['Пошаговый план действий', 'Подготовка документов'],
            ['Консультация', 'Пошаговый план действий', 'Подготовка документов'],
        ])
        self.assertContains(response, 'disabled aria-describedby="payment-status"', count=3)
        self.assertEqual(Payment.objects.count(), 0)

    def test_owner_can_set_bundle_prices_for_future_import_and_export_them(self):
        user = get_user_model().objects.create_user(username='price-editor', is_staff=True)
        self.client.force_login(user)
        url = reverse('core:import_questionnaire')
        self.client.post(url, {'action': 'analyze', 'name': 'Новый импорт',
            'graph': SimpleUploadedFile('graph.drawio', GRAPH.encode()),
            'word': SimpleUploadedFile('text.docx', word_bytes(WORD))})
        response = self.post_import({'action': 'download', 'offer_price_0': '300', 'offer_price_1': '500', 'offer_price_2': '700'})
        package = json.loads(response.content)
        self.assertEqual(package['offer_prices'], ['300', '500', '700'])
        self.assertEqual(package['conclusions']['1']['source_prices'], ['99', '199', '299'])

    def test_private_drafts_csrf_and_anonymous_session_isolation(self):
        self.client.get(self.url)
        self.post_action('answer', answer=1)
        other = Client()
        self.assertEqual(other.get(self.url).context['node']['code'], '1')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(self.url)
        self.assertEqual(csrf_client.post(self.url, {'action': 'answer', 'answer': 0, 'revision': 0}).status_code, 403)
        self.questionnaire.is_active = False
        self.questionnaire.save()
        self.assertEqual(other.get(self.url).status_code, 404)

    def test_legacy_endpoints_cannot_modify_or_charge_imported_content(self):
        conclusion = self.questionnaire.conclusions.first()
        answer = self.questionnaire.questions.first().answers.first()
        self.assertEqual(self.client.post(reverse('core:user_payment', args=[conclusion.id])).status_code, 409)
        self.assertEqual(self.client.post(reverse('core:api_generate_document'), json.dumps({'conclusion_id': conclusion.id}), content_type='application/json').status_code, 409)
        for name in ['api_check_answer', 'api_get_next_question']:
            self.assertEqual(self.client.post(reverse('core:' + name), json.dumps({'answer_id': answer.id}), content_type='application/json').status_code, 409)
        self.assertEqual(Payment.objects.count(), 0)
        user = get_user_model().objects.create_user(username='reader', password='test-only')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('core:api_load_workflow', args=[self.questionnaire.id])).status_code, 403)
        for name in ['api_save_workflow', 'api_sync_workflow']:
            self.assertEqual(self.client.post(reverse('core:' + name), json.dumps({'questionnaire_id': self.questionnaire.id, 'workflow': {'nodes': []}}), content_type='application/json').status_code, 409)
        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.workflow['format'], FORMAT)

    def test_staff_upload_review_save_and_export(self):
        url = reverse('core:import_questionnaire')
        self.assertEqual(self.client.get(url).status_code, 302)
        user = get_user_model().objects.create_user(username='owner', password='test-only', is_staff=True)
        self.client.force_login(user)
        response = self.client.post(url, {'action': 'analyze', 'name': 'Тестовый импорт',
            'graph': SimpleUploadedFile('graph.drawio', GRAPH.encode()),
            'word': SimpleUploadedFile('text.docx', word_bytes(WORD))})
        self.assertContains(response, 'Проверьте переходы и тексты')
        self.assertFalse(response.context['errors'])
        response = self.post_import({'action': 'save', 'direction': self.direction.id})
        self.assertContains(response, 'Подтвердите проверку')
        response = self.post_import({'action': 'save', 'direction': self.direction.id, 'reviewed': 'yes'})
        self.assertContains(response, 'Черновик сохранён')
        draft = Questionnaire.objects.get(name='Тестовый импорт')
        self.assertFalse(draft.is_active)
        self.assertEqual(self.client.get(reverse('core:guided_questionnaire', args=[draft.id])).status_code, 200)
        response = self.post_import({'action': 'download'})
        self.assertEqual(json.loads(response.content)['format'], FORMAT)
        response = self.post_import({'action': 'save', 'direction': self.direction.id, 'reviewed': 'yes', 'activate': 'yes'})
        draft.refresh_from_db()
        self.assertTrue(draft.is_active)
        self.assertEqual(Questionnaire.objects.filter(name='Тестовый импорт').count(), 1)

    def test_stale_owner_tab_cannot_overwrite_new_draft_and_direction_is_retained(self):
        user = get_user_model().objects.create_user(username='editor', is_staff=True)
        self.client.force_login(user)
        url = reverse('core:import_questionnaire')
        response = self.client.get(url, {'q': self.questionnaire.id})
        old_revision = response.context['draft_revision']
        self.assertEqual(response.context['selected_direction'], str(self.direction.id))
        self.client.post(url, {'action': 'analyze', 'name': 'Другой опросник',
            'graph': SimpleUploadedFile('graph.drawio', GRAPH.encode()),
            'word': SimpleUploadedFile('text.docx', word_bytes(WORD))})
        response = self.client.post(url, {'action': 'save', 'draft_revision': old_revision,
            'name': 'Устаревшая вкладка', 'direction': self.direction.id, 'reviewed': 'yes'})
        self.assertContains(response, 'Этот просмотр устарел')
        self.assertEqual(self.client.session['questionnaire_import_draft']['name'], 'Другой опросник')
        self.assertEqual(Questionnaire.objects.count(), 1)
