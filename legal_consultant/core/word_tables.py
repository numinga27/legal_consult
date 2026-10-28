"""Read explicitly labelled DOCX columns without flattening their semantics."""
import re


def read_labelled_tables(root, ns):
    from .questionnaire_import import Q_RE, C_RE, ImportProblem
    tables = []
    for table in root.findall('.//w:tbl', ns):
        tables.append([['\n\n'.join(
            ''.join(t.text or '' for t in p.findall('.//w:t', ns)).strip()
            for p in cell.findall('w:p', ns)).strip()
            for cell in row.findall('w:tc', ns)] for row in table.findall('w:tr', ns)])
    def normal(text):
        return ' '.join(text.casefold().split())
    result_tables = []
    for rows in tables:
        if not rows:
            continue
        headers = [normal(c) for c in rows[0]]
        free = [i for i, h in enumerate(headers) if h.startswith(('бесплатный результат', 'бесплатная часть'))]
        plan = [i for i, h in enumerate(headers) if h.startswith('пошаговый план')]
        title = [i for i, h in enumerate(headers) if h == 'заголовок']
        if free and plan and title:
            if any(len(x) != 1 for x in (free, plan, title)):
                raise ImportProblem('Повторные заголовки столбцов результатов Word.')
            result_tables.append((rows, title[0], free[0], plan[0]))
    if not result_tables:
        return None  # Preserve the legacy paragraph/price format.
    questions, conclusions = {}, {}
    for rows, ti, fi, pi in result_tables:
        for row in rows[1:]:
            if not any(row):
                continue
            if len(row) <= max(ti, fi, pi) or not (match := C_RE.match(row[ti])):
                raise ImportProblem('В строке таблицы результатов нужен заголовок «Вывод 1: …» и отдельные столбцы текста и плана.')
            code = match[1]
            if code in conclusions:
                raise ImportProblem(f'Повторный Вывод {code} в Word.')
            conclusions[code] = {'title': ' '.join(match[2].split()), 'short_text': row[fi],
                                 'plan_text': row[pi], 'full_text': '', 'source_prices': []}
    for rows in tables:
        if not any(len(row) >= 3 and Q_RE.match(row[0]) for row in rows):
            continue
        current = None
        for row in rows:
            if len(row) < 3:
                raise ImportProblem('В таблице вопросов нужны три столбца: вопрос, ответ, консультация.')
            match = Q_RE.match(row[0])
            if match:
                code = match[1]
                if code in questions:
                    raise ImportProblem(f'Повторный заголовок В{code} в Word.')
                current = questions[code] = {'text': row[0][match.end():].strip(), 'answers': {},
                                             'consultation_from_answers': True}
            if current is None:
                continue
            label = re.sub(r'^[АБВГA-D]\)\s*', '', row[1]).strip()
            if not label or label in current['answers']:
                raise ImportProblem(f'Пустой или повторный ответ в строке Word: {row[1]}.')
            current['answers'][label] = '' if row[2].strip() in ('-', '—', '–') else row[2]
    if not questions or not conclusions:
        raise ImportProblem('Нужны таблица вопросов и таблица результатов.')
    return questions, conclusions
