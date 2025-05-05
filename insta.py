import telebot
import os
from telebot.async_telebot import AsyncTeleBot
import asyncio
import sys
import aiohttp
import tempfile
import shutil # Оставим импорт, хотя в новой функции он не используется
from bs4 import BeautifulSoup
from urllib.parse import urlparse # <<< Добавлен импорт
import traceback # <<< Добавлен импорт
from playwright.async_api import async_playwright

# --- Чтение токена бота из файла ---
try:
    # Используем относительный путь, если скрипт и файл в одной папке
    token_file_path = os.path.join(os.path.dirname(__file__), 'bot-token.txt')
    if not os.path.exists(token_file_path):
        # Если не найден рядом, пробуем абсолютный путь (как в оригинале)
        token_file_path = 'bot-token.txt'

    with open(token_file_path, 'r') as file:
        botToken = file.read().strip() # .strip() удаляет пробелы и переносы строк
except FileNotFoundError:
    print(f"Ошибка: Файл токена 'bot-token.txt' не найден.")
    print("Пожалуйста, убедитесь, что файл существует в той же папке, что и скрипт, или по пути 'bot-token.txt'.")
    sys.exit(1) # Используем ненулевой код выхода для ошибок
except OSError as e:
    print(f"Ошибка при чтении файла токена 'bot-token.txt': {e}")
    sys.exit(1)

if not botToken:
    print("Ошибка: Токен не найден в файле 'bot-token.txt'.")
    print("Пожалуйста, добавьте валидный токен в файл.")
    sys.exit(1)

# --- Запуск бота в асинхронном режиме ---
print("Запуск бота...")
bot = AsyncTeleBot(botToken)

# --- Администратор бота ---
ADMIN_FILE = os.path.join(os.path.dirname(__file__), 'adm.txt') # Файл, где хранится username администратора

def read_admin_username():
    """Читает username администратора из файла adm.txt."""
    admin_username = None
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'r') as f:
                admin_username = f.read().strip()
        except OSError as e:
            print(f"Ошибка чтения username администратора из {ADMIN_FILE}: {e}")
            sys.exit(1) # Выход, если файл администратора не может быть прочитан
    else:
        print(f"Ошибка: Файл {ADMIN_FILE} не найден.")
        print("Пожалуйста, создайте этот файл и поместите в него username администратора.")
        sys.exit(1) # Выход, если файл администратора отсутствует

    if not admin_username:
        print(f"Ошибка: Username администратора не найден в {ADMIN_FILE}.")
        print("Пожалуйста, добавьте username администратора в этот файл.")
        sys.exit(1) # Выход, если username администратора пуст

    return admin_username

ADMIN_USERNAME = read_admin_username() # Читаем username администратора из файла

# --- Файлы для управления пользователями и доступом ---
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.txt')
ACCESS_LOG_FILE = os.path.join(os.path.dirname(__file__), 'access.txt')

# --- Функции для работы с файлом users.txt (храним usernames) ---
def read_users_file():
    """Читает список usernames из файла users.txt."""
    users = []
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                for line in f:
                    username = line.strip()
                    if username: # Добавляем только непустые строки
                        users.append(username)
        except OSError as e:
            print(f"Ошибка чтения файла пользователей {USERS_FILE}: {e}")
            # Не выходим из программы, но список будет пуст
    return users

def write_users_file(users):
    """Записывает список usernames в файл users.txt."""
    try:
        with open(USERS_FILE, 'w') as f:
            for username in users:
                f.write(username + '\n')
    except OSError as e:
        print(f"Ошибка записи в файл пользователей {USERS_FILE}: {e}")

def add_user_to_file(username):
    """Добавляет username в файл users.txt."""
    users = read_users_file()
    if username not in users:
        users.append(username)
        write_users_file(users)
        return True
    return False

def delete_user_from_file(username):
    """Удаляет username из файла users.txt."""
    users = read_users_file()
    if username in users:
        users.remove(username)
        write_users_file(users)
        return True
    return False

def is_user_authorized(message: telebot.types.Message):
    """Проверяет, авторизован ли пользователь (есть ли его username в users.txt)."""
    authorized_users = read_users_file()
    username = message.from_user.username
    # Добавим проверку на случай, если у пользователя нет username (@...)
    if username:
        return username in authorized_users
    else:
        print(f"Предупреждение: У пользователя {message.from_user.id} ({message.from_user.first_name}) нет username.")
        return False # Пользователи без username не могут быть авторизованы по этой логике

# --- Функция для логирования доступа в access.txt (логируем usernames) ---
def log_access(message: telebot.types.Message):
    """Логирует username в access.txt, только если его там еще нет."""
    username = message.from_user.username
    if not username:
        # Не логируем пользователей без username
        return

    # Создаем файл, если его нет
    if not os.path.exists(ACCESS_LOG_FILE):
        try:
            open(ACCESS_LOG_FILE, 'a').close()
        except OSError as e:
            print(f"Ошибка создания файла лога доступа {ACCESS_LOG_FILE}: {e}")
            return # Не можем логировать, если файл не создается

    try:
        # Читаем существующие записи
        with open(ACCESS_LOG_FILE, 'r') as f:
            access_log = f.read().splitlines()

        # Добавляем, если пользователя еще нет в логе
        if username not in access_log:
            with open(ACCESS_LOG_FILE, 'a') as f: # Открываем в режиме добавления 'a'
                f.write(username + '\n')
    except OSError as e:
        print(f"Ошибка чтения/записи в файл лога доступа {ACCESS_LOG_FILE}: {e}")

# --- Функция скачивания видео (ОБНОВЛЕННАЯ ВЕРСИЯ) ---
from playwright.async_api import async_playwright
import asyncio
# ... (остальные импорты)

async def download_video_playwright(url):
    print(f"Загружаем страницу с помощью Playwright: {url}")
    video_url = None
    temp_file_path = None

    try:
        async with async_playwright() as p:
            # Можно попробовать разные браузеры (chromium, firefox, webkit)
            # headless=True - запускать без видимого окна браузера
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36') # Задаем User Agent

            try:
                # Переходим на страницу и ждем полной загрузки (включая JS)
                await page.goto(url, wait_until='networkidle', timeout=60000) # Увеличим таймаут
                print(f"Страница {url} загружена.")

                # --- Попытка найти видео URL после выполнения JS ---
                # Способ 1: Искать мета-теги снова (вдруг JS их добавил?)
                video_meta_tag_twitter = await page.query_selector('meta[name="twitter:player:stream"]')
                if video_meta_tag_twitter:
                    video_url = await video_meta_tag_twitter.get_attribute('content')
                    print(f"Найден twitter:player:stream URL: {video_url}")

                if not video_url:
                    video_meta_tag_og = await page.query_selector('meta[property="og:video"]')
                    if video_meta_tag_og:
                        video_url = await video_meta_tag_og.get_attribute('content')
                        print(f"Найден og:video URL: {video_url}")

                # Способ 2: Искать тег <video>
                if not video_url:
                    video_element = await page.query_selector('video')
                    if video_element:
                        video_url = await video_element.get_attribute('src')
                        print(f"Найден URL в теге <video>: {video_url}")
                        # Иногда URL может быть в <source> внутри <video>
                        if not video_url:
                             source_element = await video_element.query_selector('source')
                             if source_element:
                                 video_url = await source_element.get_attribute('src')
                                 print(f"Найден URL в теге <source>: {video_url}")

                # --- Если URL найден, скачиваем его (можно через aiohttp или Playwright) ---
                if video_url:
                     # Убедимся, что URL абсолютный
                     if video_url.startswith('/'):
                          parsed_original_url = urlparse(url)
                          base_url = f"{parsed_original_url.scheme}://{parsed_original_url.netloc}"
                          video_url = base_url + video_url
                     print(f"Извлеченный абсолютный URL видео: {video_url}")

                     # Скачивание через aiohttp (как раньше, но с найденным URL)
                     async with aiohttp.ClientSession() as session:
                          headers = { # Можно добавить те же заголовки
                               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
                          }
                          async with session.get(video_url, headers=headers, allow_redirects=True, timeout=300) as video_response:
                               if video_response.status == 200:
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file_obj:
                                         temp_file_path = temp_file_obj.name
                                         bytes_downloaded = 0
                                         async for chunk in video_response.content.iter_chunked(8192):
                                              if chunk:
                                                   temp_file_obj.write(chunk)
                                                   bytes_downloaded += len(chunk)
                                         print(f"Видео скачано в: {temp_file_path} ({bytes_downloaded} байт)")
                                         if bytes_downloaded == 0:
                                              print("Ошибка: Скачан пустой файл.")
                                              os.remove(temp_file_path)
                                              temp_file_path = None
                               else:
                                    print(f"Ошибка скачивания видео ({video_url}): Статус {video_response.status}")
                else:
                     print("Не удалось найти URL видео на странице после загрузки JS.")
                     # Можно сохранить HTML после JS для анализа
                     # html_after_js = await page.content()
                     # with open("debug_after_js.html", "w", encoding="utf-8") as f:
                     #     f.write(html_after_js)
                     # print("HTML после выполнения JS сохранен в debug_after_js.html")

            except Exception as e:
                print(f"Ошибка при обработке страницы Playwright: {e}")
                traceback.print_exc()
            finally:
                 await browser.close()
    except Exception as e:
        print(f"Ошибка при запуске/работе Playwright: {e}")
        traceback.print_exc()

    return temp_file_path # Возвращаем путь или None

# --- Обработчики команд бота ---

@bot.message_handler(commands=['start'])
async def start_command(message: telebot.types.Message):
    """Обработчик команды /start - приветственное сообщение."""
    log_access(message) # Логируем заход
    await bot.send_message(message.chat.id, "👋 Привет! Я бот для скачивания видео из Instagram.\n\n"
                             "Просто отправь мне ссылку на Instagram Reels, и я постараюсь его скачать и отправить тебе! 🚀")

@bot.message_handler(commands=['add', 'del', 'list'])
async def admin_commands(message: telebot.types.Message):
    """Обработчик команд администратора: /add, /del, /list."""
    # Проверяем наличие username у отправителя команды
    admin_username = message.from_user.username
    if not admin_username:
         await bot.send_message(message.chat.id, "🚫 Для использования команд администратора у вас должен быть установлен username в Telegram.")
         return

    # Проверяем права администратора
    if admin_username != ADMIN_USERNAME:
        await bot.send_message(message.chat.id, "🚫 У вас нет прав администратора для выполнения этой команды.")
        return

    # Обработка самой команды
    command_parts = message.text.split()
    command = command_parts[0].replace('/', '')

    if command == 'list':
        users = read_users_file()
        if users:
            # Форматируем список с @ перед каждым именем
            users_list_text = "\n".join([f"@{u}" for u in users])
            await bot.send_message(message.chat.id, f"👥 Список авторизованных пользователей:\n{users_list_text}")
        else:
             await bot.send_message(message.chat.id, "👥 Список авторизованных пользователей пуст.")

    elif command == 'add':
        if len(command_parts) < 2:
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите username для добавления после команды /add (например, `/add someusername`).", parse_mode='Markdown')
            return
        # Убираем возможное @ в начале имени пользователя
        username_to_add = command_parts[1].lstrip('@')
        if not username_to_add: # Проверка на пустой username после lstrip
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите корректный username для добавления.")
            return

        if add_user_to_file(username_to_add):
            await bot.send_message(message.chat.id, f"✅ Пользователь @{username_to_add} успешно добавлен.")
            print(f"Admin @{admin_username} added user @{username_to_add}") # Лог в консоль
        else:
            await bot.send_message(message.chat.id, f"⚠️ Пользователь @{username_to_add} уже есть в списке.")

    elif command == 'del':
        if len(command_parts) < 2:
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите username для удаления после команды /del (например, `/del someusername`).", parse_mode='Markdown')
            return
        # Убираем возможное @ в начале имени пользователя
        username_to_delete = command_parts[1].lstrip('@')
        if not username_to_delete: # Проверка на пустой username после lstrip
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите корректный username для удаления.")
            return

        if delete_user_from_file(username_to_delete):
            await bot.send_message(message.chat.id, f"✅ Пользователь @{username_to_delete} успешно удален.")
            print(f"Admin @{admin_username} deleted user @{username_to_delete}") # Лог в консоль
        else:
            await bot.send_message(message.chat.id, f"⚠️ Пользователь @{username_to_delete} не найден в списке.")

# --- Обработчик текстовых сообщений (основная функция бота) ---
@bot.message_handler(func=lambda message: message.text is not None and not message.text.startswith("/")) # Обработка всех текстовых сообщений, НЕ являющихся командами
async def make_some(message: telebot.types.Message):
    """Обработчик текстовых сообщений, включая проверку на ссылку Reel и ответ на любой другой текст."""

    # Проверка на ссылку Reel (более гибкая)
    text = message.text.strip() # Убираем пробелы по краям
    if "instagram.com/reel/" in text:
        # Извлекаем URL, даже если в сообщении есть лишний текст
        # Простой способ: ищем первое вхождение https://...instagram.com/reel/...
        url_start_index = text.find("https://www.instagram.com/reel/")
        if url_start_index == -1:
             url_start_index = text.find("https://instagram.com/reel/") # Без www

        if url_start_index != -1:
            # Находим конец URL (пробел, перенос строки или конец строки)
            url_end_index = len(text)
            for char in [' ', '\n', '\t']:
                found_index = text.find(char, url_start_index)
                if found_index != -1:
                    url_end_index = min(url_end_index, found_index)
            instagram_url = text[url_start_index:url_end_index]
            print(f"Извлечен URL: {instagram_url}")
        else:
            # Если не нашли по https, может быть без него? Маловероятно, но для полноты
            if text.startswith("instagram.com/reel/") or text.startswith("www.instagram.com/reel/"):
                 instagram_url = "https://" + text.split()[0] # Берем первое слово
                 print(f"Извлечен URL (без https): {instagram_url}")
            else:
                 await bot.send_message(message.chat.id, "🤔 Не смог точно распознать ссылку на Instagram Reel в вашем сообщении.")
                 return # Выходим, если URL не извлечен

        # --- Проверка авторизации ---
        if not is_user_authorized(message):
            # Получаем username администратора для сообщения
            admin_contact = f"@{ADMIN_USERNAME}" if ADMIN_USERNAME else "администратору"
            await bot.send_message(message.chat.id, f"🔒 Извините, у вас нет доступа к этому боту.\n\n"
                                     f"Обратитесь к {admin_contact}, чтобы получить разрешение на использование.")
            # Дополнительно логируем попытку неавторизованного доступа
            user_info = f"user_id={message.from_user.id}"
            if message.from_user.username:
                user_info += f", username=@{message.from_user.username}"
            print(f"Неавторизованная попытка доступа от {user_info} со ссылкой: {instagram_url}")
            return

        log_access(message) # Логируем успешный авторизованный доступ

        # --- Процесс скачивания ---
        ddinstagram_url = instagram_url.replace("instagram.com", "ddinstagram.com")
        # Убираем параметры типа ?igsh=... , так как ddinstagram может их не любить
        ddinstagram_url = ddinstagram_url.split('?')[0]
        print(f"ddinstagram URL для обработки: {ddinstagram_url}")

        # Отправляем сообщение о начале скачивания
        processing_message = await bot.send_message(message.chat.id, "⏳ Ищу и скачиваю видео... Пожалуйста, подождите.")

        video_path = await download_video_playwright(ddinstagram_url)

        # Удаляем сообщение "Скачиваю..."
        try:
            await bot.delete_message(message.chat.id, processing_message.message_id)
        except Exception as e:
            print(f"Не удалось удалить сообщение о статусе: {e}") # Не критично, просто логируем

        # --- Отправка видео или сообщения об ошибке ---
        if video_path:
            try:
                file_size = os.path.getsize(video_path)
                print(f"Размер скачанного файла: {file_size} байт")

                # Отправляем видео как файл
                # Используем try-except для отправки, чтобы поймать возможные ошибки Telegram API
                try:
                    await bot.send_chat_action(message.chat.id, 'upload_video') # Показываем статус "отправка видео"
                    with open(video_path, 'rb') as video_file:
                        # Добавляем подпись к видео с оригинальной ссылкой
                        #caption_text = f"Видео из: {instagram_url}"
                        await bot.send_video(message.chat.id, video_file, timeout=60) # Увеличим таймаут на отправку
                    print("Видео успешно отправлено.")
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Ошибка Telegram API при отправке видео: {e}")
                    # Проверяем на специфичную ошибку размера файла (лимит Telegram 50 МБ для ботов)
                    if "file is too big" in str(e).lower() or e.error_code == 400:
                         await bot.send_message(message.chat.id, f"😔 Видео скачано, но оно слишком большое для отправки через Telegram (больше 50 МБ).\nРазмер файла: {file_size / (1024*1024):.2f} МБ")
                    else:
                         await bot.send_message(message.chat.id, f"Не удалось отправить видео. Ошибка Telegram: {e}")
                except Exception as e_send:
                    print(f"Неожиданная ошибка при отправке видео: {e_send}")
                    await bot.send_message(message.chat.id, f"Произошла неожиданная ошибка при отправке видео.")

            finally: # Блок finally выполнится в любом случае после try (даже если была ошибка)
                # Удаляем временный файл после попытки отправки
                if os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                        print(f"Временный файл {video_path} удален.")
                    except OSError as e:
                        print(f"Ошибка удаления временного файла {video_path}: {e}")
        else:
             # Если download_video вернул None
             await bot.send_message(message.chat.id, "😔 Не удалось скачать видео с этой ссылки. Возможно, ссылка недействительна, видео удалено или сайт ddinstagram временно недоступен.")

    # Обработка других ссылок Instagram (не Reels)
    elif "instagram.com/" in text:
        await bot.send_message(message.chat.id, "⚠️ Похоже, это ссылка на Instagram, но не на Reel.\n"
                                 "Я умею скачивать только видео из раздела Reels (ссылки вида `https://www.instagram.com/reel/...`).")

    # Обработка любого другого текста
    else:
        await bot.send_message(message.chat.id, "🤔 Чтобы я скачал видео, отправь мне, пожалуйста, ссылку на Instagram Reel.")


# --- Запуск бота ---
if __name__ == '__main__':
    try:
        print("Бот запущен и готов к работе.")
        # Используем asyncio.run() для запуска асинхронной функции polling
        asyncio.run(bot.polling(non_stop=True, skip_pending=True)) # non_stop для перезапуска при ошибках, skip_pending чтобы не обрабатывать старые сообщения
    except Exception as e:
        print(f"Критическая ошибка при запуске или работе бота: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("Бот остановлен.")
