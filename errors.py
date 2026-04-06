class BotError(Exception):
    """Базовое исключение для бота."""
    pass

class SendMessageError(BotError):
    """Ошибка при отправке сообщения в Telegram."""
    pass

class APIRequestError(BotError):
    """Ошибка при запросе к внешнему API."""
    pass

class APIResponseError(BotError):
    """Ошибка в структуре ответа API."""
    pass