"""The three separately ordered services; prices are configured per questionnaire."""
SERVICES = (
    (
        'Письменная консультация',
        'Узнайте больше о вашей проблеме с точки зрения закона.',
        'consultation',
    ),
    (
        'Пошаговый план действий',
        'Узнайте, что и как сделать в вашей ситуации для решения проблемы.',
        'plan',
    ),
    (
        'Документы',
        'Получите готовые документы для решения вашей проблемы '
        '(от вас потребуется заполнить только поля с идентифицирующими данными)',
        'documents',
    ),
)


def help_offers(package):
    prices = package.get('offer_prices', ['', '', ''])
    if not isinstance(prices, list) or len(prices) != 3:
        prices = ['', '', '']
    return [dict(title=title, description=description, services=(title,), icon=icon, code=icon, price=price)
            for (title, description, icon), price in zip(SERVICES, prices)]
