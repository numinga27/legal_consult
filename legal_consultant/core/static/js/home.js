(() => {
    'use strict';
    const form = document.getElementById('topic-search');
    const input = document.getElementById('searchProblem');
    const cards = Array.from(document.querySelectorAll('[data-topic]'));
    const status = document.getElementById('search-status');
    const empty = document.getElementById('no-results');
    const normalize = value => value.normalize('NFKC').toLocaleLowerCase('ru').replace(/ё/g, 'е').trim();
    const tokenize = value => normalize(value).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const stopWords = new Set(['я', 'меня', 'мне', 'у', 'с', 'со', 'по', 'на', 'в', 'во', 'и', 'как', 'что', 'это', 'мой', 'моя', 'мои']);
    const synonyms = [
        ['авто', 'дтп', 'осаго', 'машин', 'автомобил'],
        ['работ', 'труд', 'увол', 'уволь', 'зарплат'],
        ['семь', 'семейн', 'развод', 'брак', 'алимент'],
        ['покуп', 'товар', 'потребител', 'магазин'],
        ['долг', 'кредит', 'задолжен', 'приказ'],
        ['судебн', 'судприказ'],
        ['жиль', 'квартир', 'недвижим', 'жилищ'],
    ];
    const matchesRoot = (word, root) => word === root || (root !== 'авто' && word.startsWith(root));
    const searchable = cards.map(card => {
        const words = tokenize(card.dataset.search);
        // Match word beginnings: e.g. 'авто' must not match 'авторское'.
        const groups = synonyms.filter(group => group.some(root => words.some(word => matchesRoot(word, root))));
        return {card, words, groups};
    });
    function search() {
        const query = normalize(input.value);
        const words = tokenize(query).filter(word => !stopWords.has(word));
        let count = 0;
        searchable.forEach(({card, words: contentWords, groups}) => {
            const match = words.every(word => contentWords.some(candidate => candidate.startsWith(word)) ||
                groups.some(group => group.some(root => matchesRoot(word, root))));
            card.hidden = !match;
            if (match) count += 1;
        });
        empty.hidden = !query || count > 0 || cards.length === 0;
        status.textContent = query ? (count ? `Найдено направлений: ${count}` : 'По вашему запросу ничего не найдено.') : '';
    }
    form.addEventListener('submit', event => {event.preventDefault(); search();});
    input.addEventListener('input', search);
    document.getElementById('clear-search').addEventListener('click', () => {
        input.value = ''; search(); input.focus();
    });
    form.hidden = false;
    search();
})();
