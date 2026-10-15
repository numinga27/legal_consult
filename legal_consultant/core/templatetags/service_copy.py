from django import template

register = template.Library()


@register.filter
def independent_services(value):
    """Apply the client's marketing correction without rewriting source legal text."""
    return str(value).replace(
        'Получите доступ к одному из пакетных решений для вас ниже.',
        'Выберите одну или несколько нужных вам услуг ниже.',
    )
