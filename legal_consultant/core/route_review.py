"""Bounded route review for the owner, including private text previews."""
from .consultation_text import consultation_text
from .questionnaire_import import validate_package


def route_review(package, limit=1000):
    if validate_package(package):
        return {'results': [], 'count': 0, 'truncated': False}
    groups = {key: {'code': key, 'title': value['title'], 'routes': []}
              for key, value in package['conclusions'].items()}
    stack = [(package['start'], [], [])]
    count = 0
    text_size = 0
    while stack and count < limit and text_size < 2000000:
        current, history, labels = stack.pop()
        if current.startswith('result:'):
            text = consultation_text(package, history, current)
            text_size += len(text)
            groups[current[7:]]['routes'].append({'path': ' → '.join(labels), 'consultation': text})
            count += 1
            continue
        node = package['nodes'][current]
        for i in reversed(range(len(node['answers']))):
            answer = node['answers'][i]
            stack.append((answer['target'], history + [{'node': current, 'answer': i}],
                          labels + [f'В{node.get("code", current)}: {answer["text"]}']))
    return {'results': list(groups.values()), 'count': count, 'truncated': bool(stack)}
