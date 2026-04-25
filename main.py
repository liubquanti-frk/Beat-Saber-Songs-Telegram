import os
import logging
import zipfile
import requests
import asyncio
import json
import base64
import urllib.parse
from aiogram import Bot, Dispatcher, types
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from dotenv import load_dotenv

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GAME_ROOT = os.getenv("GAME_ROOT")
CUSTOM_LEVELS = os.path.join(GAME_ROOT, "Beat Saber_Data", "CustomLevels")


logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# /start handler
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Відправте ID або посилання на мапу Beat Saver для завантаження.")

# Download and extract map, then update playlist
def download_and_extract_map_and_update_playlist(map_id: str, user_id: int, user_title: str, user_avatar_b64: str = "") -> str:
    api_url = f"https://api.beatsaver.com/maps/id/{map_id}"
    resp = requests.get(api_url)
    if resp.status_code != 200:
        return "Мапу не знайдено."
    data = resp.json()

    version = data['versions'][0]
    download_url = version['downloadURL']
    song_hash = version['hash']
    levelid = f"custom_level_{song_hash.upper()}"
    song_name = data.get('metadata', {}).get('songName') or data.get('name', map_id)
    song_author = data.get('metadata', {}).get('songAuthorName', '')
    cover_url = version.get('coverURL', '')

    # Download and extract
    os.makedirs(CUSTOM_LEVELS, exist_ok=True)
    zip_path = os.path.join(CUSTOM_LEVELS, f"{map_id}.zip")
    zip_resp = requests.get(download_url)
    if zip_resp.status_code != 200:
        return "Не вдалося завантажити архів."
    with open(zip_path, "wb") as f:
        f.write(zip_resp.content)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(os.path.join(CUSTOM_LEVELS, map_id))
    os.remove(zip_path)

    # Update playlist
    playlist_dir = os.path.join(GAME_ROOT, "Playlists", "Telegram")
    os.makedirs(playlist_dir, exist_ok=True)
    playlist_path = os.path.join(playlist_dir, f"{user_id}.bplist")
    playlist = {
        "playlistTitle": user_title,
        "playlistAuthor": str(user_id),
        "playlistDescription": "",
        "songs": [],
        "image": user_avatar_b64 or ""
    }
    # Try to load existing playlist
    if os.path.exists(playlist_path):
        try:
            with open(playlist_path, "r", encoding="utf-8") as f:
                playlist = json.load(f)
            # Update title/author/image if changed
            playlist["playlistTitle"] = user_title
            playlist["playlistAuthor"] = str(user_id)
            if user_avatar_b64:
                playlist["image"] = user_avatar_b64
        except Exception:
            pass
    # Add song if not present
    if not any(s.get("hash", "").upper() == song_hash.upper() for s in playlist["songs"]):
        song_entry = {
            "songName": song_name,
            "hash": song_hash.upper(),
            "levelid": levelid
        }
        if song_author:
            song_entry["songAuthorName"] = song_author
        if cover_url:
            song_entry["coverURL"] = cover_url
        playlist["songs"].append(song_entry)
        with open(playlist_path, "w", encoding="utf-8") as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)
    return f"Мапу {map_id} завантажено і додано до плейлісту {user_title}!"



# Handler for map id/url

@router.message()
async def handle_map(message: Message):
    text = message.text.strip()
    import re
    match = re.search(r"([0-9a-fA-F]{1,6})$", text)
    if match:
        map_id = match.group(1)
        await process_download(message, map_id)
        return
    # Якщо не ID/URL — пошук
    await message.reply("Виконую пошук...")
    page = 0
    page_size = 10
    await send_search_results(message, text, page, page_size)

# Відправка результатів пошуку з пагінацією
async def send_search_results(message_or_cb, query, page, page_size):
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://api.beatsaver.com/search/text/{page}?q={encoded_query}&pageSize={page_size}"
    resp = requests.get(search_url)
    if resp.status_code != 200:
        await message_or_cb.reply("Помилка пошуку на Beat Saver.")
        return
    data = resp.json()
    docs = data.get('docs', [])
    if not docs:
        await message_or_cb.reply("Нічого не знайдено.")
        return
    keyboard = []
    for doc in docs:
        title = doc.get('name', 'Без назви')
        author = doc.get('metadata', {}).get('songAuthorName', '')
        btn_text = f"{title} — {author}" if author else title
        is_verified = False
        if 'uploader' in doc and isinstance(doc['uploader'], dict):
            is_verified = doc['uploader'].get('verifiedMapper', False)
        is_ranked = doc.get('ranked', False) or doc.get('blRanked', False)
        if is_ranked:
            btn_text = "🎖️ " + btn_text
        elif is_verified:
            btn_text = "✅ " + btn_text
        # Кодуємо query для callback_data
        encoded_query = urllib.parse.quote(query)
        keyboard.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"select_{doc['id']}_{page}_{encoded_query}"
            )
        ])
    # Пагінація
    nav_buttons = []
    encoded_query = urllib.parse.quote(query)
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}_{encoded_query}"))
    nav_buttons.append(InlineKeyboardButton(text=f"Сторінка {page+1}", callback_data="noop"))
    if len(docs) == page_size:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{page+1}_{encoded_query}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text_msg = "Оберіть мапу:" if isinstance(message_or_cb, Message) else "Оберіть мапу (оновлено):"
    if isinstance(message_or_cb, Message):
        await message_or_cb.reply(text_msg, reply_markup=markup)
    else:
        await message_or_cb.message.edit_text(text_msg, reply_markup=markup)

# Callback handler для вибору мапи з пошуку

# Callback handler для вибору мапи з пошуку та пагінації
@router.callback_query()
async def handle_callback(callback: CallbackQuery):
    if callback.data.startswith("select_"):
        # select_{mapid}_{page}_{query}
        parts = callback.data.split('_', 3)
        map_id = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        query = urllib.parse.unquote(parts[3]) if len(parts) > 3 else ""
        # Отримуємо деталі мапи
        api_url = f"https://api.beatsaver.com/maps/id/{map_id}"
        resp = requests.get(api_url)
        if resp.status_code != 200:
            await callback.message.edit_text("Мапу не знайдено.")
            await callback.answer()
            return
        data = resp.json()
        version = data['versions'][0]
        title = data.get('name', map_id)
        author = data.get('metadata', {}).get('songAuthorName', '')
        level_author = data.get('metadata', {}).get('levelAuthorName', '')
        bpm = data.get('metadata', {}).get('bpm', '')
        duration = data.get('metadata', {}).get('duration', '')
        ranked = data.get('ranked', False) or data.get('blRanked', False)
        verified = data.get('uploader', {}).get('verifiedMapper', False)
        cover = version.get('coverURL', '')
        desc = data.get('description', '')
        info = f"<b>{title}</b>\n"
        if author:
            info += f"Автор: {author}\n"
        if level_author:
            info += f"Маппер: {level_author}\n"
        if bpm:
            info += f"BPM: {bpm}\n"
        if duration:
            mins = int(duration) // 60
            secs = int(duration) % 60
            info += f"Тривалість: {mins}:{secs:02d}\n"
        if ranked:
            info += "<b>Ranked</b>\n"
        if verified:
            info += "<b>Verified Mapper</b>\n"
        if desc:
            info += f"\n{desc}"
        # Кнопки: Повернутися, Завантажити
        # Тепер backto_{page}_{query}
        encoded_query = urllib.parse.quote(query)
        back_data = f"backto_{page}_{encoded_query}"
        confirm_data = f"confirm_{map_id}_{callback.message.message_id}"
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⬅️ Повернутися", callback_data=back_data),
                    InlineKeyboardButton(text="Завантажити ✅", callback_data=confirm_data)
                ]
            ]
        )
        if cover:
            await callback.message.edit_text(info, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=False)
        else:
            await callback.message.edit_text(info, reply_markup=markup, parse_mode="HTML")
        await callback.answer()
    elif callback.data.startswith("backto_"):
        # Повернення до попереднього пошуку (оновити список)
        # Витягуємо query з тексту повідомлення (заголовок)
        # Для простоти: зберігаємо query у callback.message.reply_to_message.text або у callback.message.text
        # Але краще зберігати у callback.message.reply_markup, але Telegram не дає цього напряму
        # Тому збережемо query у callback.message.text після "Оберіть мапу: ..."
        # Або зберігати у callback.data, але тут message_id
        # Для простоти: повертаємо на першу сторінку з останнім текстом пошуку
        orig_text = callback.message.text
        # Витягуємо query з callback.message.reply_to_message, якщо є
        # Якщо ні — просимо користувача повторити пошук
        # (Можна зберігати query у callback.data, але це обмеження callback_data)
        # Тому просто оновлюємо на "Оберіть мапу:"
        await callback.message.edit_text("Оберіть мапу:")
        await callback.answer()
    elif callback.data.startswith("confirm_"):
        # confirm_{map_id}_{message_id}
        parts = callback.data.split("_", 2)
        map_id = parts[1]
        await callback.message.edit_text("Завантаження...")
        await process_download(callback.message, map_id, callback.from_user)
        await callback.answer()
    elif callback.data.startswith("backto_"):
        # backto_{page}_{query}
        parts = callback.data.split('_', 2)
        page = int(parts[1]) if len(parts) > 1 else 0
        query = urllib.parse.unquote(parts[2]) if len(parts) > 2 else ""
        await send_search_results(callback, query, page, 10)
        await callback.answer()
    elif callback.data.startswith("page_"):
        # page_{page}_{query}
        parts = callback.data.split('_', 2)
        page = int(parts[1]) if len(parts) > 1 else 0
        query = urllib.parse.unquote(parts[2]) if len(parts) > 2 else ""
        await send_search_results(callback, query, page, 10)
        await callback.answer()

# Винесена функція для завантаження та додавання до плейліста
async def process_download(message, map_id, user_obj=None):
    loop = asyncio.get_event_loop()
    user = user_obj or message.from_user
    user_id = user.id
    user_title = (user.first_name or "")
    if getattr(user, "last_name", None):
        user_title += f" {user.last_name}"
    user_avatar_b64 = ""
    try:
        photos = await message.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file = await message.bot.get_file(file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            content = file_bytes.read()
            b64 = base64.b64encode(content).decode()
            user_avatar_b64 = f"base64,{b64}"
    except Exception:
        pass
    result = await loop.run_in_executor(None, download_and_extract_map_and_update_playlist, map_id, user_id, user_title.strip(), user_avatar_b64)
    await message.answer(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
