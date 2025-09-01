import asyncio
from playwright.async_api import async_playwright
import requests
import os
import json
import time
from datetime import datetime, timedelta
import hashlib
import signal
import atexit

# --- ДАННЫЕ ---
PHONE = "9944476229"  # твой номер
TG_BOT_TOKEN = "8487304030:AAEemcE1Y9J1plzoOlZuxm8XDF_7WzQZtI4"
TG_CHANNEL = "@max_bridgetotg"

# Путь для сохранения сессии
SESSION_DIR = "./max_session"
COOKIES_FILE = os.path.join(SESSION_DIR, "cookies.json")
STORAGE_FILE = os.path.join(SESSION_DIR, "storage.json")
MESSAGES_FILE = os.path.join(SESSION_DIR, "last_messages.json")
LAST_CHECK_FILE = os.path.join(SESSION_DIR, "last_check_time.json")
STATUS_MESSAGE_FILE = os.path.join(SESSION_DIR, "status_message.json")

# Глобальная переменная для ID статусного сообщения
status_message_id = None

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
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    localStorage_data[key] = localStorage.getItem(key);
                }
                
                // Получаем sessionStorage
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    sessionStorage_data[key] = sessionStorage.getItem(key);
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
                    if (storage_data.localStorage) {
                        for (const [key, value] of Object.entries(storage_data.localStorage)) {
                            localStorage.setItem(key, value);
                        }
                    }
                    
                    // Восстанавливаем sessionStorage
                    if (storage_data.sessionStorage) {
                        for (const [key, value] of Object.entries(storage_data.sessionStorage)) {
                            sessionStorage.setItem(key, value);
                        }
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

def create_message_hash(text, timestamp_str=""):
    """Создает уникальный хеш для сообщения"""
    # Нормализуем текст (убираем лишние пробелы и переносы)
    normalized_text = ' '.join(text.split())
    # Создаем хеш из текста и времени
    hash_input = f"{normalized_text}|{timestamp_str}"
    return hashlib.md5(hash_input.encode('utf-8')).hexdigest()

async def save_last_messages(messages_data):
    """Сохраняет данные о последних сообщениях с временными метками"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(MESSAGES_FILE, 'w') as f:
        json.dump({
            'messages': messages_data,
            'last_check': time.time()
        }, f, indent=2)

async def load_last_messages():
    """Загружает данные о последних сообщениях"""
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, 'r') as f:
                data = json.load(f)
            return data.get('messages', {}), data.get('last_check', 0)
        except:
            return {}, 0
    return {}, 0

def save_last_check_time():
    """Сохраняет время последней проверки в отдельный файл"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    current_time = time.time()
    with open(LAST_CHECK_FILE, 'w') as f:
        json.dump({
            'last_check_time': current_time,
            'readable_time': datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        }, f, indent=2)
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

def is_message_recent(message_time_str, last_check_timestamp):
    """Проверяет, является ли сообщение новее времени последней проверки"""
    try:
        # Пробуем разные форматы времени
        time_formats = [
            "%H:%M",
            "%H:%M:%S", 
            "%d.%m %H:%M",
            "%d/%m %H:%M",
            "сегодня %H:%M",
            "вчера %H:%M"
        ]
        
        message_time = None
        now = datetime.now()
        
        # Обработка относительных времен
        if "сегодня" in message_time_str.lower():
            time_part = message_time_str.lower().replace("сегодня", "").strip()
            try:
                message_time = datetime.strptime(time_part, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
            except:
                pass
        elif "вчера" in message_time_str.lower():
            time_part = message_time_str.lower().replace("вчера", "").strip()
            try:
                yesterday = now - timedelta(days=1)
                message_time = datetime.strptime(time_part, "%H:%M").replace(
                    year=yesterday.year, month=yesterday.month, day=yesterday.day
                )
            except:
                pass
        else:
            # Пробуем стандартные форматы
            for fmt in time_formats:
                try:
                    if "%d" not in fmt:  # Только время
                        message_time = datetime.strptime(message_time_str, fmt).replace(
                            year=now.year, month=now.month, day=now.day
                        )
                    else:  # Дата и время
                        message_time = datetime.strptime(message_time_str, fmt).replace(year=now.year)
                    break
                except:
                    continue
        
        if message_time:
            # Сравниваем с временем последней проверки
            message_timestamp = message_time.timestamp()
            return message_timestamp > last_check_timestamp
            
    except Exception as e:
        print(f"⚠️ Ошибка парсинга времени '{message_time_str}': {e}")
    
    # Если не удалось распарсить время, считаем сообщение новым (безопасный подход)
    return True

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
                print(f"✅ Отправлено {msg_type} в Telegram: {text[:50]}...")
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
    with open(STATUS_MESSAGE_FILE, 'w') as f:
        json.dump({'message_id': message_id}, f)

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
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status_text = f"🤖 <b>Статус скрипта мониторинга Max</b>\n\n"
    status_text += f"📊 Состояние: <b>{status}</b>\n"
    status_text += f"🕒 Последнее обновление: <i>{current_time}</i>"
    
    if status == "активен":
        status_text += f"\n\n🔄 Скрипт мониторит новые сообщения..."
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
    """Получает все сообщения с страницы с улучшенным парсингом"""
    messages_data = {}
    last_check_timestamp = load_last_check_time()
    
    # Расширенный список селекторов для сообщений
    possible_selectors = [
        ".message",
        "[data-message]",
        ".chat-message", 
        ".msg",
        "div[role='log'] > div",
        ".message-container",
        ".dialog-message",
        ".chat-item",
        ".message-bubble"
    ]
    
    found_selector = None
    for selector in possible_selectors:
        try:
            elements = await page.locator(selector).count()
            if elements > 0:
                found_selector = selector
                print(f"✅ Найден селектор сообщений: {selector} ({elements} элементов)")
                break
        except:
            continue
    
    if not found_selector:
        print("❌ Не удалось найти сообщения на странице")
        return messages_data
    
    # Получаем все элементы сообщений
    message_elements = await page.locator(found_selector).all()
    
    for idx, msg_element in enumerate(message_elements):
        try:
            # Получаем весь текст элемента
            full_text = await msg_element.text_content()
            if not full_text or len(full_text.strip()) < 2:
                continue
            
            # Ищем время сообщения
            time_text = ""
            time_selectors = [
                ".time", ".timestamp", ".message-time", 
                "[data-time]", ".date", ".msg-time"
            ]
            
            for time_sel in time_selectors:
                try:
                    time_elem = msg_element.locator(time_sel).first
                    if await time_elem.count() > 0:
                        time_text = await time_elem.text_content()
                        break
                except:
                    continue
            
            # ИСПРАВЛЕННЫЙ парсинг отправителя
            sender = ""
            message_text = full_text.strip()
            
            # Расширенные селекторы для отправителя
            sender_selectors = [
                ".sender", ".author", ".username", ".name", 
                "[data-sender]", ".message-author", ".from",
                ".peer-title", ".dialog-peer-title", ".user-name",
                ".message-name", ".chat-title", ".contact-name",
                "[data-peer-id] .name", ".avatar + .name"
            ]
            
            for sender_sel in sender_selectors:
                try:
                    sender_elem = msg_element.locator(sender_sel).first
                    if await sender_elem.count() > 0:
                        sender_text = await sender_elem.text_content()
                        if sender_text and sender_text.strip():
                            sender = sender_text.strip()
                            break
                except:
                    continue
            
            # ИСПРАВЛЕННЫЕ дополнительные методы поиска отправителя
            if not sender:
                try:
                    # Ищем в родительских элементах - ИСПРАВЛЕНО
                    parent = msg_element.locator('..')
                    for sender_sel in sender_selectors:
                        try:
                            sender_elem = parent.locator(sender_sel).first
                            sender_count = await sender_elem.count()
                            if sender_count > 0:
                                sender_text = await sender_elem.text_content()
                                if sender_text and sender_text.strip():
                                    sender = sender_text.strip()
                                    break
                        except:
                            continue
                    
                    # Ищем по data-атрибутам
                    if not sender:
                        try:
                            data_attrs = await msg_element.evaluate("""
                                element => {
                                    const attrs = {};
                                    for (let attr of element.attributes) {
                                        if (attr.name.includes('peer') || attr.name.includes('user') || attr.name.includes('sender')) {
                                            attrs[attr.name] = attr.value;
                                        }
                                    }
                                    return attrs;
                                }
                            """)
                            
                            for attr_name, attr_value in data_attrs.items():
                                if attr_value and len(attr_value) < 50:
                                    sender = attr_value
                                    break
                        except:
                            pass
                                
                except Exception as e:
                    # Убираем спам в терминал - просто игнорируем ошибку
                    pass
            
            # Если отправитель все еще не найден, пробуем извлечь из текста
            if not sender and message_text:
                lines = message_text.split('\n')
                if len(lines) > 1:
                    potential_sender = lines[0].strip()
                    # Улучшенная эвристика для определения отправителя
                    if (len(potential_sender) < 50 and 
                        not potential_sender.replace(':', '').replace(' ', '').isdigit() and
                        (':' in potential_sender or 
                         potential_sender.endswith('написал') or 
                         potential_sender.endswith('отправил') or
                         any(word in potential_sender.lower() for word in ['admin', 'moderator', 'пользователь']))):
                        sender = potential_sender.replace(':', '').strip()
                        message_text = '\n'.join(lines[1:]).strip()
            
            # Ищем изображения в сообщении
            images = []
            image_selectors = [
                "img", ".image", ".photo", ".picture",
                "[data-type='photo']", ".message-media img"
            ]
            
            for img_sel in image_selectors:
                try:
                    img_elements = await msg_element.locator(img_sel).all()
                    for img_elem in img_elements:
                        img_src = await img_elem.get_attribute('src')
                        if img_src and ('http' in img_src or img_src.startswith('data:image')):
                            images.append(img_src)
                except:
                    continue
            
            # Очищаем текст от времени если оно включено
            if time_text and time_text in message_text:
                message_text = message_text.replace(time_text, '').strip()
            
            # Пропускаем сообщения старше времени последней проверки
            if time_text and not is_message_recent(time_text, last_check_timestamp):
                continue
            
            # Формируем финальное сообщение с улучшенным форматированием
            final_message = ""
            
            # Добавляем информацию об отправителе
            if sender:
                # Очищаем имя отправителя от лишних символов
                clean_sender = sender.replace('написал:', '').replace('отправил:', '').strip()
                final_message = f"👤 <b>От: {clean_sender}</b>\n"
            else:
                final_message = "💬 <b>Новое сообщение из Max!</b>\n"
            
            # Добавляем разделитель
            final_message += "─" * 25 + "\n"
            
            # Добавляем текст сообщения
            if message_text and message_text.strip():
                final_message += f"{message_text}\n"
            
            # Добавляем информацию об изображениях
            if images:
                if len(images) == 1:
                    final_message += "📷 <i>Содержит изображение</i>\n"
                else:
                    final_message += f"📷 <i>Содержит {len(images)} изображений</i>\n"
            
            # Добавляем время
            if time_text:
                final_message += f"\n🕒 <i>{time_text}</i>"
            
            # Создаем уникальный хеш
            hash_content = message_text + (sender or "") + (time_text or "")
            msg_hash = create_message_hash(hash_content, time_text)
            
            # Обрабатываем первое изображение если есть
            image_path = None
            if images:
                try:
                    first_image = images[0]
                    if first_image.startswith('http'):
                        # Генерируем имя файла
                        img_filename = f"img_{msg_hash[:8]}_{int(time.time())}.jpg"
                        image_path = await download_image(page, first_image, img_filename)
                except Exception as e:
                    print(f"⚠️ Ошибка обработки изображения: {e}")
            
            messages_data[msg_hash] = {
                'text': final_message,
                'timestamp': time_text,
                'created_at': time.time(),
                'sender': sender or "Неизвестно",
                'image_path': image_path,
                'has_images': len(images) > 0
            }
                
        except Exception as e:
            print(f"⚠️ Ошибка при парсинге сообщения {idx}: {e}")
            continue
    
    return messages_data

async def monitor_messages(page):
    """Основной цикл мониторинга сообщений"""
    print("🔄 Запуск мониторинга сообщений...")
    
    # Отправляем/обновляем статусное сообщение
    await send_or_update_status_message("активен", is_initial=True)
    
    # Сохраняем время начала мониторинга
    save_last_check_time()
    
    # Загружаем последние сообщения
    last_messages_data, last_check_time = await load_last_messages()
    
    # Получаем текущие сообщения для инициализации
    current_messages_data = await get_messages_from_page(page)
    print(f"📝 Найдено {len(current_messages_data)} актуальных сообщений на странице")
    
    # Если это первый запуск, сохраняем все текущие сообщения как "старые"
    if not last_messages_data:
        print("🆕 Первый запуск - помечаем все текущие сообщения как прочитанные")
        await save_last_messages(current_messages_data)
        last_messages_data = current_messages_data
    
    while True:
        try:
            # Небольшая пауза перед обновлением
            await asyncio.sleep(2)
            
            # Прокручиваем вниз чтобы загрузить новые сообщения
            await page.keyboard.press("End")
            await asyncio.sleep(1)
            
            # Получаем новые сообщения
            new_messages_data = await get_messages_from_page(page)
            
            # Находим действительно новые сообщения
            new_message_hashes = set(new_messages_data.keys()) - set(last_messages_data.keys())
            
            if new_message_hashes:
                print(f"🆕 Найдено {len(new_message_hashes)} новых сообщений!")
                
                # Отправляем только новые сообщения
                for msg_hash in new_message_hashes:
                    message_data = new_messages_data[msg_hash]
                    
                    # Отправляем сообщение с изображением или без
                    success = await send_to_telegram(
                        message_data['text'], 
                        message_data.get('image_path')
                    )
                    
                    if success:
                        sender_info = f" от {message_data['sender']}" if message_data['sender'] != "Неизвестно" else ""
                        img_info = " (с изображением)" if message_data.get('image_path') else ""
                        print(f"✅ Сообщение отправлено{sender_info}{img_info}: {msg_hash[:8]}...")
                    
                    await asyncio.sleep(2)  # пауза между отправками
                
                # Сохраняем новое состояние
                await save_last_messages(new_messages_data)
                last_messages_data = new_messages_data
            else:
                print("📭 Новых сообщений нет")
            
            # Обновляем время последней проверки
            save_last_check_time()
            
            # Пауза перед следующей проверкой
            print(f"⏰ Следующая проверка через 15 секунд... ({datetime.now().strftime('%H:%M:%S')})")
            await asyncio.sleep(15)
            
        except Exception as e:
            print(f"❌ Ошибка в мониторинге: {e}")
            await asyncio.sleep(5)  # пауза при ошибке
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
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status_text = f"🤖 <b>Статус скрипта мониторинга Max</b>\n\n"
        status_text += f"📊 Состояние: <b>неактивен</b>\n"
        status_text += f"🕒 Последнее обновление: <i>{current_time}</i>\n\n"
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
        # Создаем браузер с расширенными настройками
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
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
            await page.goto("https://web.max.ru/-68115395545773", timeout=30000)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(5)
            
            print("🎯 Чат загружен! Запускаем постоянный мониторинг...")
            print("💡 Для остановки нажми Ctrl+C")
            
            # Запускаем бесконечный мониторинг
            await monitor_messages(page)
            
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки...")
            await send_or_update_status_message("неактивен")
        except Exception as e:
            print(f"\n💥 Критическая ошибка: {e}")
            await send_or_update_status_message("неактивен")
        finally:
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