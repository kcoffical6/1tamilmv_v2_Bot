import os
import time
from dotenv import load_dotenv
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import logging
import threading
try:
    from tamilmvbot.hotstar_handler import HotstarMonitor
except ImportError:
    from hotstar_handler import HotstarMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
# ============ WOODctaft =================
TOKEN = os.getenv('TOKEN', '5497255628:AAEwBfKmLKJIb5O_MKy8fEVgxyOk19-WkJs')
TAMILMV_URL = os.getenv('TAMILMV_URL', 'https://www.1tamilmv.fi')
# ========================================
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Initialize Hotstar Monitor
hotstar_monitor = HotstarMonitor()

# Global variables
movie_list = []
real_dict = {}

# /start command


@bot.message_handler(commands=['start'])
def random_answer(message):
    text_message = """<b>Hello 👋</b>

<blockquote><b>🎬 Get latest Movies from 1Tamilmv</b></blockquote>

⚙️ <b>How to use me??</b> 🤔

✯ Please enter /view command and you'll get magnet link as well as link to torrent file 😌

<blockquote><b>🔗 Share and Support 💝</b></blockquote>"""

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            '🔗 GitHub 🔗',
            url='https://github.com/SudoR2spr'),
        types.InlineKeyboardButton(
            text="⚡ Powered By",
            url='https://t.me/Opleech_WD'))

    bot.send_photo(
        chat_id=message.chat.id,
        photo='https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg',
        caption=text_message,
        reply_markup=keyboard
    )

@bot.message_handler(commands=['monitor'])
def monitor_handler(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Usage: /monitor <hotstar_url>\nExample: /monitor https://www.hotstar.com/in/shows/show-name/12345")
            return

        url = args[1]
        success, response = hotstar_monitor.add_show(message.chat.id, url)
        bot.reply_to(message, response)
    except Exception as e:
        logger.error(f"Monitor command error: {e}")
        bot.reply_to(message, "❌ An error occurred processing your request.")

def run_monitor_loop():
    logger.info("Starting Hotstar monitor loop")
    while True:
        try:
            hotstar_monitor.check_updates(bot)
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        time.sleep(600) # Check every 10 minutes

# /view command


@bot.message_handler(commands=['view'])
def start(message):
    bot.send_message(message.chat.id, "<b>🧲 Please wait for 10 ⏰ seconds</b>")
    global movie_list, real_dict
    movie_list, real_dict = tamilmv()

    combined_caption = """<b><blockquote>🔗 Select a Movie from the list 🎬</blockquote></b>\n\n🔘 Please select a movie:"""
    keyboard = makeKeyboard(movie_list)

    bot.send_photo(
        chat_id=message.chat.id,
        photo='https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg',
        caption=combined_caption,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global real_dict
    for key, value in enumerate(movie_list):
        if call.data == f"{key}":
            if value in real_dict.keys():
                for i in real_dict[value]:
                    bot.send_message(call.message.chat.id, text=i)


def makeKeyboard(movie_list):
    markup = types.InlineKeyboardMarkup()
    for key, value in enumerate(movie_list):
        markup.add(
            types.InlineKeyboardButton(
                text=value,
                callback_data=f"{key}"))
    return markup


def tamilmv():
    mainUrl = TAMILMV_URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    movie_list = []
    real_dict = {}

    try:
        web = requests.get(mainUrl, headers=headers)
        web.raise_for_status()
        soup = BeautifulSoup(web.text, 'lxml')

        temps = soup.find_all('div', {'class': 'ipsType_break ipsContained'})

        if len(temps) < 15:
            logger.warning("Not enough movies found on the page")
            return [], {}

        for i in range(15):
            title = temps[i].findAll('a')[0].text.strip()
            link = temps[i].find('a')['href']
            movie_list.append(title)

            movie_details = get_movie_details(link)
            real_dict[title] = movie_details

        return movie_list, real_dict
    except Exception as e:
        logger.error(f"Error in tamilmv function: {e}")
        return [], {}


def get_movie_details(url):
    try:
        html = requests.get(url, timeout=15)
        html.raise_for_status()
        soup = BeautifulSoup(html.text, 'lxml')

        mag = [a['href'] for a in soup.find_all(
            'a', href=True) if 'magnet:' in a['href']]
        filelink = [a['href'] for a in soup.find_all(
            'a', {"data-fileext": "torrent", 'href': True})]

        movie_details = []
        movie_title = soup.find('h1').text.strip(
        ) if soup.find('h1') else "Unknown Title"

        for p in range(len(mag)):
            torrent_link = filelink[p] if p < len(filelink) else None
            if torrent_link and not torrent_link.startswith('http'):
                torrent_link = f'{TAMILMV_URL}{torrent_link}'

            message = f"""
<b>📂 Movie Title:</b>
<blockquote>{movie_title}</blockquote>

🧲 <b>Magnet Link:</b>
<pre>{mag[p]}</pre>
"""
            if torrent_link:
                message += f"""
📥 <b>Download Torrent:</b>
<a href="{torrent_link}">🔗 Click Here</a>
"""
            else:
                message += """
📥 <b>Torrent File:</b> Not Available
"""

            movie_details.append(message)

        return movie_details
    except Exception as e:
        logger.error(f"Error retrieving movie details: {e}")
        return []


if __name__ == "__main__":
    # Start monitor thread
    monitor_thread = threading.Thread(target=run_monitor_loop, daemon=True)
    monitor_thread.start()

    # Remove any previous webhook
    bot.remove_webhook()
    time.sleep(1)

    # Start polling
    logger.info("Starting bot polling...")
    bot.infinity_polling()
