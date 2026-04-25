# Beat Saber Songs Telegram

Цей бот дозволяє завантажувати пісні для Beat Saber через Telegram та автоматично додавати їх у плейліст користувача з аватаром.

## Вимоги

- Python 3.10+
- Beat Saber встановлений на ПК

## Встановлення

1. Клонувати репозиторій:

   ```sh
   git clone https://github.com/liubquanti-frk/Beat-Saber-Songs-Telegram.git
   cd Beat-Saber-Songs-Telegram
   ```
2. Встановити залежності:

   ```sh
   pip install -r requirements.txt
   ```
3. Створити файл `.env` у корені проекту та додати:

   ```env
   BOT_TOKEN=ваш_токен_бота
   GAME_ROOT=шлях_до_кореня_гри_Beat_Saber
   ```

   Наприклад:

   ```env
   BOT_TOKEN=123456789:ABC...xyz
   GAME_ROOT=D:\Games\Beat Saber
   ```
4. Запустити бота:

   ```sh
   python main.py
   ```

## Використання

- Відправте боту ID або посилання на мапу з Beat Saver.
- Мапа буде завантажена у папку Beat Saber_Data/CustomLevels/.
- Пісня автоматично додасться у ваш Telegram-плейліст (Playlists/Telegram/ВАШ_ID.bplist) з вашим ім'ям та аватаром.

## Особливості

- Підтримка декількох користувачів (окремий плейліст для кожного).
- Плейліст містить ім'я, id та аватар користувача.
- Пісні не дублюються у плейлісті.
