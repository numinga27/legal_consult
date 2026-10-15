"""Validate a visual draft before replacing its graph, in one transaction."""
from decimal import Decimal, InvalidOperation
from django.db import transaction
from .models import Question, Answer, Conclusion, AnswerConclusion, Questionnaire, Payment, ConclusionDocument
from .questionnaire_import import FORMAT, ImportProblem, validate_package


@transaction.atomic
def save_visual_draft(questionnaire_id, workflow):
    item = Questionnaire.objects.select_for_update().get(pk=questionnaire_id)
    if item.is_active or item.is_archived or item.helporder_set.exists() or item.consultation_set.exists() or item.usersession_set.exists() or item.runs.exists() or Payment.objects.filter(conclusion__questionnaire=item).exists() or ConclusionDocument.objects.filter(conclusion__questionnaire=item).exists():
        raise ImportProblem('Для опросника с публикацией, историей или документами используйте редактор вопросов и выводов. Пересборка схемы доступна только для нового черновика.')
    if not isinstance(workflow, dict) or not isinstance(workflow.get('nodes'), list) or not isinstance(workflow.get('connections'), list):
        raise ImportProblem('Некорректный формат схемы.')
    if workflow.get('format') == FORMAT:
        raise ImportProblem('Для формата импорта используйте загрузку из документов.')
    if not 1 <= len(workflow['nodes']) <= 1000 or len(workflow['connections']) > 3000:
        raise ImportProblem('Схема пуста или превышает допустимый размер.')
    nodes = {}
    for node in workflow['nodes']:
        if not isinstance(node, dict) or not isinstance(node.get('id'), str) or not node['id'] or node['id'] in nodes or node.get('type') not in {'start', 'question', 'answer', 'conclusion'}:
            raise ImportProblem('В схеме есть неизвестные или повторяющиеся блоки.')
        if not isinstance(node.get('title'), str) or not node['title'].strip() or not isinstance(node.get('text', ''), str):
            raise ImportProblem('Заполните название каждого блока.')
        if node['type'] in {'answer', 'conclusion'} and len(node['title']) > 200:
            raise ImportProblem('Текст ответа или заголовок вывода длиннее 200 символов.')
        nodes[node['id']] = node
    edges = []
    for edge in workflow['connections']:
        if not isinstance(edge, dict) or not isinstance(edge.get('source'), str) or not isinstance(edge.get('target'), str):
            raise ImportProblem('Некорректная связь между блоками.')
        source, target = edge['source'], edge['target']
        if source not in nodes or target not in nodes:
            raise ImportProblem('Связь ведёт к отсутствующему блоку.')
        if (nodes[source]['type'], nodes[target]['type']) not in {('start', 'question'), ('question', 'answer'), ('answer', 'question'), ('answer', 'conclusion')} or (source, target) in edges:
            raise ImportProblem('Неверная или повторяющаяся связь между блоками.')
        edges.append((source, target))
    package = {'format': FORMAT, 'name': item.name, 'nodes': {}, 'conclusions': {}}
    for key, node in nodes.items():
        if node['type'] == 'question':
            package['nodes'][key] = {'text': node['title'], 'answers': []}
        elif node['type'] == 'conclusion':
            package['conclusions'][key] = {'title': node['title'], 'short_text': node.get('text', ''), 'full_text': node.get('text', '')}
            try:
                price = Decimal(str(node.get('price', 0)))
                rate = int(node.get('success_rate', 50))
                if not price.is_finite() or not 0 <= price <= Decimal('99999999.99') or price.as_tuple().exponent < -2 or not 0 <= rate <= 100:
                    raise ValueError
            except (ValueError, TypeError, InvalidOperation):
                raise ImportProblem('Укажите корректную цену и вероятность от 0 до 100%.')
    referenced_questions = set()
    for key, node in nodes.items():
        if node['type'] != 'answer':
            continue
        parents = [source for source, target in edges if target == key]
        targets = [target for source, target in edges if source == key]
        if len(parents) != 1 or len(targets) != 1:
            raise ImportProblem('У каждого ответа должен быть один вопрос и один следующий шаг.')
        target = targets[0]
        if nodes[target]['type'] == 'question':
            referenced_questions.add(target)
        package['nodes'][parents[0]]['answers'].append({'text': node['title'], 'intermediate_text': node.get('text', ''), 'target': 'result:' + target if nodes[target]['type'] == 'conclusion' else target})
    starts = set(package['nodes']) - referenced_questions
    start_nodes = [key for key, node in nodes.items() if node['type'] == 'start']
    if len(start_nodes) > 1:
        raise ImportProblem('Оставьте один блок начала схемы.')
    if start_nodes:
        targets = [target for source, target in edges if source == start_nodes[0]]
        if len(targets) != 1:
            raise ImportProblem('Соедините начало схемы с одним первым вопросом.')
        package['start'] = targets[0]
    else:
        package['start'] = next(iter(starts)) if len(starts) == 1 else ''
    errors = validate_package(package)
    if errors:
        raise ImportProblem(' '.join(errors[:4]))
    # No records are touched until the complete graph is validated. References
    # with history/files are rejected above, so their IDs can never be reassigned.
    item.questions.all().delete()
    item.conclusions.all().delete()
    ordered = sorted(package['nodes'], key=lambda key: key != package['start'])
    questions = {key: Question.objects.create(questionnaire=item, order=i, text=nodes[key]['title'], help_text=nodes[key].get('text', '')) for i, key in enumerate(ordered, 1)}
    results = {key: Conclusion.objects.create(questionnaire=item, order=i, title=nodes[key]['title'], short_text=nodes[key].get('text', ''), full_text=nodes[key].get('text', ''), price=nodes[key].get('price', 0), success_rate=nodes[key].get('success_rate', 50)) for i, key in enumerate(package['conclusions'], 1)}
    for key, node in package['nodes'].items():
        for i, entry in enumerate(node['answers'], 1):
            final = entry['target'].startswith('result:')
            answer = Answer.objects.create(question=questions[key], text=entry['text'], order=i, intermediate_text=entry['intermediate_text'], is_final=final, next_question=questions.get(entry['target']))
            if final:
                AnswerConclusion.objects.create(answer=answer, conclusion=results[entry['target'][7:]])
    item.workflow = workflow
    item.save(update_fields=['workflow', 'updated_at'])
    return item
