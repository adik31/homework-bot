import requests
import time
import logging
from dotenv import load_dotenv
import os
import telebot
from telebot import apihelper


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

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
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

last_error_message = None


def check_tokens():
    """Проверяет наличие всех необходимых токенов."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing = [name for name, value in tokens.items() if not value]
    if missing:
        logger.critical(
            'Отсутствуют необходимые переменные окружения: %s',
            ', '.join(missing)
        )
        return False
    logger.info('Все переменные окружения доступны')
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    if not message:
        logger.warning('Попытка отправить пустое сообщение')
        return
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Бот отправил сообщение')
    except Exception as e:
        logger.error('Ошибка при отправке сообщения: %s', e)
        raise


def get_api_answer(timestamp):
    """Отправляет запрос к API практикума."""
    payload = {'from_date': timestamp}
    logger.debug('Отправка запроса к API. timestamp: %s', timestamp)

    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload,
            timeout=60
        )
    except requests.exceptions.RequestException as e:
        logger.error('Ошибка при запросе к API: %s', e)
        raise Exception(f'Ошибка при запросе к API: {e}') from e

    if response.status_code != 200:
        error_msg = f'Эндпоинт {ENDPOINT} недоступен. ' \
                    f'Код ответа API: {response.status_code}'
        logger.error(error_msg)
        raise Exception(error_msg)

    try:
        return response.json()
    except ValueError as e:
        raise ValueError(f'Ошибка при преобразовании JSON ответа: {e}')


def check_response(response):
    """Проверяет структуру ответа от API."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API должен быть словарем. '
            f'Получен тип: {type(response)}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')
    if 'current_date' not in response:
        raise KeyError('В ответе API отсутствует ключ "current_date"')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Значение "homeworks" должно быть списком. '
            f'Получен тип: {type(homeworks)}'
        )

    for homework in homeworks:
        if not isinstance(homework, dict):
            raise TypeError('Элемент списка homeworks должен быть словарем')
        if 'homework_name' not in homework or 'status' not in homework:
            raise KeyError(
                'В домашней работе нет ключей "homework_name" или "status"'
            )
        if homework.get('status') not in HOMEWORK_VERDICTS:
            raise ValueError(
                f'Неизвестный статус домашней работы: {homework.get("status")}'
            )

    if not isinstance(response.get('current_date'), (int, float)):
        raise TypeError('Значение "current_date" должно быть числом')

    logger.debug('Ответ проверен. Получено домашних работ: %d', len(homeworks))
    return True


def parse_status(homework):
    """Формирует сообщение о статусе домашней работы."""
    homework_name = homework.get('homework_name')
    status = homework.get('status')

    if not homework_name or not status:
        raise KeyError(
            'Отсутствуют обязательные поля homework_name или status'
        )

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: "{status}"')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная функция бота."""
    global last_error_message

    if not check_tokens():
        logger.critical('Программа принудительно остановлена.')
        return

    if PROXY_HOST and PROXY_PORT:
        proxy_url = f'{PROXY_TYPE}://'
        if PROXY_USERNAME and PROXY_PASSWORD:
            proxy_url += f'{PROXY_USERNAME}:{PROXY_PASSWORD}@'
        proxy_url += f'{PROXY_HOST}:{PROXY_PORT}'

        logger.info('Настроен прокси: %s', proxy_url)
        apihelper.proxy = {'http': proxy_url, 'https': proxy_url}
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        logger.info('Бот создан с использованием прокси')
    else:
        logger.info('Прокси не настроен, используется прямое подключение')
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        logger.info('Бот создан без прокси')

    try:
        bot.get_me()
        logger.info('Подключение к Telegram успешно')
    except Exception as e:
        logger.error('Ошибка подключения к Telegram: %s', e)

    timestamp = int(time.time())
    sent_homeworks = set()

    try:
        send_message(
            bot,
            'Бот запущен и начал отслеживание статусов домашних работ'
        )
    except Exception as e:
        logger.error('Не удалось отправить приветственное сообщение: %s', e)

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)

            timestamp = response.get('current_date', int(time.time()))
            homeworks = response.get('homeworks', [])

            if not homeworks:
                logger.debug('Нет новых статусов домашних работ')
            else:
                for homework in homeworks:
                    homework_id = homework.get('id')
                    if homework_id and homework_id not in sent_homeworks:
                        try:
                            message = parse_status(homework)
                            send_message(bot, message)
                            sent_homeworks.add(homework_id)
                        except Exception as e:
                            logger.error(
                                'Ошибка при обработке работы ID %s: %s',
                                homework_id,
                                e
                            )

            last_error_message = None

        except (KeyError, TypeError, ValueError) as e:
            error_message = f'Ошибка в ответе API: {e}'
            logger.error(error_message)
            if last_error_message != error_message:
                try:
                    send_message(bot, error_message)
                    last_error_message = error_message
                except Exception:
                    pass

        except Exception as e:
            error_message = f'Сбой в работе программы: {e}'
            logger.error(error_message)
            if last_error_message != error_message:
                try:
                    send_message(bot, error_message)
                    last_error_message = error_message
                except Exception:
                    pass

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
