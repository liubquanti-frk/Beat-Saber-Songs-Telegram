import os
import logging
import zipfile
import requests
import asyncio
import json
import base64
from aiogram import Bot, Dispatcher, types
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
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
    if not match:
        await message.reply("Введіть коректний ID або посилання на мапу.")
        return
    map_id = match.group(1)
    await message.reply("Завантаження...")
    loop = asyncio.get_event_loop()
    user_id = message.from_user.id
    user_title = (message.from_user.first_name or "")
    if message.from_user.last_name:
        user_title += f" {message.from_user.last_name}"
    # Get avatar (profile photo)
    user_avatar_b64 = ""
    try:
        photos = await message.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file = await message.bot.get_file(file_id)
            # Download file bytes via Telegram API
            file_bytes = await message.bot.download_file(file.file_path)
            # file_bytes is a BufferedReader, read all
            content = file_bytes.read()
            b64 = base64.b64encode(content).decode()
            user_avatar_b64 = f"base64,{b64}"
    except Exception:
        pass
    result = await loop.run_in_executor(None, download_and_extract_map_and_update_playlist, map_id, user_id, user_title.strip(), user_avatar_b64)
    await message.reply(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
