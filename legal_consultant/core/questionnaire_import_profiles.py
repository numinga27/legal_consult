"""Reviewed repairs for one exact source pair, never applied to unrelated files."""
import re


def refine_court_order(package, cells, paragraphs):
    if package['sources'] != {
        'graph_sha256': '98a49c92b134ebd74069c692093cdc6c8279cfcdff1822eab6088aebfa9ea0b9',
        'word_sha256': '9af4dfd3fd125c89a35257dd2d284927159e841b559e9eebce11d1a09c236dbe',
    }:
        return
    nodes = package['nodes']
    repairs = [
        ('HgjSNt0WqrnvkYVKWa35-64', 'Нет', 'result:5'),
        ('HgjSNt0WqrnvkYVKWa35-70', 'Нет', 'result:2.3'),
        ('HgjSNt0WqrnvkYVKWa35-72', 'Нет', 'result:2.2'),
        ('HgjSNt0WqrnvkYVKWa35-74', 'Нет', 'result:2.1'),
        ('VjxwNj25DGgLvjahsPyy-1', 'Нет', 'Nr9201bLw6oBRVnrILMu-13'),
        ('VjxwNj25DGgLvjahsPyy-17', 'Нет', 'result:12'),
        ('Nr9201bLw6oBRVnrILMu-13', 'Нет', 'Nr9201bLw6oBRVnrILMu-16'),
    ]
    for key, label, target in repairs:
        next(a for a in nodes[key]['answers'] if a['text'] == label)['target'] = target
    # Word groups four prices/full consultations after the short text of 2.3.
    lines = [p for p in paragraphs if p]
    start = next(i for i, p in enumerate(lines) if p.startswith('Вывод 2:'))
    end = next(i for i, p in enumerate(lines) if p.startswith('Вывод 3:'))
    group = lines[start:end]
    for i, code in enumerate(['2', '2.1', '2.2', '2.3'], 1):
        result = package['conclusions'][code]
        short_start = next(n for n, p in enumerate(group) if p.startswith('Вывод ' + code + ':')) + 1
        short_end = next((n for n in range(short_start, len(group))
                          if group[n].startswith('Вывод ') or re.match(r'^1\.\s+\d+$', group[n])), len(group))
        result['short_text'] = '\n\n'.join(p for p in group[short_start:short_end] if p != 'с')
        price_start = next(n for n, p in enumerate(group) if re.match(rf'^{i}\.\s+\d+$', p))
        result['source_prices'] = [group[price_start].split()[-1], *group[price_start + 1:price_start + 3]]
        body_start = next(n for n, p in enumerate(group) if re.match(rf'^{i}\s*[–—-]', p))
        body_end = next((n for n in range(body_start + 1, len(group)) if re.match(r'^\d\s*[–—-]', group[n])), len(group))
        result['full_text'] = '\n\n'.join(group[body_start:body_end])
    package['start'] = 'HgjSNt0WqrnvkYVKWa35-45'
    # Owner requested the live reference's bundle prices (2026-09-13), not Word's older numbers.
    package['offer_prices'] = ['298', '498', '697']
    package['notes'] = [
        'Применён проверенный разбор именно этой пары файлов (сверены SHA-256).',
        'По поручению владельца три пакета помощи скопированы с эталона 13.09.2026: 298 / 498 / 697 ₽. Исходные числа Word сохранены отдельно и не используются как цены пакетов.',
        'Подробное дерево используется отдельно от поясняющего эскиза. Зелёные стрелки — Да, красные — Нет.',
        'Восстановлены 5 непривязанных стрелок подробного дерева по их конечным координатам и содержанию блоков; ветка В8 Нет уточнена по Word.',
        'Добавлен отсутствующий переход В7.3 Нет → Вывод 2.3 из Word. В8 Нет → 2.2, В8.1 Нет → 2.1, В8.1 Да → 2.',
        'Тексты Вывода 2 и вариантов 2.1–2.3 сопоставлены с четырьмя отдельными консультациями Word. Удалён одиночный символ «с» после 2.1.',
        'В схеме у Вывода 8 ошибочно написано «есть задолженность», хотя ветка проходит через В6 Нет. Использован согласующийся с веткой текст Word «отсутствует задолженность».',
        'В файлах нет отдельных шаблонов документов и выделенных текстов пошаговых планов: сохранены бесплатные выводы, консультации и подсказки.',
    ]
