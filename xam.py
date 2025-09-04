import asyncio
from playwright.async_api import async_playwright
import requests
import os
import json
import time
import gc  # Добавляем для сборки мусора
from datetime import datetime, timedelta
import pytz  # Добавляем библиотеку для работы с часовыми поясами
import hashlib
import signal
import atexit

# --- ДАННЫЕ ---
PHONE = "9944476229"  # твой номер
TG_BOT_TOKEN = "8487304030:AAEemcE1Y9J1plzoOlZuxm8XDF_7WzQZtI4"
TG_CHANNEL = "@max_bridgetotg"

# Настройка часового пояса - Екатеринбург
TIMEZONE = pytz.timezone('Asia/Yekaterinburg')

# Путь для сохранения сессии
SESSION_DIR = "./max_session"
COOKIES_FILE = os.path.join(SESSION_DIR, "cookies.json")
STORAGE_FILE = os.path.join(SESSION_DIR, "storage.json")
MESSAGES_FILE = os.path.join(SESSION_DIR, "last_messages.json")
LAST_CHECK_FILE = os.path.join(SESSION_DIR, "last_check_time.json")
STATUS_MESSAGE_FILE = os.path.join(SESSION_DIR, "status_message.json")

# Глобальная переменная для ID статусного сообщения
status_message_id = None

def get_local_time():
    """Возвращает текущее время в часовом поясе Екатеринбурга"""
    return datetime.now(TIMEZONE)

def format_local_time(dt=None):
    """Форматирует время в екатеринбургском часовом поясе"""
    if dt is None:
        dt = get_local_time()
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def cleanup_memory():
    """Очистка памяти и сборка мусора"""
    try:
        print("🧹 Выполняем очистку памяти...")
        
        # Принудительная сборка мусора
        collected = gc.collect()
        print(f"🗑️ Собрано {collected} объектов мусора")
        
        # Очистка старых файлов изображений (старше 1 часа)
        images_dir = os.path.join(SESSION_DIR, "images")
        if os.path.exists(images_dir):
            current_time = time.time()
            cleaned_files = 0
            
            for filename in os.listdir(images_dir):
                file_path = os.path.join(images_dir, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > 3600:  # 1 час
                        try:
                            os.remove(file_path)
                            cleaned_files += 1
                        except Exception as e:
                            print(f"⚠️ Не удалось удалить {filename}: {e}")
            
            if cleaned_files > 0:
                print(f"🗂️ Удалено {cleaned_files} старых файлов изображений")
        
        # Ограничиваем размер файла сообщений
        if os.path.exists(MESSAGES_FILE):
            try:
                with open(MESSAGES_FILE, 'r') as f:
                    data = json.load(f)
                
                messages = data.get('messages', {})
                if len(messages) > 100:  # Если сообщений больше 100
                    # Оставляем только 50 последних
                    sorted_messages = sorted(
                        messages.items(), 
                        key=lambda x: x[1].get('created_at', 0)
                    )
                    recent_messages = dict(sorted_messages[-50:])
                    
                    data['messages'] = recent_messages
                    with open(MESSAGES_FILE, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    print(f"📝 Очищена база сообщений: оставлено 50 из {len(messages)}")
            except Exception as e:
                print(f"⚠️ Ошибка очистки базы сообщений: {e}")
        
        print("✅ Очистка памяти завершена")
        
    except Exception as e:
        print(f"❌ Ошибка очистки памяти: {e}")

async def save_session(context, page):
    """Сохраняет полную сессию (cookies + localStorage + sessionStorage)"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    
    try:
        # Сохраняем cookies
        cookies = await context.cookies()
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        # Сохраняем localStorage и sessionStorage
        storage_data = await page.evaluate("""
            () => {
                const localStorage_data = {};
                const sessionStorage_data = {};
                
                // Получаем localStorage
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        localStorage_data[key] = localStorage.getItem(key);
                    }
                } catch (e) {
                    console.log('localStorage error:', e);
                }
                
                // Получаем sessionStorage
                try {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        sessionStorage_data[key] = sessionStorage.getItem(key);
                    }
                } catch (e) {
                    console.log('sessionStorage error:', e);
                }
                
                return {
                    localStorage: localStorage_data,
                    sessionStorage: sessionStorage_data
                };
            }
        """)
        
        with open(STORAGE_FILE, 'w') as f:
            json.dump(storage_data, f, indent=2)
        
        print("✅ Сессия полностью сохранена!")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения сессии: {e}")
        return False

async def load_session(context, page):
    """Загружает полную сессию"""
    session_loaded = False
    
    try:
        # Загружаем cookies
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            session_loaded = True
            print("✅ Cookies загружены!")
        
        # Загружаем localStorage и sessionStorage
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, 'r') as f:
                storage_data = json.load(f)
            
            await page.evaluate("""
                (storage_data) => {
                    // Восстанавливаем localStorage
                    try {
                        if (storage_data.localStorage) {
                            for (const [key, value] of Object.entries(storage_data.localStorage)) {
                                localStorage.setItem(key, value);
                            }
                        }
                    } catch (e) {
                        console.log('localStorage restore error:', e);
                    }
                    
                    // Восстанавливаем sessionStorage
                    try {
                        if (storage_data.sessionStorage) {
                            for (const [key, value] of Object.entries(storage_data.sessionStorage)) {
                                sessionStorage.setItem(key, value);
                            }
                        }
                    } catch (e) {
                        console.log('sessionStorage restore error:', e);
                    }
                }
            """, storage_data)
            print("✅ Storage данные загружены!")
        
        return session_loaded
    except Exception as e:
        print(f"❌ Ошибка загрузки сессии: {e}")
        return False

async def check_logged_in(page):
    """Проверяет, залогинен ли пользователь"""
    try:
        await page.goto("https://web.max.ru", timeout=15000)
        await asyncio.sleep(5)
        
        # Ждем загрузки страницы
        await page.wait_for_load_state('networkidle', timeout=10000)
        
        # Если есть поле для ввода номера - не залогинен
        login_field = await page.locator("input.field").count()
        if login_field > 0:
            print("🔐 Найдено поле для логина")
            return False
        
        # Проверяем различные элементы интерфейса чатов
        interface_selectors = [
            "[data-testid='chat-list']",
            ".chat-list",
            ".sidebar",
            ".messages",
            ".dialog-list",
            ".chats",
            ".conversations"
        ]
        
        for selector in interface_selectors:
            count = await page.locator(selector).count()
            if count > 0:
                print("✅ Найден интерфейс чатов - пользователь авторизован")
                return True
        
        print("❓ Статус авторизации неясен")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка проверки авторизации: {e}")
        return False

def create_message_hash(text, timestamp_str="", sender=""):
    """Создает уникальный хеш для сообщения"""
    # Нормализуем текст (убираем лишние пробелы и переносы)
    normalized_text = ' '.join(text.split())
    # Создаем хеш из текста, времени и отправителя
    hash_input = f"{normalized_text}|{timestamp_str}|{sender}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()

async def save_last_messages(messages_data):
    """Сохраняет данные о последних сообщениях с временными метками"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    try:
        with open(MESSAGES_FILE, 'w') as f:
            json.dump({
                'messages': messages_data,
                'last_check': time.time()
            }, f, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения сообщений: {e}")

async def load_last_messages():
    """Загружает данные о последних сообщениях"""
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, 'r') as f:
                data = json.load(f)
            return data.get('messages', {}), data.get('last_check', 0)
        except Exception as e:
            print(f"⚠️ Ошибка загрузки сообщений: {e}")
            return {}, 0
    return {}, 0

def save_last_check_time():
    """Сохраняет время последней проверки в отдельный файл"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    current_time = time.time()
    local_time = get_local_time()
    
    try:
        with open(LAST_CHECK_FILE, 'w') as f:
            json.dump({
                'last_check_time': current_time,
                'readable_time': format_local_time(local_time)
            }, f, indent=2)
        return current_time
    except Exception as e:
        print(f"❌ Ошибка сохранения времени проверки: {e}")
        return current_time

def load_last_check_time():
    """Загружает время последней проверки из файла"""
    if os.path.exists(LAST_CHECK_FILE):
        try:
            with open(LAST_CHECK_FILE, 'r') as f:
                data = json.load(f)
            return data.get('last_check_time', 0)
        except:
            pass
    return 0

async def download_image(page, img_url, img_filename):
    """Скачивает изображение и сохраняет его"""
    try:
        os.makedirs(os.path.join(SESSION_DIR, "images"), exist_ok=True)
        img_path = os.path.join(SESSION_DIR, "images", img_filename)
        
        # Используем страницу браузера для загрузки (чтобы сохранить авторизацию)
        response = await page.request.get(img_url)
        if response.ok:
            with open(img_path, 'wb') as f:
                f.write(await response.body())
            return img_path
        else:
            print(f"❌ Ошибка загрузки изображения: {response.status}")
            return None
    except Exception as e:
        print(f"❌ Ошибка скачивания изображения: {e}")
        return None

async def send_to_telegram(text, image_path=None):
    """Отправляет сообщение/изображение в Telegram с retry логикой"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Ограничиваем длину сообщения
            if len(text) > 1000:  # Для изображений делаем короче
                text = text[:1000] + "..."
            
            if image_path and os.path.exists(image_path):
                # Отправляем изображение с подписью
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
                
                with open(image_path, 'rb') as photo:
                    files = {'photo': photo}
                    data = {
                        'chat_id': TG_CHANNEL,
                        'caption': text,
                        'parse_mode': 'HTML'
                    }
                    
                    response = requests.post(url, files=files, data=data, timeout=15)
                
                # Удаляем файл после отправки
                try:
                    os.remove(image_path)
                except:
                    pass
                    
            else:
                # Отправляем обычное текстовое сообщение
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                response = requests.post(url, json={
                    "chat_id": TG_CHANNEL, 
                    "text": text,
                    "parse_mode": "HTML"
                }, timeout=10)
            
            if response.status_code == 200:
                msg_type = "изображение" if image_path else "сообщение"
                print(f"✅ Отправлено {msg_type} в Telegram")
                return True
            else:
                print(f"❌ Ошибка отправки в Telegram (попытка {attempt + 1}): {response.status_code}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    
        except Exception as e:
            print(f"❌ Ошибка отправки в Telegram (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
    
    return False

def save_status_message_id(message_id):
    """Сохраняет ID статусного сообщения"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    try:
        with open(STATUS_MESSAGE_FILE, 'w') as f:
            json.dump({'message_id': message_id}, f)
    except Exception as e:
        print(f"❌ Ошибка сохранения ID статуса: {e}")

def load_status_message_id():
    """Загружает ID статусного сообщения"""
    if os.path.exists(STATUS_MESSAGE_FILE):
        try:
            with open(STATUS_MESSAGE_FILE, 'r') as f:
                data = json.load(f)
            return data.get('message_id')
        except:
            pass
    return None

async def send_or_update_status_message(status="активен", is_initial=False):
    """Отправляет новое статусное сообщение или обновляет существующее"""
    global status_message_id
    
    current_time = format_local_time()  # Используем екатеринбургское время
    status_text = f"🤖 <b>Статус скрипта мониторинга Max</b>\n\n"
    status_text += f"📊 Состояние: <b>{status}</b>\n"
    status_text += f"🕒 Последнее обновление: <i>{current_time} (Екатеринбург)</i>"
    
    if status == "активен":
        status_text += f"\n\n🔄 Скрипт мониторит новые сообщения каждые 15 минут..."
    else:
        status_text += f"\n\n⏸️ Скрипт был остановлен"
    
    try:
        if is_initial or not status_message_id:
            # Отправляем новое сообщение
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            response = requests.post(url, json={
                "chat_id": TG_CHANNEL,
                "text": status_text,
                "parse_mode": "HTML"
            }, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                status_message_id = result['result']['message_id']
                save_status_message_id(status_message_id)
                print(f"✅ Отправлено статусное сообщение: {status}")
                return True
        else:
            # Обновляем существующее сообщение
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
            response = requests.post(url, json={
                "chat_id": TG_CHANNEL,
                "message_id": status_message_id,
                "text": status_text,
                "parse_mode": "HTML"
            }, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ Обновлено статусное сообщение: {status}")
                return True
            else:
                print(f"❌ Ошибка обновления статуса: {response.status_code}")
                # Если не удалось обновить, отправляем новое
                return await send_or_update_status_message(status, is_initial=True)
    
    except Exception as e:
        print(f"❌ Ошибка работы со статусным сообщением: {e}")
    
    return False

async def get_messages_from_page(page):
    """Получение сообщений с страницы с улучшенной обработкой ошибок"""
    messages_data = {}
    
    try:
        # Обновляем страницу для актуальных данных
        await page.reload(timeout=30000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        
        # Прокручиваем до конца чтобы загрузить последние сообщения
        await page.keyboard.press("End")
        await asyncio.sleep(3)
        
        print("🔍 Ищем сообщения на странице...")
        
        # Используем JavaScript для более точного поиска сообщений
        messages_info = await page.evaluate("""
            () => {
                const messages = [];
                
                // Расширенный список селекторов для поиска сообщений
                const selectors = [
                    '.message',
                    '[data-message]',
                    '[data-message-id]',
                    '.chat-message',
                    '.msg',
                    '.dialog-message',
                    '.message-container',
                    '.message-bubble',
                    '[class*="message"]',
                    '[id*="message"]',
                    'div[role="log"] > div',
                    '.im-page-chat-body .im-message',
                    '.tgico-message',
                    '.Message',
                    '.bubble'
                ];
                
                let foundElements = [];
                
                // Пробуем каждый селектор
                for (const selector of selectors) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            console.log(`Найдено ${elements.length} элементов с селектором: ${selector}`);
                            foundElements = Array.from(elements);
                            break;
                        }
                    } catch (e) {
                        continue;
                    }
                }
                
                // Если ничего не нашли, ищем любые div с текстом
                if (foundElements.length === 0) {
                    console.log('Ищем любые div с потенциальными сообщениями...');
                    const allDivs = document.querySelectorAll('div');
                    foundElements = Array.from(allDivs).filter(div => {
                        const text = div.textContent || '';
                        return text.length > 10 && text.length < 1000 && 
                               div.children.length < 10; // простая эвристика
                    });
                    console.log(`Найдено ${foundElements.length} потенциальных сообщений`);
                }
                
                // Обрабатываем найденные элементы
                foundElements.slice(-20).forEach((element, index) => { // берем последние 20
                    try {
                        const fullText = element.textContent || element.innerText || '';
                        if (fullText.trim().length < 2) return;
                        
                        // Ищем время в элементе
                        let timeText = '';
                        const timeSelectors = ['.time', '.timestamp', '.message-time', '[data-time]', '.date'];
                        for (const timeSelector of timeSelectors) {
                            const timeEl = element.querySelector(timeSelector);
                            if (timeEl) {
                                timeText = timeEl.textContent || '';
                                break;
                            }
                        }
                        
                        // Если время не найдено, ищем паттерны времени в тексте
                        if (!timeText) {
                            const timePattern = /\b(\d{1,2}:\d{2})\b/;
                            const timeMatch = fullText.match(timePattern);
                            if (timeMatch) {
                                timeText = timeMatch[1];
                            }
                        }
                        
                        // Ищем отправителя
                        let sender = '';
                        const senderSelectors = [
                            '.sender', '.author', '.username', '.name', 
                            '.peer-title', '.message-author', '.from'
                        ];
                        
                        for (const senderSelector of senderSelectors) {
                            const senderEl = element.querySelector(senderSelector);
                            if (senderEl) {
                                sender = senderEl.textContent || '';
                                break;
                            }
                        }
                        
                        // Ищем изображения
                        const images = [];
                        const imgElements = element.querySelectorAll('img');
                        imgElements.forEach(img => {
                            const src = img.src;
                            if (src && (src.startsWith('http') || src.startsWith('data:'))) {
                                images.push(src);
                            }
                        });
                        
                        messages.push({
                            index: index,
                            text: fullText.trim(),
                            time: timeText.trim(),
                            sender: sender.trim(),
                            images: images
                        });
                        
                    } catch (e) {
                        console.log('Ошибка обработки элемента:', e);
                    }
                });
                
                return messages;
            }
        """)
        
        print(f"📝 Найдено {len(messages_info)} потенциальных сообщений")
        
        # Обрабатываем найденные сообщения
        current_time = time.time()
        current_local_time = format_local_time()  # Используем екатеринбургское время
        
        for msg_info in messages_info:
            try:
                text = msg_info['text']
                time_str = msg_info['time']
                sender = msg_info['sender']
                images = msg_info['images']
                
                if len(text) < 3:  # пропускаем слишком короткие
                    continue
                
                # Формируем сообщение
                final_message = ""
                
                if sender:
                    final_message += f"👤 <b>От: {sender}</b>\n"
                else:
                    final_message += "💬 <b>Новое сообщение из Max!</b>\n"
                
                final_message += "─" * 25 + "\n"
                final_message += f"{text}\n"
                
                if images:
                    if len(images) == 1:
                        final_message += "📷 <i>Содержит изображение</i>\n"
                    else:
                        final_message += f"📷 <i>Содержит {len(images)} изображений</i>\n"
                
                # Добавляем время - сначала из сообщения, потом текущее екатеринбургское
                if time_str:
                    final_message += f"\n🕒 <i>Время в чате: {time_str}</i>"
                
                final_message += f"\n📅 <i>Обнаружено: {current_local_time} (Екатеринбург)</i>"
                
                # Создаем хеш
                msg_hash = create_message_hash(text, time_str, sender)
                
                # Обрабатываем первое изображение если есть
                image_path = None
                if images:
                    try:
                        first_image = images[0]
                        if first_image.startswith('http'):
                            img_filename = f"img_{msg_hash[:8]}_{int(current_time)}.jpg"
                            image_path = await download_image(page, first_image, img_filename)
                    except Exception as e:
                        print(f"⚠️ Ошибка обработки изображения: {e}")
                
                messages_data[msg_hash] = {
                    'text': final_message,
                    'timestamp': time_str,
                    'created_at': current_time,
                    'sender': sender or "Неизвестно",
                    'image_path': image_path,
                    'has_images': len(images) > 0,
                    'raw_text': text  # для отладки
                }
                
            except Exception as e:
                print(f"⚠️ Ошибка обработки сообщения: {e}")
                continue
        
        print(f"✅ Обработано {len(messages_data)} сообщений")
        return messages_data
        
    except Exception as e:
        print(f"❌ Ошибка получения сообщений: {e}")
        return {}

async def monitor_messages(page):
    """Основной цикл мониторинга сообщений с интервалом 15 минут"""
    print("🔄 Запуск мониторинга сообщений (интервал: 15 минут)...")
    
    # Отправляем/обновляем статусное сообщение
    await send_or_update_status_message("активен", is_initial=True)
    
    # Загружаем последние сообщения
    last_messages_data, last_check_time = await load_last_messages()
    
    # Получаем текущие сообщения для инициализации
    print("📡 Получаем текущее состояние сообщений...")
    current_messages_data = await get_messages_from_page(page)
    print(f"📊 Найдено {len(current_messages_data)} сообщений на странице")
    
    # Если это первый запуск или данных мало
    if not last_messages_data or len(last_messages_data) < 3:
        print("🆕 Первый запуск или мало данных - инициализируем базу сообщений")
        await save_last_messages(current_messages_data)
        last_messages_data = current_messages_data
        
        # Отправляем тестовое сообщение с екатеринбургским временем
        current_local_time = format_local_time()
        await send_to_telegram(f"🚀 <b>Мониторинг запущен!</b>\n\nСкрипт начал отслеживать новые сообщения в чате Max.\n📅 <i>Запуск: {current_local_time} (Екатеринбург)</i>\n⏰ <i>Проверка каждые 15 минут</i>")
    
    save_last_check_time()
    iteration = 0
    
    while True:
        try:
            iteration += 1
            local_time = format_local_time()
            print(f"\n🔄 Проверка #{iteration} - {local_time}")
            
            # Выполняем очистку мусора каждые 10 проверок
            if iteration % 10 == 0:
                cleanup_memory()
                # Обновляем статусное сообщение после очистки
                await send_or_update_status_message("активен")
            
            # Небольшая пауза и прокрутка
            await asyncio.sleep(3)
            
            # Получаем новые сообщения
            new_messages_data = await get_messages_from_page(page)
            
            if not new_messages_data:
                print("⚠️ Не удалось получить сообщения, пробуем еще раз...")
                await asyncio.sleep(30)
                continue
            
            # Находим сообщения которых не было в последнем снимке
            new_message_hashes = set(new_messages_data.keys()) - set(last_messages_data.keys())
            
            # Дополнительная проверка по времени создания для надежности
            recent_messages = []
            current_time = time.time()
            
            for msg_hash, msg_data in new_messages_data.items():
                # Если сообщение новое по хешу ИЛИ очень свежее (менее 20 минут)
                is_new_hash = msg_hash in new_message_hashes
                is_very_recent = (current_time - msg_data.get('created_at', 0)) < 1200  # 20 минут
                
                if is_new_hash or (is_very_recent and msg_hash not in last_messages_data):
                    recent_messages.append(msg_hash)
            
            if recent_messages:
                print(f"🆕 Найдено {len(recent_messages)} новых сообщений!")
                
                # Отправляем новые сообщения
                for msg_hash in recent_messages:
                    message_data = new_messages_data[msg_hash]
                    
                    print(f"📤 Отправляем: {message_data['raw_text'][:50]}...")
                    
                    success = await send_to_telegram(
                        message_data['text'], 
                        message_data.get('image_path')
                    )
                    
                    if success:
                        sender_info = f" от {message_data['sender']}" if message_data['sender'] != "Неизвестно" else ""
                        img_info = " (с изображением)" if message_data.get('image_path') else ""
                        print(f"✅ Отправлено{sender_info}{img_info}")
                    else:
                        print(f"❌ Ошибка отправки сообщения")
                    
                    await asyncio.sleep(2)  # пауза между отправками
                
                # Сохраняем новое состояние
                await save_last_messages(new_messages_data)
                last_messages_data = new_messages_data
                print("💾 Состояние сохранено")
                
            else:
                print("📭 Новых сообщений нет")
                
                # Обновляем базу сообщений даже если новых нет
                await save_last_messages(new_messages_data)
                last_messages_data = new_messages_data
            
            # Обновляем время последней проверки
            save_last_check_time()
            
            # Пауза 15 минут перед следующей проверкой
            print(f"⏰ Следующая проверка через 15 минут...")
            
            # Разбиваем ожидание на более мелкие интервалы для возможности прерывания
            for i in range(90):  # 90 * 10 секунд = 15 минут
                await asyncio.sleep(10)
                # Каждые 5 минут показываем прогресс
                if i % 30 == 29:  # 30 * 10 секунд = 5 минут
                    remaining = (90 - i - 1) * 10 // 60
                    print(f"⏳ Осталось {remaining} минут до следующей проверки...")
            
        except Exception as e:
            print(f"❌ Ошибка в мониторинге: {e}")
            await asyncio.sleep(60)  # При ошибке ждем 1 минуту
            continue

async def login(page, context):
    """Выполняет процедуру логина"""
    print("🔐 Выполняем вход в аккаунт...")
    
    try:
        # 1. Открываем сайт
        await page.goto("https://web.max.ru", timeout=30000)
        await page.wait_for_load_state('networkidle')

        # 2. Ищем и заполняем поле номера
        await page.wait_for_selector("input.field", timeout=30000)
        await page.fill("input.field", PHONE)
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")

        # 3. Ждём появления полей для SMS-кода
        print("⏳ Ожидание SMS-кода...")
        await page.wait_for_selector(".code input.digit", timeout=60000)

        # 4. Спрашиваем код в консоли
        sms_code = input("📱 Введи СМС-код (6 цифр): ").strip()
        
        if len(sms_code) != 6 or not sms_code.isdigit():
            print("❌ Ошибка: код должен содержать ровно 6 цифр")
            return False

        # 5. Вводим каждую цифру
        digit_inputs = await page.locator(".code input.digit").all()
        
        for i, digit in enumerate(sms_code):
            if i < len(digit_inputs):
                await digit_inputs[i].fill(digit)
                await asyncio.sleep(0.2)

        await page.keyboard.press("Enter")
        
        # 6. Ждём загрузки интерфейса
        print("⏳ Ждем загрузки интерфейса...")
        await asyncio.sleep(10)
        await page.wait_for_load_state('networkidle', timeout=30000)
        
        # 7. Сохраняем сессию
        await save_session(context, page)
        print("✅ Авторизация успешна!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False

def cleanup():
    """Функция очистки при завершении программы"""
    print("\n🔄 Завершение работы скрипта...")
    try:
        # Запускаем обновление статуса в синхронном режиме
        import requests
        current_time = format_local_time()  # Используем екатеринбургское время
        status_text = f"🤖 <b>Статус скрипта мониторинга Max</b>\n\n"
        status_text += f"📊 Состояние: <b>неактивен</b>\n"
        status_text += f"🕒 Последнее обновление: <i>{current_time} (Екатеринбург)</i>\n\n"
        status_text += f"⏸️ Скрипт был остановлен"
        
        message_id = load_status_message_id()
        if message_id:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
            response = requests.post(url, json={
                "chat_id": TG_CHANNEL,
                "message_id": message_id,
                "text": status_text,
                "parse_mode": "HTML"
            }, timeout=5)
            
            if response.status_code == 200:
                print("✅ Статус обновлен: скрипт неактивен")
            else:
                print("⚠️ Не удалось обновить статус")
        
        # Финальная очистка памяти
        cleanup_memory()
                
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении статуса: {e}")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    cleanup()
    exit(0)

async def main():
    global status_message_id
    
    # Загружаем ID статусного сообщения
    status_message_id = load_status_message_id()
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    
    async with async_playwright() as p:
        # Создаем браузер с расширенными настройками для стабильности
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--memory-pressure-off'
            ]
        )
        
        # Создаем контекст с реалистичными настройками
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        
        page = await context.new_page()

        try:
            # Загружаем сохраненную сессию
            session_loaded = await load_session(context, page)
            
            # Проверяем, нужно ли логиниться
            logged_in = False
            if session_loaded:
                logged_in = await check_logged_in(page)
            
            if not logged_in:
                print("🔑 Требуется авторизация...")
                if not await login(page, context):
                    print("❌ Не удалось войти в аккаунт")
                    await browser.close()
                    return
            else:
                print("✅ Уже авторизован! Пропускаем вход...")

            # Переходим в чат и запускаем мониторинг
            print("📱 Переходим в чат...")
            await page.goto("https://web.max.ru/-68122153113024", timeout=30000)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(5)
            
            print("🎯 Чат загружен! Запускаем мониторинг с интервалом 15 минут...")
            print("💡 Для остановки нажми Ctrl+C")
            
            # Запускаем бесконечный мониторинг
            await monitor_messages(page)
            
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки...")
            await send_or_update_status_message("неактивен")
        except Exception as e:
            print(f"\n💥 Критическая ошибка: {e}")
            await send_or_update_status_message("неактивен")
            import traceback
            traceback.print_exc()
        finally:
            print("🧹 Закрываем браузер...")
            await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Мониторинг остановлен пользователем")
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

