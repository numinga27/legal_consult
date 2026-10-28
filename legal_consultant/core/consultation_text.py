"""Build paid text only from the validated path; never send it in free results."""


def consultation_text(package, history, current):
    from .guided_views import position
    if position(package, history) != current or not current.startswith('result:'):
        raise ValueError('Консультация доступна только для завершённого маршрута.')
    result = package['conclusions'][current[7:]]
    if package.get('consultation_mode') != 'answers':
        return result.get('full_text', '')
    parts = []
    for entry in history:
        node = package['nodes'][entry['node']]
        answer = node['answers'][entry['answer']]
        text = answer.get('intermediate_text', '').strip()
        if text and text not in ('-', '—', '–'):
            parts.append(f'{node["text"]}\nОтвет: {answer["text"]}\n\n{text}')
    if result.get('full_text', '').strip():
        parts.append(result['full_text'])
    return '\n\n'.join(parts)
