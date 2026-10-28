import html
import io
from zipfile import ZipFile
from copy import deepcopy
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .questionnaire_import import prepare_import, validate_package, save_package
from .consultation_text import consultation_text
from .route_review import route_review
from .models import LegalDirection, HelpOrder, Consultation


def table_word():
    tables = [
        [['В1: Первый вопрос?', 'А) Да', 'ONLY YES 1'], ['', 'Б) Нет', 'ONLY NO 1'],
         ['В2: Второй вопрос?', 'А) Да', 'ONLY YES 2'], ['', 'Б) Нет', 'ONLY NO 2']],
        [['Заголовок', 'Бесплатный результат', 'Пошаговый план действий (отдельная услуга)'],
         ['Вывод 3:\nОбщий итог', 'FREE ONLY', 'PLAN ONLY']]]
    content = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    for rows in tables:
        content += '<w:tbl>'
        for row in rows:
            content += '<w:tr>' + ''.join('<w:tc>' + ''.join('<w:p><w:r><w:t>' + html.escape(p) + '</w:t></w:r></w:p>' for p in c.split('\n')) + '</w:tc>' for c in row) + '</w:tr>'
        content += '</w:tbl>'
    content += '</w:body></w:document>'
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', content)
    return stream.getvalue()


GRAPH = '''<mxGraphModel><root>
<mxCell id="q1" value="В1" vertex="1" parent="1"/>
<mxCell id="q2" value="В2" vertex="1" parent="1"><mxGeometry x="100" y="100" width="40" height="40"/></mxCell>
<mxCell id="c" value="Вывод 3 Общий итог" vertex="1" parent="1"><mxGeometry x="200" y="200" width="40" height="40"/></mxCell>
<mxCell id="a" edge="1" source="q1" target="q2" value="Да" parent="1"/>
<mxCell id="b" edge="1" source="q1" value="Нет" parent="1"><mxGeometry><mxPoint as="targetPoint" x="100" y="120"/></mxGeometry></mxCell>
<mxCell id="c1" edge="1" source="q2" target="c" value="Да" parent="1"/>
<mxCell id="c2" edge="1" source="q2" target="c" value="Нет" parent="1"/>
</root></mxGraphModel>'''


def package():
    p = prepare_import(GRAPH.encode(), table_word(), 'Тест столбцов')
    p['offer_prices'] = ['100', '200', '300']
    return p


class ColumnImportTests(SimpleTestCase):
    def test_columns_multiline_title_and_no_colon_terminal(self):
        p = package()
        self.assertEqual(validate_package(p), [])
        self.assertEqual(p['conclusions']['3'], {'title': 'Общий итог', 'short_text': 'FREE ONLY',
            'full_text': '', 'plan_text': 'PLAN ONLY', 'source_prices': []})
        self.assertEqual(p['nodes']['q1']['answers'][1]['target'], 'q2')

    def test_nearby_or_overlapping_geometry_is_not_guessed(self):
        for graph in [GRAPH.replace('x="100" y="120"', 'x="99" y="120"'),
                      GRAPH.replace('x="200" y="200"', 'x="100" y="100"')]:
            p = prepare_import(graph.encode(), table_word(), 'Проверка')
            self.assertEqual(p['nodes']['q1']['answers'][1]['target'], '')
            self.assertTrue(validate_package(p))

    def test_each_route_to_same_result_has_its_own_consultation(self):
        p = package()
        report = route_review(p)
        self.assertEqual(report['count'], 4)
        texts = {r['consultation'] for r in report['results'][0]['routes']}
        self.assertEqual(len(texts), 4)
        text = consultation_text(p, [{'node': 'q1', 'answer': 0}, {'node': 'q2', 'answer': 1}], 'result:3')
        self.assertIn('ONLY YES 1', text)
        self.assertIn('ONLY NO 2', text)
        self.assertNotIn('ONLY NO 1', text)
        self.assertNotIn('PLAN ONLY', text)
        with self.assertRaises(ValueError):
            consultation_text(p, [{'node': 'q2', 'answer': 1}], 'result:3')
        self.assertTrue(route_review(p, limit=2)['truncated'])


class ColumnOrderTests(TestCase):
    def test_path_snapshot_stays_private_and_back_removes_old_answers(self):
        q, _ = save_package(package(), LegalDirection.objects.create(name='Раздел'), activate=True)
        url = reverse('core:guided_questionnaire', args=[q.pk])
        self.client.get(url)
        def post(action, answer=0):
            state = self.client.session[f'guided_questionnaire_{q.pk}']
            return self.client.post(url, {'action': action, 'answer': answer, 'revision': state['revision']}, follow=True)
        post('answer', 0);post('back');post('answer', 1)
        result = post('answer', 0)
        self.assertContains(result, 'FREE ONLY')
        self.assertNotContains(result, 'ONLY NO 1')
        self.assertNotContains(result, 'PLAN ONLY')
        selection = reverse('core:select_help', args=[q.pk, 0])
        form = self.client.get(selection)
        self.client.post(selection, {'selection':form.context['selection'], 'revision':form.context['revision'],
            'full_name':'Тест', 'email':'test@example.com', 'phone':'+79000000000'})
        order = HelpOrder.objects.get()
        self.assertIn('ONLY NO 1', order.private_text)
        self.assertIn('ONLY YES 2', order.private_text)
        self.assertNotIn('ONLY YES 1', order.private_text)
        q.workflow['nodes']['q1']['answers'][1]['intermediate_text'] = 'EDITED AFTER ORDER'
        q.save();order.refresh_from_db()
        self.assertNotIn('EDITED AFTER ORDER', order.private_text)
        detail = self.client.get(reverse('core:help_order', args=[order.pk]))
        self.assertNotContains(detail, 'ONLY NO 1')
        self.client.force_login(get_user_model().objects.create_user('owner', is_staff=True))
        review = self.client.get(reverse('core:import_questionnaire') + f'?q={q.pk}')
        self.assertContains(review, 'Проверка маршрутов: 4')
