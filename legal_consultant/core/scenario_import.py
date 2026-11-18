"""Verify explicit scenarios against the graph; never guess conflicting routes."""
import io
import re
from zipfile import ZipFile, BadZipFile

def read_scenarios(data):
    from .questionnaire_import import MAX_BYTES, ImportProblem, xml_root
    if len(data) > MAX_BYTES:
        raise ImportProblem('Файл сценариев больше 5 МБ.')
    try:
        with ZipFile(io.BytesIO(data)) as z:
            item = z.getinfo('word/document.xml')
            if item.file_size > MAX_BYTES:
                raise ImportProblem('Текст сценариев больше 5 МБ.')
            root = xml_root(z.read(item))
    except (BadZipFile, KeyError, RuntimeError) as exc:
        raise ImportProblem('Сценарии нужно загрузить в DOCX.') from exc
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    lines = [''.join(t.text or '' for t in p.findall('.//w:t', ns)).strip()
             for p in root.findall('.//w:p', ns)]
    checks, current, result = [], None, None
    for line in lines:
        if not line:
            continue
        heading = re.match(r'^Вывод\s+(\d+(?:\.\d+)*)\s*:', line, re.I)
        if heading:
            result = heading[1]
            current = None
            continue
        scenario = re.match(r'^Сценарий\s+(\d+)\s*:', line, re.I)
        if scenario and result:
            current = {'result': result, 'number': scenario[1], 'steps': []}
            checks.append(current)
            line = line[scenario.end():]
        if current is not None:
            current['steps'] += [[m[0], m[1].casefold()] for m in
                                re.findall(r'В\s*(\d+(?:\.\d+)*)\s*[-–—]\s*(да|нет)\b', line, re.I)]
    if not checks:
        raise ImportProblem('Не найдены сценарии: нужны «Вывод 1:», «Сценарий 1:», «В1-да; В2-нет».')
    return checks

def validate_scenarios(package):
    checks = package.get('scenario_checks', [])
    if not isinstance(checks, list) or len(checks) > 1000:
        return ['Некорректный список сценариев (не больше 1000).']
    errors, seen = [], {}
    for check in checks:
        try:
            result, number, steps = check['result'], check['number'], check['steps']
            label = f'Вывод {result}, сценарий {number}'
            if not steps:
                errors.append(label + ': путь пустой.')
                continue
            signature = tuple((str(q), str(a).casefold()) for q, a in steps)
            if signature in seen and seen[signature] != result:
                errors.append(label + ': такой же путь указан для вывода ' + seen[signature] + '.')
            seen[signature] = result
            current = package['start']
            for code, answer in signature:
                node = package['nodes'].get(current)
                if node is None or str(node.get('code')) != code:
                    raise ValueError
                matches = [a for a in node['answers'] if a['text'].strip().casefold() == answer]
                if len(matches) != 1:
                    raise ValueError
                current = matches[0]['target']
            if current != 'result:' + result:
                errors.append(label + ': схема ведёт к ' + current + ', проверьте переходы.')
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append('Сценарий не соответствует последовательности вопросов и ответов схемы.')
    return errors
