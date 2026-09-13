"""The three reference bundles; configured prices are separate from Word numbers."""
BUNDLES = (
    ('Правовая оценка ситуации', ('Консультация', 'Пошаговый план действий'), 'consultation'),
    ('Документальное сопровождение', ('Пошаговый план действий', 'Подготовка документов'), 'plan'),
    ('Максимальная помощь', ('Консультация', 'Пошаговый план действий', 'Подготовка документов'), 'documents'),
)


def help_offers(package):
    prices = package.get('offer_prices', ['', '', ''])
    if not isinstance(prices, list) or len(prices) != 3:
        prices = ['', '', '']
    return [dict(title=title, services=services, icon=icon, price=price)
            for (title, services, icon), price in zip(BUNDLES, prices)]
