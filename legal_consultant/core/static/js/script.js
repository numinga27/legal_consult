// Основной JavaScript для сайта

$(document).ready(function() {
    // Автоматическое скрытие сообщений через 5 секунд
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);

    // Обработка кликов по кнопкам ответов в опроснике
    $('.answer-btn').on('click', function() {
        $(this).addClass('selected').siblings().removeClass('selected');
    });

    // Подтверждение удаления
    $('.delete-confirm').on('click', function(e) {
        if (!confirm('Вы уверены, что хотите удалить этот элемент?')) {
            e.preventDefault();
        }
    });
});

// Функция для обновления прогресс-бара
function updateProgress(current, total) {
    const percent = (current / total) * 100;
    $('.progress-fill').css('width', percent + '%');
    $('.progress-text').text(Math.round(percent) + '%');
}

// Функция для плавной прокрутки к элементу
function scrollToElement(selector) {
    $('html, body').animate({
        scrollTop: $(selector).offset().top - 100
    }, 500);
}