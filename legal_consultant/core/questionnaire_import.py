"""Deterministic Draw.io + DOCX import. Uploaded HTML is parsed, never executed."""
import base64
import hashlib
import html
import io
import json
import re
import zlib
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from django.db import transaction
from .models import Questionnaire, Question, Answer, Conclusion, AnswerConclusion

FORMAT = 'questionnaire-import-v1'
MAX_BYTES = 5 * 1024 * 1024
Q_RE = re.compile(r'^В\s*(\d+(?:\.\d+)*)\s*(?::\s*|\s+|$)', re.I)
C_RE = re.compile(r'^Вывод\s+(\d+(?:\.\d+)*)\s*:\s*(.*)', re.I)


class ImportProblem(ValueError):
    pass


def xml_root(data):
    if len(data) > MAX_BYTES or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ImportProblem('XML слишком большой или содержит запрещённые объявления.')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportProblem('Не удалось прочитать XML схемы или Word.') from exc


class GraphHTML(HTMLParser):
    graphs = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-mxgraph' in attrs:
            if self.graphs is None:
                self.graphs = []
            self.graphs.append(json.loads(attrs['data-mxgraph'])['xml'])


def plain(value):
    return html.unescape(re.sub(r'<[^>]*>', '', re.sub(r'<br\s*/?>', '\n', value, flags=re.I))).strip()


def read_graph(data):
    if len(data) > MAX_BYTES:
        raise ImportProblem('Схема должна быть не больше 5 МБ.')
    try:
        if b'data-mxgraph' in data:
            parser = GraphHTML()
            parser.feed(data.decode('utf-8-sig'))
            if len(parser.graphs or []) != 1:
                raise ImportProblem('Загрузите HTML с одной схемой Draw.io.')
            data = parser.graphs[0].encode()
        root = xml_root(data)
        pages = list(root.iter('diagram'))
        if len(pages) > 1:
            raise ImportProblem('Экспортируйте нужную страницу схемы отдельным файлом.')
        if pages and pages[0].find('mxGraphModel') is None:
            compressed = base64.b64decode(pages[0].text or '', validate=True)
            decoder = zlib.decompressobj(-15)
            expanded = decoder.decompress(compressed, MAX_BYTES + 1)
            if len(expanded) > MAX_BYTES or not decoder.eof:
                raise ImportProblem('Распакованная схема превышает лимит 5 МБ.')
            root = xml_root(unquote(expanded.decode()).encode())
        cells = list(root.iter('mxCell'))
        if not cells or len(cells) > 3000:
            raise ImportProblem('В схеме нет блоков или больше 3000 элементов.')
        return cells
    except (KeyError, ValueError, UnicodeError, zlib.error) as exc:
        raise ImportProblem('Не удалось прочитать Draw.io. Нужен .drawio, .xml или .drawio.html.') from exc


def read_word(data):
    if len(data) > MAX_BYTES:
        raise ImportProblem('Word должен быть не больше 5 МБ.')
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            item = archive.getinfo('word/document.xml')
            if item.file_size > MAX_BYTES:
                raise ImportProblem('Распакованный текст Word превышает 5 МБ.')
            root = xml_root(archive.read(item))
    except (BadZipFile, KeyError, RuntimeError) as exc:
        raise ImportProblem('Нужен незашифрованный документ .docx.') from exc
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = [''.join(t.text or '' for t in p.findall('.//w:t', ns)).strip()
                  for p in root.findall('.//w:p', ns)]
    questions, conclusions = {}, {}
    section, answer = None, None
    for line in paragraphs:
        if not line:
            continue
        qm, cm = Q_RE.match(line), C_RE.match(line)
        am = re.match(r'^[АБВГA-D]\)\s*(.+)', line)
        if qm:
            code = qm[1]
            if code in questions:
                raise ImportProblem(f'Повторный заголовок В{code} в Word.')
            section = questions[code] = {'text': line[qm.end():].strip(), 'answers': {}}
            answer = None
        elif cm:
            if cm[1] in conclusions:
                raise ImportProblem(f'Повторный Вывод {cm[1]} в Word.')
            section = conclusions[cm[1]] = {'title': cm[2], 'lines': []}
            answer = None
        elif section is not None and 'lines' in section:
            section['lines'].append(line)
        elif am and section is not None:
            answer = am[1].strip()
            if answer in section['answers']:
                raise ImportProblem(f'Повторный ответ {answer} в Word.')
            section['answers'][answer] = []
        elif answer and line != 'Выводы к таблице:':
            section['answers'][answer].append(line)
    if not questions or not conclusions:
        raise ImportProblem('Word должен содержать заголовки В1: …, А) Да, Б) Нет и Вывод 1: …')
    for question in questions.values():
        question['answers'] = {key: '\n\n'.join(lines) if lines != ['-'] else ''
                               for key, lines in question['answers'].items()}
    for conclusion in conclusions.values():
        lines = conclusion.pop('lines')
        prices = next((i for i in range(len(lines) - 2)
                       if all(re.fullmatch(r'\d{1,6}', s) for s in lines[i:i + 3])), None)
        conclusion.update(short_text='\n\n'.join(lines if prices is None else lines[:prices]),
                          full_text='' if prices is None else '\n\n'.join(lines[prices + 3:]),
                          source_prices=[] if prices is None else lines[prices:prices + 3])
    return questions, conclusions, paragraphs


def prepare_import(graph_bytes, word_bytes, name):
    cells = read_graph(graph_bytes)
    texts, conclusions, paragraphs = read_word(word_bytes)
    # Some drawings contain both an explanatory sketch and a detailed numbered tree.
    vertices = {c.get('id'): c for c in cells if c.get('vertex') == '1'}
    compact = {key: c for key, c in vertices.items() if re.fullmatch(r'В\d+(?:\.\d+)*', plain(c.get('value', '')), re.I)}
    question_cells = compact or {key: c for key, c in vertices.items() if Q_RE.match(plain(c.get('value', '')))}
    notes = []
    if compact:
        notes.append('Использована подробная схема с короткими номерами вопросов; поясняющий эскиз исключён.')
    package = {'format': FORMAT, 'name': name.strip(), 'start': '', 'nodes': {},
               'conclusions': conclusions, 'notes': notes,
               'sources': {'graph_sha256': hashlib.sha256(graph_bytes).hexdigest(),
                           'word_sha256': hashlib.sha256(word_bytes).hexdigest()}}
    for key, cell in question_cells.items():
        code = Q_RE.match(plain(cell.get('value', '')))[1]
        if code not in texts:
            raise ImportProblem(f'В Word нет текста В{code}.')
        package['nodes'][key] = {'code': code, 'text': texts[code]['text'],
                                'answers': [{'text': label, 'intermediate_text': content, 'target': ''}
                                            for label, content in texts[code]['answers'].items()]}
    terminal_cells = {key: C_RE.match(plain(c.get('value', '')))[1] for key, c in vertices.items()
                      if C_RE.match(plain(c.get('value', '')))}
    destinations = {**{key: key for key in question_cells},
                    **{key: 'result:' + code for key, code in terminal_cells.items()}}
    incoming, seen_answers = set(), set()
    for cell in cells:
        if cell.get('edge') != '1' or cell.get('source') not in question_cells:
            continue
        node = package['nodes'][cell.get('source')]
        label = plain(cell.get('value', ''))
        labels = [plain(c.get('value', '')) for c in cells if c.get('parent') == cell.get('id')]
        if not label and labels:
            label = ' '.join(labels)
        if not label:
            color = re.search(r'strokeColor=(#[0-9A-Fa-f]{6});', cell.get('style', ''))
            if color and color[1].upper() in {'#33FF33', '#66FF66', '#00FF00'}:
                label = 'Да'
            elif color and color[1].upper() in {'#FF0000', '#FF3333'}:
                label = 'Нет'
        target = destinations.get(cell.get('target'), '')
        if not target:
            notes.append(f'В{node["code"]}, {label or "ответ без подписи"}: стрелка {cell.get("id")} не привязана. Выберите переход.')
        matched = [a for a in node['answers'] if a['text'].casefold() == label.casefold()]
        answer_key = (cell.get('source'), label.casefold())
        if len(matched) == 1 and answer_key not in seen_answers:
            matched[0]['target'] = target
        else:
            if len(matched) == 1:
                matched[0]['target'] = ''
            notes.append(f'В{node["code"]}: не удалось однозначно сопоставить ответ на стрелке {cell.get("id")}.')
        seen_answers.add(answer_key)
        incoming.add(target)
    starts = [key for key in package['nodes'] if key not in incoming]
    if len(starts) == 1:
        package['start'] = starts[0]
    else:
        notes.append('Выберите первый вопрос: у схемы несколько начал или есть непривязанные стрелки.')
    from .questionnaire_import_profiles import refine_court_order
    refine_court_order(package, cells, paragraphs)
    package['notes'].append('Цены сохранены как числа из Word; назначение услуг и платёжная выдача требуют настройки. Тексты перенесены без юридической редактуры.')
    return package


def validate_package(package):
    errors = []
    if not isinstance(package, dict) or package.get('format') != FORMAT:
        return ['Неподдерживаемый формат импорта.']
    prices = package.get('offer_prices', ['', '', ''])
    if (not isinstance(prices, list) or len(prices) != 3 or
            any(not isinstance(price, str) or (price != '' and not re.fullmatch(r'[1-9][0-9]{0,6}', price)) for price in prices)):
        errors.append('Укажите три цены пакетов: целые рубли от 1 до 9999999 или пустое поле.')
    nodes, results = package.get('nodes'), package.get('conclusions')
    if not isinstance(nodes, dict) or not isinstance(results, dict) or not nodes or not results:
        return ['Нужны вопросы и результаты.']
    if len(nodes) > 500 or len(results) > 500:
        return ['Не больше 500 вопросов и 500 результатов за один импорт.']
    if not isinstance(package.get('name'), str) or not 1 <= len(package['name']) <= 200:
        errors.append('Название должно содержать от 1 до 200 символов.')
    if not isinstance(package.get('start'), str) or package['start'] not in nodes:
        errors.append('Выберите первый вопрос.')
    for key, node in nodes.items():
        if not isinstance(key, str) or not key or key.startswith('result:'):
            errors.append('Номер блока должен быть строкой без префикса result:.')
        if not isinstance(node, dict) or not isinstance(node.get('text'), str) or not node['text'].strip():
            errors.append(f'{key}: нет текста вопроса.')
            continue
        answers = node.get('answers')
        if not isinstance(answers, list) or not 2 <= len(answers) <= 20:
            errors.append(f'{key}: нужно от 2 до 20 ответов.')
            continue
        labels = set()
        for answer in answers:
            if not isinstance(answer, dict):
                errors.append(f'{key}: некорректный ответ.')
                continue
            label, target = answer.get('text'), answer.get('target')
            if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200 or label.casefold() in labels:
                errors.append(f'{key}: пустой, повторный или слишком длинный ответ.')
            else:
                labels.add(label.casefold())
            if not isinstance(answer.get('intermediate_text', ''), str):
                errors.append(f'{key}: некорректный текст подсказки.')
            if not isinstance(target, str) or (target not in nodes and (not target.startswith('result:') or target[7:] not in results)):
                errors.append(f'В{node.get("code", key)}, «{label}»: выберите существующий вопрос или вывод.')
    for key, result in results.items():
        if not isinstance(key, str) or not key:
            errors.append('Номер вывода должен быть непустой строкой.')
        if not isinstance(result, dict) or any(not isinstance(result.get(field), str)
                                               for field in ['title', 'short_text', 'full_text']):
            errors.append(f'Вывод {key}: неверный формат текстов.')
        elif not result['title'].strip() or not result['short_text'].strip() or len(result['title']) > 200:
            errors.append(f'Вывод {key}: нужен заголовок до 200 символов и бесплатный текст.')
    if errors:
        return errors
    visited, active, reached = set(), set(), set()
    def visit(key):
        if key.startswith('result:'):
            reached.add(key[7:])
            return
        if key in active:
            errors.append(f'Обнаружен цикл возле В{nodes[key].get("code", key)}.')
            return
        if key in visited:
            return
        visited.add(key)
        active.add(key)
        for answer in nodes[key]['answers']:
            visit(answer['target'])
        active.remove(key)
    visit(package['start'])
    for key in nodes.keys() - visited:
        errors.append(f'В{nodes[key].get("code", key)} ({key}) недостижим от начала.')
    for key in results.keys() - reached:
        errors.append(f'Вывод {key} недостижим от начала.')
    return errors


@transaction.atomic
def save_package(package, direction, *, activate=False):
    errors = validate_package(package)
    if errors:
        raise ImportProblem('\n'.join(errors))
    # Never replace an existing questionnaire or its sessions on reimport.
    digest = hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for existing in Questionnaire.objects.filter(direction=direction):
        if existing.workflow.get('import_digest') == digest:
            if activate and not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=['is_active'])
            return existing, False
    questionnaire = Questionnaire.objects.create(direction=direction, name=package['name'],
        description='Ответьте на вопросы и получите оценку вашей ситуации.', is_active=activate,
        workflow={**package, 'import_digest': digest})
    nodes = {key: Question.objects.create(questionnaire=questionnaire, order=i, text=node['text'])
             for i, (key, node) in enumerate(sorted(package['nodes'].items(), key=lambda pair: pair[0] != package['start']), 1)}
    results = {key: Conclusion.objects.create(questionnaire=questionnaire, order=i, title=result['title'],
                short_text=result['short_text'], full_text=result['full_text'])
               for i, (key, result) in enumerate(package['conclusions'].items(), 1)}
    for key, node in package['nodes'].items():
        for i, entry in enumerate(node['answers'], 1):
            target = entry['target']
            answer = Answer.objects.create(question=nodes[key], text=entry['text'], order=i,
                intermediate_text=entry.get('intermediate_text', ''), next_question=nodes.get(target),
                is_final=target.startswith('result:'))
            if answer.is_final:
                AnswerConclusion.objects.create(answer=answer, conclusion=results[target[7:]])
    return questionnaire, True
