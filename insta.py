import telebot
import os
from telebot.async_telebot import AsyncTeleBot
import asyncio
import sys
import aiohttp
import tempfile
import shutil
from bs4 import BeautifulSoup

# Чтение токена бота из файла
try:
    with open('bot-token.txt', 'r') as file:
        botToken = file.read().replace('\n', '')
except OSError as e:
    print ("Error while reading bot token from bot-token.txt file. Please re-create image with this file.")
    sys.exit()

if not botToken:
    print ("No token is read from bot-token.txt file. Please re-create docker image with valid file content.")
    sys.exit()

# Запуск бота в асинхронном режиме
print ("Запуск бота...")
bot = AsyncTeleBot(botToken)

# --- Администратор бота ---
ADMIN_FILE = 'adm.txt' # Файл, где хранится username администратора

def read_admin_username():
    """Читает username администратора из файла adm.txt."""
    admin_username = None
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'r') as f:
                admin_username = f.read().strip()
        except OSError as e:
            print(f"Error reading admin username from {ADMIN_FILE}: {e}")
            sys.exit() # Exit if admin file cannot be read
    else:
        print(f"Error: {ADMIN_FILE} file not found. Please create this file and put the admin username inside.")
        sys.exit() # Exit if admin file is missing

    if not admin_username:
        print(f"Error: No admin username found in {ADMIN_FILE}. Please add the admin username to this file.")
        sys.exit() # Exit if admin username is empty

    return admin_username

ADMIN_USERNAME = read_admin_username() # Читаем username администратора из файла

# --- Файлы для управления пользователями и доступом ---
USERS_FILE = 'users.txt'
ACCESS_LOG_FILE = 'access.txt'

# --- Функции для работы с файлом users.txt (храним usernames) ---
def read_users_file():
    """Читает список usernames из файла users.txt."""
    users = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            for line in f:
                username = line.strip()
                if username:
                    users.append(username)
    return users

def write_users_file(users):
    """Записывает список usernames в файл users.txt."""
    with open(USERS_FILE, 'w') as f:
        for username in users:
            f.write(username + '\n')

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
    if username:
        return username in authorized_users
    return False

# --- Функция для логирования доступа в access.txt (логируем usernames) ---
def log_access(message: telebot.types.Message):
    """Логирует username в access.txt, только если его там еще нет."""
    username = message.from_user.username
    if not username:
        return

    if not os.path.exists(ACCESS_LOG_FILE):
        open(ACCESS_LOG_FILE, 'a').close()

    with open(ACCESS_LOG_FILE, 'r+') as f:
        access_log = f.read().splitlines()
        if username not in access_log:
            f.write(username + '\n')

# --- Функция скачивания видео (без изменений) ---
async def download_video(url):
    """Асинхронная функция для скачивания видео по URL."""
    print(f"Downloading video info from: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                print(f"Info response status: {response.status}")
                print(f"Info response headers: {response.headers}")
                if response.status == 200:
                    html_content = await response.text()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    video_meta_tag = soup.find('meta', attrs={'name': 'twitter:player:stream'})
                    if video_meta_tag:
                        video_url = video_meta_tag.get('content')
                        print(f"Video URL found in twitter:player:stream meta tag: {video_url}")
                    else:
                        video_meta_tag = soup.find('meta', attrs={'property': 'og:video'})
                        if video_meta_tag:
                            video_url = video_meta_tag.get('content')
                            print(f"Video URL found in og:video meta tag: {video_url}")
                        else:
                            print("Video URL not found in HTML meta tags.")
                            return None
                    if not video_url:
                        print("Video URL extraction failed.")
                        return None
                    absolute_video_url = "https://ddinstagram.com" + video_url
                    print(f"Starting video download from extracted absolute URL: {absolute_video_url}")
                    async with session.get(absolute_video_url) as video_response:
                        print(f"Video download status: {video_response.status}")
                        if video_response.status == 200:
                            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                            with open(temp_file.name, 'wb') as f:
                                while True:
                                    chunk = await video_response.content.read(1024)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                            print(f"Video downloaded to: {temp_file.name}")
                            return temp_file.name
                        else:
                            print(f"Error downloading video from URL {absolute_video_url}: Status code {video_response.status}")
                            return None
                else:
                    print(f"Error getting info from {url}: Status code {response.status}")
                    return None
    except Exception as e:
        print(f"Error during video download process: {e}")
        return None

# --- Обработчики команд бота ---

@bot.message_handler(commands=['start'])
async def start_command(message: telebot.types.Message):
    """Обработчик команды /start - приветственное сообщение."""
    log_access(message)
    await bot.send_message(message.chat.id, "👋 Привет! Я бот для скачивания видео из Instagram.\n\n"
                             "Просто отправь мне ссылку на Instagram Reels, и я постараюсь его скачать и отправить тебе! 🚀")

@bot.message_handler(commands=['add', 'del', 'list'])
async def admin_commands(message: telebot.types.Message):
    """Обработчик команд администратора: /add, /del, /list."""
    command = message.text.split()[0].replace('/', '')
    admin_username = message.from_user.username

    if admin_username != ADMIN_USERNAME:
        await bot.send_message(message.chat.id, "🚫 У вас нет прав администратора для выполнения этой команды.")
        return

    if command == 'list':
        users = read_users_file()
        users_list_text = "\n".join([f"@{u}" for u in users]) if users else "Список пользователей пуст."
        await bot.send_message(message.chat.id, f"👥 Список авторизованных пользователей:\n{users_list_text}")

    elif command == 'add':
        if len(message.text.split()) < 2:
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите username для добавления после команды /add (например, /add username).")
            return
        username_to_add = message.text.split()[1]
        if add_user_to_file(username_to_add):
            await bot.send_message(message.chat.id, f"✅ Пользователь @{username_to_add} успешно добавлен.")
        else:
            await bot.send_message(message.chat.id, f"⚠️ Пользователь @{username_to_add} уже есть в списке.")

    elif command == 'del':
        if len(message.text.split()) < 2:
            await bot.send_message(message.chat.id, "⚠️ Пожалуйста, укажите username для удаления после команды /del (например, /del username).")
            return
        username_to_delete = message.text.split()[1]
        if delete_user_from_file(username_to_delete):
            await bot.send_message(message.chat.id, f"✅ Пользователь @{username_to_delete} успешно удален.")
        else:
            await bot.send_message(message.chat.id, f"⚠️ Пользователь @{username_to_delete} не найден в списке.")

# --- Обработчик текстовых сообщений (основная функция бота) ---
@bot.message_handler(func=lambda message: message.text is not None and not message.text.startswith("/")) # Handle all text messages that are NOT commands
async def make_some(message: telebot.types.Message):
    """Обработчик текстовых сообщений, включая проверку на ссылку Reel и ответ на любой другой текст."""

    if message.text.startswith("https://www.instagram.com/reel/"): # Проверка на Reel link
        if not is_user_authorized(message):
            await bot.send_message(message.chat.id, "🔒 Извините, у вас нет доступа к этому боту.\n\n"
                                     "Обратитесь к администратору, чтобы получить разрешение на использование.")
            return

        log_access(message)

        instagram_url = message.text
        ddinstagram_url = instagram_url.replace("https://www.instagram.com", "https://ddinstagram.com")
        print(f"ddinstagram URL: {ddinstagram_url}")

        await bot.send_message(message.chat.id, "Скачиваю Instagram Reels...")

        video_path = await download_video(ddinstagram_url)

        if video_path:
            try:
                file_size = os.path.getsize(video_path)
                print(f"Downloaded file size: {file_size} bytes")
                if file_size == 0:
                    print("Warning: Downloaded file is empty!")
                    await bot.send_message(message.chat.id, "Ошибка: Скачанный файл оказался пустым.")
                else:
                    with open(video_path, 'rb') as video_file:
                        await bot.send_video(message.chat.id, video_file)
                    print("Video sent successfully.")
            except Exception as e:
                await bot.send_message(message.chat.id, f"Не удалось отправить видео. Ошибка: {e}")
            finally:
                # Удаляем временный файл после отправки
                try:
                    os.remove(video_path)
                    print(f"Temporary file {video_path} deleted.")
                except OSError as e:
                    print(f"Error deleting temporary file {video_path}: {e}")

        else:
            await bot.send_message(message.chat.id, "Не удалось скачать видео с ddinstagram.")
    elif message.text.startswith("https://www.instagram.com"): # Если начинается с instagram.com, но не reel
        await bot.send_message(message.chat.id, "⚠️ Пожалуйста, отправьте ссылку на Instagram Reel (например, https://www.instagram.com/reel/YourReelID/).\n"
                                 "Ссылки на другие типы постов не поддерживаются.")
    else: # Handle ANY other text message
        await bot.send_message(message.chat.id, "🤔 Похоже, это не ссылка на Instagram Reel. "
                                 "Отправьте мне, пожалуйста, ссылку на Instagram Reels, чтобы я мог скачать видео.")

asyncio.run(bot.polling())