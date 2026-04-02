import requests
import time
from dotenv import load_dotenv
import os

load_dotenv('keys.env')

PRACTICUM_TOKEN = os.getenv('PRTOKEN')
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

def test_api():
    print("=" * 50)
    print("Проверка API Яндекс.Практикума")
    print("=" * 50)
    
    # Проверяем наличие токена
    if not PRACTICUM_TOKEN:
        print("❌ Ошибка: PRACTICUM_TOKEN не найден в .env файле")
        return
    
    print(f"✅ Токен найден: {PRACTICUM_TOKEN[:10]}...")
    
    # Параметры запроса
    timestamp = int(time.time())
    params = {'from_date': timestamp - 86400}  # За последние 24 часа
    
    print(f"\n📡 Отправка запроса к API...")
    print(f"URL: {ENDPOINT}")
    print(f"Timestamp: {timestamp}")
    print(f"From date: {params['from_date']}")
    
    try:
        # Делаем запрос
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
            timeout=30
        )
        
        print(f"\n📊 Результат запроса:")
        print(f"Статус код: {response.status_code}")
        print(f"Заголовки: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("\n✅ Успешный ответ!")
            
            try:
                data = response.json()
                print(f"\n📦 Структура ответа:")
                print(f"Ключи: {list(data.keys())}")
                
                if 'homeworks' in data:
                    homeworks = data['homeworks']
                    print(f"Количество домашних работ: {len(homeworks)}")
                    
                    if homeworks:
                        print("\n📝 Первая работа:")
                        first_homework = homeworks[0]
                        for key, value in first_homework.items():
                            print(f"  {key}: {value}")
                
                if 'current_date' in data:
                    print(f"\n🕐 Current date: {data['current_date']}")
                    
            except ValueError as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                print(f"Текст ответа: {response.text[:500]}")
                
        elif response.status_code == 401:
            print("\n❌ Ошибка авторизации (401)")
            print("Проверьте правильность PRACTICUM_TOKEN")
            try:
                error_data = response.json()
                print(f"Сообщение: {error_data}")
            except:
                print(f"Ответ: {response.text}")
                
        elif response.status_code == 400:
            print("\n❌ Ошибка в параметрах запроса (400)")
            try:
                error_data = response.json()
                print(f"Сообщение: {error_data}")
            except:
                print(f"Ответ: {response.text}")
                
        else:
            print(f"\n❌ Неожиданный статус код: {response.status_code}")
            print(f"Ответ: {response.text[:500]}")
            
    except requests.exceptions.Timeout:
        print("\n❌ Таймаут при запросе к API")
        print("Сервер не отвечает в течение 30 секунд")
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Ошибка подключения к API: {e}")
        print("Проверьте интернет-соединение")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Ошибка при запросе: {e}")
        
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
    
    print("\n" + "=" * 50)

if __name__ == '__main__':
    test_api()