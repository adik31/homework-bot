import logging
import os
import time

import requests
import telebot

from dotenv import load_dotenv
from telebot import apihelper
from Erorrs import (
    BotError,
    SendMessageError,
    APIRequestError,
    APIResponseError
)
from http import HTTPStatus

load_dotenv('keys.env')

PRACTICUM_TOKEN = os.getenv('PRTOKEN')
TELEGRAM_TOKEN = os.getenv('TGTOKEN')
TELEGRAM_CHAT_ID = os.getenv('USRTOKEN')

PROXY_TYPE = os.getenv('PROXY_TYPE', 'socks5')
PROXY_HOST = os.getenv('PROXY_HOST')
PROXY_PORT = os.getenv('PROXY_PORT')
PROXY_USERNAME = os.getenv('PROXY_USERNAME')
PROXY_PASSWORD = os.getenv('PROXY_PASSWORD')

RETRY_PERIOD = 600
RETRY_IP_PERIOD = 60
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет наличие всех необходимых токенов."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing = [name for name, value in tokens.items() if not value]
    if missing:
        raise BotError(
            f'Отсутствуют переменные окружения: {", ".join(missing)}'
        )
    logger.info('Все переменные окружения доступны')
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    if not message:
        return
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Бот отправил сообщение')
    except Exception as e:
        raise SendMessageError(
            f'Не удалось отправить сообщение: {message[:50]}...'
        ) from e


def get_api_answer(timestamp):
    """Отправляет запрос к API практикума."""
    request_kwargs = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
        'timeout': RETRY_IP_PERIOD
    }

    try:
        response = requests.get(**request_kwargs)
    except requests.exceptions.RequestException as e:
        raise APIRequestError(f'Ошибка при запросе к API: {e}') from e

    if response.status_code != HTTPStatus.OK:
        raise APIResponseError(
            f'{ENDPOINT} недоступен. Код ответа: {response.status_code}'
        )

    try:
        return response.json()
    except ValueError as e:
        raise APIResponseError(
            f'Ошибка при преобразовании JSON ответа: {e}'
        ) from e


def check_response(response):
    """Проверяет структуру ответа от API."""
    if not isinstance(response, dict):
        raise TypeError(
            'Ответ API должен быть словарем. '
            f'Получен тип: {type(response)}'
        )

    if 'homeworks' not in response:
        raise APIResponseError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Значение "homeworks" должно быть списком. '
            f'Получен тип: {type(homeworks)}'
        )

    if not isinstance(response.get('current_date'), (int, float)):
        raise TypeError('Значение "current_date" должно быть числом')

    return True


def parse_status(homework):
    """Формирует сообщение о статусе домашней работы."""
    if 'homework_name' not in homework:
        raise APIResponseError(
            'В домашней работе отсутствует ключ "homework_name"'
        )

    if 'status' not in homework:
        raise APIResponseError('В домашней работе отсутствует ключ "status"')

    homework_name = homework['homework_name']
    status = homework['status']

    if not homework_name or not isinstance(homework_name, str):
        raise APIResponseError(
            f'Некорректное значение "homework_name": {homework_name}'
        )

    if status not in HOMEWORK_VERDICTS:
        raise APIResponseError(f'Неизвестный статус: "{status}"')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def _setup_proxy():
    """Настраивает прокси для подключения к Telegram."""
    if not (PROXY_HOST and PROXY_PORT):
        return

    proxy_url = f'{PROXY_TYPE}://'
    if PROXY_USERNAME and PROXY_PASSWORD:
        proxy_url += f'{PROXY_USERNAME}:{PROXY_PASSWORD}@'
    proxy_url += f'{PROXY_HOST}:{PROXY_PORT}'

    apihelper.proxy = {'http': proxy_url, 'https': proxy_url}


def _process_homework_cycle(bot, timestamp, last_message_id):
    """Обрабатывает один цикл проверки статусов домашних работ."""
    response = get_api_answer(timestamp)
    check_response(response)

    homeworks = response['homeworks']

    if not homeworks:
        return timestamp, last_message_id

    for homework in homeworks:
        homework_id = homework.get('id')
        if not homework_id:
            continue

        if homework_id == last_message_id:
            break

        message = parse_status(homework)
        send_message(bot, message)
        last_message_id = homework_id

    timestamp = response['current_date']

    return timestamp, last_message_id


def _send_error(bot, error_message, last_error_message):
    """Отправляет сообщение об ошибке, если оно новое."""
    if last_error_message != error_message:
        try:
            send_message(bot, error_message)
            return error_message
        except SendMessageError:
            return last_error_message
    return last_error_message


def handle_cycle_error(e, bot, last_error_message, error_type='api'):
    """Обрабатывает ошибки в цикле бота."""
    if error_type == 'send':
        logger.error('Ошибка при отправке сообщения: %s', e)
        return last_error_message

    if error_type == 'api':
        logger.error('Ошибка при работе с API: %s', e)
        user_message = f'Ошибка при проверке статуса: {e}'
    else:
        logger.exception('Непредвиденная ошибка: %s', e)
        user_message = 'Ошибка в работе бота.'

    return _send_error(bot, user_message, last_error_message)


def run_bot_iteration(bot, timestamp, last_message_id, last_error_message):
    """Выполняет одну итерацию бота с обработкой ошибок."""
    try:
        new_timestamp, new_last_id = _process_homework_cycle(
            bot, timestamp, last_message_id,
        )
        return new_timestamp, new_last_id, None
    except SendMessageError as e:
        return timestamp, last_message_id, handle_cycle_error(
            e, bot, last_error_message, 'send'
        )
    except (APIRequestError, APIResponseError) as e:
        return timestamp, last_message_id, handle_cycle_error(
            e, bot, last_error_message, 'api'
        )
    except Exception as e:
        return timestamp, last_message_id, handle_cycle_error(
            e, bot, last_error_message, 'unknown'
        )


def main():
    """Основная функция бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('bot.log', encoding='utf-8')]
    )

    timestamp = int(time.time())
    last_message_id = None
    last_error_message = None

    try:
        check_tokens()
    except BotError as e:
        logger.critical('Ошибка инициализации: %s', e)
        return

    try:
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        _setup_proxy()
        bot.get_me()
    except Exception as e:
        logger.error('Ошибка при создании/настройке бота: %s', e)
        return

    try:
        send_message(
            bot,
            'Бот запущен и начал отслеживание статусов домашних работ'
        )
    except SendMessageError as e:
        logger.error('Не удалось отправить приветственное сообщение: %s', e)

    while True:
        timestamp, last_message_id, last_error_message = run_bot_iteration(
            bot, timestamp, last_message_id, last_error_message
        )
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
