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
import glob
import shutil

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
    """Сохраняет полную сессию с улучшенной надежностью"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    
    try:
        # Ждем стабилизации страницы
        await page.wait_for_load_state('networkidle', timeout=10000)
        await asyncio.sleep(2)
        
        # Сохраняем cookies с полным URL контекстом
        all_cookies = await context.cookies()
        # Добавляем cookies для всех поддоменов max.ru
        cookies_with_domains = []
        for cookie in all_cookies:
            cookies_with_domains.append(cookie)
            # Добавляем вариант для поддомена web.max.ru если его нет
            if cookie.get('domain') == '.max.ru' or cookie.get('domain') == 'max.ru':
                web_cookie = cookie.copy()
                web_cookie['domain'] = '.max.ru'
                cookies_with_domains.append(web_cookie)
        
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies_with_domains, f, indent=2, ensure_ascii=False)
        
        # Улучшенное сохранение storage с обработкой ошибок
        try:
            storage_data = await page.evaluate("""
                () => {
                    try {
                        const localStorage_data = {};
                        const sessionStorage_data = {};
                        
                        // Получаем localStorage
                        if (typeof localStorage !== 'undefined') {
                            for (let i = 0; i < localStorage.length; i++) {
                                try {
                                    const key = localStorage.key(i);
                                    if (key) {
                                        localStorage_data[key] = localStorage.getItem(key);
                                    }
                                } catch (e) {
                                    console.log('Error reading localStorage key:', e);
                                }
                            }
                        }
                        
                        // Получаем sessionStorage
                        if (typeof sessionStorage !== 'undefined') {
                            for (let i = 0; i < sessionStorage.length; i++) {
                                try {
                                    const key = sessionStorage.key(i);
                                    if (key) {
                                        sessionStorage_data[key] = sessionStorage.getItem(key);
                                    }
                                } catch (e) {
                                    console.log('Error reading sessionStorage key:', e);
                                }
                            }
                        }
                        
                        return {
                            localStorage: localStorage_data,
                            sessionStorage: sessionStorage_data,
                            url: window.location.href,
                            timestamp: Date.now()
                        };
                    } catch (error) {
                        return {
                            localStorage: {},
                            sessionStorage: {},
                            url: window.location.href,
                            timestamp: Date.now(),
                            error: error.message
                        };
                    }
                }
            """)
            
            with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
        except Exception as storage_error:
            print(f"⚠️ Ошибка сохранения storage (игнорируется): {storage_error}")
        
        print("✅ Сессия полностью сохранена!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка сохранения сессии: {e}")
        return False

async def load_session(context, page):
    """Загружает полную сессию с улучшенной надежностью"""
    session_loaded = False
    
    try:
        # Сначала идем на главную страницу
        await page.goto("https://web.max.ru", timeout=30000)
        await asyncio.sleep(2)
        
        # Загружаем cookies
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                
                # Фильтруем и добавляем только валидные cookies
                valid_cookies = []
                for cookie in cookies:
                    try:
                        # Убеждаемся что у cookie есть все необходимые поля
                        if all(key in cookie for key in ['name', 'value']):
                            # Устанавливаем домен если не указан
                            if 'domain' not in cookie or not cookie['domain']:
                                cookie['domain'] = '.max.ru'
                            if 'path' not in cookie:
                                cookie['path'] = '/'
                            valid_cookies.append(cookie)
                    except Exception as cookie_error:
                        print(f"⚠️ Пропускаем невалидный cookie: {cookie_error}")
                        continue
                
                if valid_cookies:
                    await context.add_cookies(valid_cookies)
                    session_loaded = True
                    print(f"✅ Загружено {len(valid_cookies)} cookies!")
                
            except Exception as cookies_error:
                print(f"⚠️ Ошибка загрузки cookies: {cookies_error}")
        
        # Перезагружаем страницу с cookies
        if session_loaded:
            await page.reload()
            await page.wait_for_load_state('networkidle', timeout=15000)
            await asyncio.sleep(2)
        
        # Загружаем localStorage и sessionStorage
        if os.path.exists(STORAGE_FILE):
            try:
                with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                    storage_data = json.load(f)
                
                await page.evaluate("""
                    (storage_data) => {
                        try {
                            // Восстанавливаем localStorage
                            if (storage_data.localStorage && typeof localStorage !== 'undefined') {
                                for (const [key, value] of Object.entries(storage_data.localStorage)) {
                                    try {
                                        if (key && value !== null && value !== undefined) {
                                            localStorage.setItem(key, value);
                                        }
                                    } catch (e) {
                                        console.log('Error setting localStorage:', key, e);
                                    }
                                }
                            }
                            
                            // Восстанавливаем sessionStorage
                            if (storage_data.sessionStorage && typeof sessionStorage !== 'undefined') {
                                for (const [key, value] of Object.entries(storage_data.sessionStorage)) {
                                    try {
                                        if (key && value !== null && value !== undefined) {
                                            sessionStorage.setItem(key, value);
                                        }
                                    } catch (e) {
                                        console.log('Error setting sessionStorage:', key, e);
                                    }
                                }
                            }
                        } catch (error) {
                            console.log('Storage restoration error:', error);
                        }
                    }
                """, storage_data)
                print("✅ Storage данные загружены!")
                
            except Exception as storage_error:
                print(f"⚠️ Ошибка загрузки storage: {storage_error}")
        
        return session_loaded
        
    except Exception as e:
        print(f"❌ Ошибка загрузки сессии: {e}")
        return False

async def check_logged_in(page):
    """ИСПРАВЛЕННАЯ проверка авторизации - более надежная"""
    try:
        print("🔍 Проверяем статус авторизации...")
        
        # Ждем загрузки страницы
        await page.wait_for_load_state('networkidle', timeout=15000)
        await asyncio.sleep(3)
        
        # Получаем текущий URL
        current_url = page.url
        print(f"📍 Текущий URL: {current_url}")
        
        # ПЕРВЫЙ И ГЛАВНЫЙ ПРИЗНАК - проверяем наличие поля ввода номера телефона
        login_field_count = await page.locator("input.field").count()
        print(f"🔍 Найдено полей для ввода номера: {login_field_count}")
        
        if login_field_count > 0:
            # Проверяем, что это именно поле для номера телефона
            try:
                field_placeholder = await page.locator("input.field").first.get_attribute("placeholder")
                field_type = await page.locator("input.field").first.get_attribute("type")
                print(f"🔍 Placeholder поля: '{field_placeholder}', тип: '{field_type}'")
                
                # Если есть поле с placeholder для телефона или типом tel
                if (field_placeholder and any(word in field_placeholder.lower() for word in ['телефон', 'phone', 'номер']) or 
                    field_type == 'tel' or
                    'login' in current_url.lower()):
                    print("🔐 Обнаружена страница входа (поле для номера телефона)")
                    return False
            except Exception as field_error:
                print(f"⚠️ Ошибка анализа поля: {field_error}")
                # Если есть поле input.field, скорее всего это форма входа
                print("🔐 Обнаружено поле ввода - вероятно страница входа")
                return False
        
        # ВТОРОЙ ПРИЗНАК - проверяем URL на предмет страниц входа
        if any(keyword in current_url.lower() for keyword in ['login', 'auth', 'signin', 'enter']):
            print("🔐 URL содержит ключевые слова страницы входа")
            return False
        
        # ТРЕТИЙ ПРИЗНАК - проверяем наличие элементов интерфейса чата
        interface_selectors = [
            "[data-testid='chat-list']",
            ".chat-list",
            ".sidebar", 
            ".messages",
            ".dialog-list",
            ".chats",
            ".conversations",
            ".peer-title",
            ".dialog-title",
            ".message",
            ".chat-input",
            ".input-message-input"
        ]
        
        found_interface_elements = 0
        for selector in interface_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"✅ Найден элемент интерфейса чата: {selector} ({count} шт.)")
                    found_interface_elements += 1
            except:
                continue
        
        # Если найдено 2 или больше элементов интерфейса чата
        if found_interface_elements >= 2:
            print(f"✅ Найдено {found_interface_elements} элементов интерфейса чата - пользователь авторизован")
            return True
        
        # ЧЕТВЕРТЫЙ ПРИЗНАК - анализируем заголовок страницы
        try:
            page_title = await page.title()
            print(f"🔍 Заголовок страницы: '{page_title}'")
            
            if any(word in page_title.lower() for word in ['вход', 'login', 'auth', 'войти']):
                print("🔐 Заголовок страницы указывает на форму входа")
                return False
            elif any(word in page_title.lower() for word in ['max', 'чат', 'сообщения']):
                print("✅ Заголовок указывает на основной интерфейс")
                return True
        except Exception as title_error:
            print(f"⚠️ Ошибка получения заголовка: {title_error}")
        
        # ПЯТЫЙ ПРИЗНАК - проверяем содержимое страницы
        try:
            page_content = await page.content()
            
            # Ищем признаки формы входа
            login_indicators = ['введите номер', 'enter phone', 'войти', 'sign in', 'login']
            found_login_indicators = sum(1 for indicator in login_indicators if indicator in page_content.lower())
            
            # Ищем признаки интерфейса чата
            chat_indicators = ['диалоги', 'сообщения', 'чаты', 'dialogs', 'messages', 'chats']
            found_chat_indicators = sum(1 for indicator in chat_indicators if indicator in page_content.lower())
            
            print(f"🔍 Найдено признаков входа: {found_login_indicators}, признаков чата: {found_chat_indicators}")
            
            if found_login_indicators > found_chat_indicators and found_login_indicators >= 2:
                print("🔐 В содержимом преобладают признаки формы входа")
                return False
            elif found_chat_indicators >= 2:
                print("✅ В содержимом найдены признаки интерфейса чата")
                return True
                
        except Exception as content_error:
            print(f"⚠️ Ошибка анализа содержимого: {content_error}")
        
        # Если ничего не определили точно, считаем что НЕ авторизован (безопасный подход)
        print("❓ Статус авторизации не определен четко - требуется проверка входа")
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
    """ИСПРАВЛЕННАЯ проверка времени сообщения с добавлением даты"""
    try:
        # Пробуем разные форматы времени
        time_formats = [
            "%H:%M",
            "%H:%M:%S", 
            "%d.%m %H:%M",
            "%d/%m %H:%M",
            "%d.%m.%Y %H:%M",
            "%d/%m/%Y %H:%M",
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
                        if "%Y" in fmt:  # Полный год
                            message_time = datetime.strptime(message_time_str, fmt)
                        else:  # Без года
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

def format_message_time(time_text):
    """НОВАЯ функция: форматирует время сообщения с добавлением даты"""
    try:
        now = datetime.now()
        
        # Если уже есть дата в сообщении, возвращаем как есть
        if any(sep in time_text for sep in ['.', '/', '-']) and len(time_text) > 8:
            return time_text
        
        # Обработка относительных времен
        if "сегодня" in time_text.lower():
            time_part = time_text.lower().replace("сегодня", "").strip()
            return f"{now.strftime('%d.%m.%Y')} {time_part}"
        elif "вчера" in time_text.lower():
            yesterday = now - timedelta(days=1)
            time_part = time_text.lower().replace("вчера", "").strip()
            return f"{yesterday.strftime('%d.%m.%Y')} {time_part}"
        else:
            # Если только время (HH:MM), добавляем сегодняшнюю дату
            if ":" in time_text and len(time_text) <= 8:
                return f"{now.strftime('%d.%m.%Y')} {time_text}"
        
        return time_text
    except Exception as e:
        print(f"⚠️ Ошибка форматирования времени: {e}")
        return time_text

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

def cleanup_images():
    """Автоматическая очистка папки с изображениями"""
    try:
        images_dir = os.path.join(SESSION_DIR, "images")
        if not os.path.exists(images_dir):
            return
        
        # Получаем все файлы изображений
        image_files = glob.glob(os.path.join(images_dir, "*"))
        
        if not image_files:
            return
        
        current_time = time.time()
        deleted_count = 0
        
        for img_file in image_files:
            try:
                # Удаляем файлы старше 1 часа
                file_age = current_time - os.path.getmtime(img_file)
                if file_age > 3600:  # 1 час в секундах
                    os.remove(img_file)
                    deleted_count += 1
            except Exception as file_error:
                print(f"⚠️ Ошибка удаления файла {img_file}: {file_error}")
        
        if deleted_count > 0:
            print(f"🗑️ Удалено {deleted_count} старых изображений")
            
        # Если файлов слишком много (больше 50), удаляем самые старые
        remaining_files = glob.glob(os.path.join(images_dir, "*"))
        if len(remaining_files) > 50:
            # Сортируем по времени создания
            remaining_files.sort(key=lambda x: os.path.getmtime(x))
            files_to_delete = remaining_files[:-30]  # Оставляем только 30 самых новых
            
            for old_file in files_to_delete:
                try:
                    os.remove(old_file)
                    deleted_count += 1
                except Exception as file_error:
                    print(f"⚠️ Ошибка удаления старого файла {old_file}: {file_error}")
            
            print(f"🗑️ Дополнительно удалено {len(files_to_delete)} файлов (лимит достигнут)")
                    
    except Exception as e:
        print(f"⚠️ Ошибка очистки изображений: {e}")

async def send_or_update_status_message(status="активен"):
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
        # Всегда пытаемся обновить существующее сообщение
        if status_message_id:
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
                print(f"⚠️ Не удалось обновить статус (код {response.status_code}), отправляем новое...")
                # Если не удалось обновить, сбрасываем ID и отправляем новое
                status_message_id = None
        
        # Отправляем новое сообщение только если не удалось обновить существующее
        if not status_message_id:
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
                print(f"✅ Отправлено новое статусное сообщение: {status}")
                return True
    
    except Exception as e:
        print(f"❌ Ошибка работы со статусным сообщением: {e}")
    
    return False

async def get_messages_from_page(page):
    """ИСПРАВЛЕННАЯ функция получения сообщений с улучшенным парсингом и добавлением даты"""
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
            
            # Парсинг отправителя
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
            
            # Дополнительные методы поиска отправителя
            if not sender:
                try:
                    # Ищем в родительских элементах
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
                    # Игнорируем ошибку
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
            
            # ИСПРАВЛЕННОЕ форматирование времени с датой
            formatted_time = format_message_time(time_text) if time_text else ""
            
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
            
            # Добавляем время с датой
            if formatted_time:
                final_message += f"\n📅 <i>{formatted_time}</i>"
            
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
                'formatted_time': formatted_time,
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
    await send_or_update_status_message("активен")
    
    # Сохраняем время начала мониторинга
    save_last_check_time()
    
    # Очищаем старые изображения при запуске
    cleanup_images()
    
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
    
    # Счетчик для периодической очистки
    cleanup_counter = 0
    
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
                        time_info = f" в {message_data['formatted_time']}" if message_data.get('formatted_time') else ""
                        print(f"✅ Сообщение отправлено{sender_info}{img_info}{time_info}: {msg_hash[:8]}...")
                    
                    await asyncio.sleep(2)  # пауза между отправками
                
                # Сохраняем новое состояние
                await save_last_messages(new_messages_data)
                last_messages_data = new_messages_data
            else:
                print("📭 Новых сообщений нет")
            
            # Обновляем время последней проверки
            save_last_check_time()
            
            # Периодическая очистка изображений (каждые 10 проверок)
            cleanup_counter += 1
            if cleanup_counter >= 10:
                cleanup_images()
                cleanup_counter = 0
            
            # Пауза перед следующей проверкой
            print(f"⏰ Следующая проверка через 30 минут... ({datetime.now().strftime('%H:%M:%S')})")
            await asyncio.sleep(1800)
            
        except Exception as e:
            print(f"❌ Ошибка в мониторинге: {e}")
            await asyncio.sleep(5)  # пауза при ошибке
            continue

async def login(page, context):
    """ИСПРАВЛЕННАЯ функция входа - теперь НЕ ПЫТАЕТСЯ входить если уже авторизован"""
    print("🔐 Проверяем необходимость входа в аккаунт...")
    
    try:
        # ВАЖНО: Сначала проверяем, не авторизованы ли мы уже
        if await check_logged_in(page):
            print("✅ Пользователь уже авторизован! Пропускаем процедуру входа.")
            return True
        
        print("🔐 Требуется авторизация. Выполняем вход...")
        
        # 1. Убеждаемся что мы на правильной странице
        current_url = page.url
        if 'web.max.ru' not in current_url:
            await page.goto("https://web.max.ru", timeout=30000)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)
        
        # 2. Еще раз проверяем после перехода
        if await check_logged_in(page):
            print("✅ После перехода оказались авторизованы!")
            return True

        # 3. Ищем и заполняем поле номера только если точно нужно
        print("📱 Ищем поле для ввода номера телефона...")
        try:
            await page.wait_for_selector("input.field", timeout=10000)
        except:
            print("❌ Поле для ввода номера не найдено в течение 10 секунд")
            return False
        
        # Проверяем, что поле действительно для номера телефона
        field_element = page.locator("input.field").first
        field_placeholder = await field_element.get_attribute("placeholder")
        
        if field_placeholder and not any(word in field_placeholder.lower() for word in ['телефон', 'phone', 'номер']):
            print(f"⚠️ Найденное поле может быть не для номера телефона (placeholder: '{field_placeholder}')")
            # Но все равно пробуем, может быть это оно
        
        print(f"📝 Вводим номер телефона: {PHONE}")
        await field_element.fill(PHONE)
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")

        # 4. Ждём появления полей для SMS-кода
        print("⏳ Ожидание SMS-кода...")
        try:
            await page.wait_for_selector(".code input.digit", timeout=60000)
        except:
            print("❌ Поля для SMS-кода не появились в течение 60 секунд")
            return False

        # 5. Спрашиваем код в консоли
        sms_code = input("📱 Введи СМС-код (6 цифр): ").strip()
        
        if len(sms_code) != 6 or not sms_code.isdigit():
            print("❌ Ошибка: код должен содержать ровно 6 цифр")
            return False

        # 6. Вводим каждую цифру
        digit_inputs = await page.locator(".code input.digit").all()
        
        for i, digit in enumerate(sms_code):
            if i < len(digit_inputs):
                await digit_inputs[i].fill(digit)
                await asyncio.sleep(0.2)

        await page.keyboard.press("Enter")
        
        # 7. Ждём загрузки интерфейса с увеличенным временем ожидания
        print("⏳ Ждем загрузки интерфейса...")
        await asyncio.sleep(10)
        
        # Ждем полной загрузки страницы
        await page.wait_for_load_state('networkidle', timeout=45000)
        await asyncio.sleep(5)
        
        # 8. Проверяем успешность входа
        login_successful = await check_logged_in(page)
        
        if not login_successful:
            print("❌ Не удалось подтвердить успешный вход")
            return False
        
        # 9. Сохраняем сессию с несколькими попытками
        print("💾 Сохранение сессии...")
        save_attempts = 0
        while save_attempts < 3:
            if await save_session(context, page):
                break
            save_attempts += 1
            await asyncio.sleep(2)
        
        if save_attempts >= 3:
            print("⚠️ Не удалось сохранить сессию, но вход выполнен")
        
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
            print("🔄 Загружаем сохраненную сессию...")
            session_loaded = await load_session(context, page)
            
            # ИСПРАВЛЕННАЯ логика проверки авторизации
            logged_in = False
            if session_loaded:
                print("✅ Сессия загружена, проверяем авторизацию...")
                logged_in = await check_logged_in(page)
            else:
                print("⚠️ Сессия не загружена или повреждена")
            
            # Выполняем вход только если НЕ авторизованы
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