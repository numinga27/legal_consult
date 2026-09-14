"""Read existing catalogue links without changing or inventing questionnaire content."""
from .models import AnswerConclusion
from .questionnaire_import import FORMAT


def runtime_package(questionnaire):
    if questionnaire.workflow.get('format') == FORMAT:
        return questionnaire.workflow
    questions = list(questionnaire.questions.order_by('order', 'id').prefetch_related('answers'))
    results = {str(c.id): {'title': c.title, 'short_text': c.short_text,
                          'full_text': c.full_text, 'source_prices': []}
               for c in questionnaire.conclusions.all()}
    links = dict(AnswerConclusion.objects.filter(answer__question__questionnaire=questionnaire)
                 .values_list('answer_id', 'conclusion_id'))
    ids = {q.id for q in questions}
    nodes = {}
    for question in questions:
        answers = []
        for answer in sorted(question.answers.all(), key=lambda a: (a.order, a.id)):
            result_id = str(links.get(answer.id, ''))
            # Conflicting/foreign/missing links require content review, never a default result.
            if answer.next_question_id in ids and not result_id:
                target = str(answer.next_question_id)
            elif not answer.next_question_id and result_id in results and results[result_id]['short_text'].strip():
                target = 'result:' + result_id
            else:
                target = 'unavailable'
            answers.append({'text': answer.text, 'target': target, 'intermediate_text': ''})
        nodes[str(question.id)] = {'text': question.text, 'code': str(question.order), 'answers': answers}
    return {'start': str(questions[0].id) if questions else 'unavailable',
            'nodes': nodes, 'conclusions': results, 'legacy': True}
