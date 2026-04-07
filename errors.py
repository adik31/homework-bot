class BotError(Exception):
    """Базовое исключение для бота."""

class SendMessageError(BotError):
    """Ошибка при отправке сообщения в Telegram."""

class APIRequestError(BotError):
    """Ошибка при запросе к внешнему API."""

class APIResponseError(BotError):
    """Ошибка в структуре ответа API."""