import json
import os
import time
import requests
import threading
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class HotstarMonitor:
    def __init__(self, data_file='hotstar_subs.json'):
        self.data_file = data_file
        self.subscriptions = self.load_data()
        self.lock = threading.Lock()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading hotstar data: {e}")
        return {}

    def save_data(self):
        with self.lock:
            try:
                with open(self.data_file, 'w') as f:
                    json.dump(self.subscriptions, f, indent=4)
            except Exception as e:
                logger.error(f"Error saving hotstar data: {e}")

    def add_show(self, chat_id, url):
        chat_id = str(chat_id)

        # Basic validation
        if "hotstar.com" not in url:
            return False, "Invalid URL. Please provide a valid Hotstar show URL."

        if url in self.subscriptions:
            if chat_id not in self.subscriptions[url]['subscribers']:
                self.subscriptions[url]['subscribers'].append(chat_id)
                self.save_data()
                return True, "Added to existing monitor list."
            else:
                return False, "You are already monitoring this show."

        # Initial scrape to get current state
        episodes = self.scrape_episodes(url)

        # If scrape fails, we shouldn't start with empty list as it might cause spam later
        known_episodes = []
        status_msg = ""

        if episodes is None:
             logger.warning(f"Initial scrape failed for {url}")
             # We initialize with empty, but the first successful scrape will define 'known'
             # without notifying to prevent spam.
             # We use a flag 'initialized': False to handle this.
             known_episodes = []
             status_msg = "Warning: Could not fetch current episodes. Will try again later."
        else:
             known_episodes = [e['id'] for e in episodes]
             status_msg = f"Found {len(episodes)} existing episodes."

        self.subscriptions[url] = {
            'subscribers': [chat_id],
            'known_episodes': known_episodes,
            'last_check': time.time(),
            'title': self.extract_title(url),
            'initialized': (episodes is not None)
        }
        self.save_data()
        return True, f"Started monitoring. {status_msg}"

    def extract_title(self, url):
        # unexpected format: https://www.hotstar.com/in/shows/bhargavi-ll-b/1271396039/
        try:
            parts = url.strip('/').split('/')
            if 'shows' in parts:
                idx = parts.index('shows')
                if len(parts) > idx + 1:
                    return parts[idx+1].replace('-', ' ').title()
        except:
            pass
        return "Unknown Show"

    def scrape_episodes(self, url):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, 'lxml')

            episodes = []

            # Strategy 1: Look for JSON state (removed dead code)
            # We rely on Strategy 2 (HTML parsing) as it covers the requirement for SSR links.

            # Strategy 2: Improved HTML parsing
            # We look for any anchor that links to an episode
            # Episode structure: .../episode-name/id/watch

            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']

                # Check for 'watch' or digit pattern
                if 'watch' in href or (href.split('/')[-1].isdigit() and len(href.split('/')[-1]) > 5):
                     # Construct full URL
                     full_link = href if href.startswith('http') else f"https://www.hotstar.com{href}"

                     # Extract ID
                     parts = full_link.strip('/').split('/')
                     ep_id = parts[-1]
                     if ep_id == 'watch' and len(parts) > 1:
                         ep_id = parts[-2]

                     # Filter out short IDs (likely not episodes)
                     if not ep_id.isdigit() or len(ep_id) < 8:
                         continue

                     # Basic title extraction
                     title = link.get_text(strip=True)
                     if not title:
                         # Try to get title from URL slug
                         # .../arjuns-support-for-bhargavi/1641016181/watch
                         # Slug is usually parts[-3] if ID is -2
                         try:
                             if len(parts) >= 3:
                                 slug = parts[-3]
                                 if slug != 'shows':
                                     title = slug.replace('-', ' ').title()
                         except:
                             pass

                     if not title:
                         title = f"Episode {ep_id}"

                     episodes.append({
                         'id': ep_id,
                         'link': full_link,
                         'title': title
                     })

            # Deduplicate by ID
            unique_episodes = {e['id']: e for e in episodes}.values()
            return list(unique_episodes)

        except Exception as e:
            logger.error(f"Scraping error for {url}: {e}")
            return None

    def check_updates(self, bot_instance):
        """
        Iterate through subscriptions and check for new episodes.
        """
        notifications = []

        for url, data in self.subscriptions.items():
            current_episodes = self.scrape_episodes(url)

            # Use 'initialized' flag to prevent spam on first successful scrape after a failure
            initialized = data.get('initialized', True)

            if current_episodes:
                known_ids = set(data['known_episodes'])
                new_episodes = [e for e in current_episodes if e['id'] not in known_ids]

                if new_episodes:
                    # Update known episodes
                    for ep in new_episodes:
                        data['known_episodes'].append(ep['id'])

                    # Only notify if we were already initialized.
                    # If this is the first successful scrape (and we weren't initialized),
                    # we just silently update the known list to avoid spamming "all existing episodes".
                    if initialized:
                        # Prepare notifications
                        for subscriber in data['subscribers']:
                            for ep in new_episodes:
                                notifications.append({
                                    'chat_id': subscriber,
                                    'text': f"🎬 <b>New Episode Detected!</b>\n\n<b>Show:</b> {data['title']}\n<b>Episode:</b> {ep['title']}\n\n🔗 {ep['link']}"
                                })
                        logger.info(f"Found {len(new_episodes)} new episodes for {url}")
                    else:
                         logger.info(f"Initialized episodes for {url} (silent update)")
                         data['initialized'] = True

                    self.save_data()

        # Send notifications
        for notif in notifications:
            try:
                bot_instance.send_message(notif['chat_id'], notif['text'], parse_mode='HTML')
            except Exception as e:
                logger.error(f"Failed to send notification to {notif['chat_id']}: {e}")
