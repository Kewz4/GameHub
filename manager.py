import base64, requests, json, re, time, os, sys, subprocess, zipfile, threading, queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import hashlib

# ============================================================================
# CONFIGURATION - BASE64 ENCODED
# ============================================================================

_CONFIG = {
    'a': 'aHR0cHM6Ly93d3cub3ZhZ2FtZXMuY29t',
    'b': 'c2hyaW5rbWUuY2xpY2s=',
    'c': 'bXJwcm9ibG9nZ2VyLmNvbQ==',
    'd': 'ZmlsZWNyeXB0LmNj',
    'e': 'bWVkaWFmaXJlLmNvbQ==',
    'f': 'd3d3Lm92YWdhbWVzLmNvbQ==',
}

class _X:
    def __init__(self):
        self._u = base64.b64decode(_CONFIG['a']).decode()
        self._s = base64.b64decode(_CONFIG['b']).decode()
        self._m = base64.b64decode(_CONFIG['c']).decode()
        self._f = base64.b64decode(_CONFIG['d']).decode()
        self._mf = base64.b64decode(_CONFIG['e']).decode()
        self._p = base64.b64decode(_CONFIG['f']).decode()
        self._sess = requests.Session()
        self._sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self._catalog = []
        self._lock = threading.Lock()
        
    def _g(self, url, retries=3):
        for _ in range(retries):
            try:
                r = self._sess.get(url, timeout=30)
                r.raise_for_status()
                return r.text
            except:
                time.sleep(2)
        return None
    
    def _bypass_chain(self, url):
        """Full bypass: shrinkme -> mrproblogger -> filecrypt"""
        try:
            # Step 1: shrinkme.click
            r = self._sess.get(url, allow_redirects=True)
            time.sleep(12)
            
            soup = BeautifulSoup(r.text, 'html.parser')
            continue_btn = soup.find('a', class_=re.compile('btn|continue'))
            if continue_btn and continue_btn.get('href'):
                next_url = continue_btn['href']
                if not next_url.startswith('http'):
                    next_url = 'https://' + self._m + next_url
                
                # Step 2: mrproblogger
                time.sleep(12)
                r2 = self._sess.get(next_url)
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                
                for a in soup2.find_all('a'):
                    txt = a.get_text(strip=True).lower()
                    if 'get' in txt or 'link' in txt:
                        filecrypt_url = a['href']
                        return self._solve_filecrypt(filecrypt_url)
            return None
        except Exception as e:
            print(f"Bypass error: {e}")
            return None
    
    def _solve_filecrypt(self, url):
        """Solve FileCrypt circle captcha with Selenium"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        try:
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            time.sleep(3)
            
            # Find and click circles
            elements = driver.find_elements(By.CSS_SELECTOR, 'circle, .circle, [class*="circle"], .captcha-circle')
            for elem in elements:
                try:
                    elem.click()
                    time.sleep(2)
                    break
                except:
                    continue
            
            time.sleep(3)
            
            # Extract links
            links = []
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                href = a.get_attribute('href')
                if href and self._mf in href:
                    links.append(href)
            
            return links
        except Exception as e:
            print(f"FileCrypt error: {e}")
            return []
        finally:
            try:
                driver.quit()
            except:
                pass
    
    def _scrape_item(self, item_url, progress_cb=None):
        _log = progress_cb or print
        _log(f"[Scraping] {item_url}")
        html = self._g(item_url)
        if not html:
            return

        soup = BeautifulSoup(html, 'html.parser')
        title = soup.find('h1', class_='entry-title')
        title = title.get_text(strip=True) if title else "Unknown"

        # Find download section
        dl_link = None
        for a in soup.find_all('a'):
            text = a.get_text(strip=True).lower()
            if 'mediafire' in text or self._mf in a.get('href', ''):
                dl_link = a['href']
                break

        if not dl_link:
            return

        _log(f"[Bypassing] {title}")
        final_links = self._bypass_chain(dl_link)

        if final_links:
            item_data = {
                't': title,
                'u': item_url,
                'd': final_links,
                'p': self._p
            }
            with self._lock:
                self._catalog.append(item_data)
                _log(f"[Found] {title} — {len(final_links)} part(s)")
    
    def _get_listings(self, page=1):
        url = f"{self._u}/page/{page}/" if page > 1 else self._u
        html = self._g(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for h in soup.find_all(['h2', 'h1'], class_='entry-title'):
            a = h.find('a')
            if a and a.get('href'):
                links.append(a['href'])
        return links
    
    def scrape_mt(self, max_pages=None, workers=3, progress_cb=None):
        _log = progress_cb or print
        page = 1
        all_links = []

        while True:
            if max_pages and page > max_pages:
                break
            _log(f"[Page {page}] Fetching listings…")
            links = self._get_listings(page)
            if not links:
                break
            all_links.extend(links)
            page += 1
            time.sleep(1)

        _log(f"[Scraper] Processing {len(all_links)} titles with {workers} workers…")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._scrape_item, url, progress_cb): url
                for url in all_links
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    _log(f"[Error] {e}")

        return self._catalog
    
    def save(self, fn='catalog.json'):
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(self._catalog, f, indent=2)
        print(f"\nSaved {len(self._catalog)} items")


class _DM:
    def __init__(self, chunks=4):
        self.chunks = chunks
        self._sess = requests.Session()
        
    def get_direct_link(self, mediafire_url):
        try:
            r = self._sess.get(mediafire_url)
            # Try multiple patterns
            patterns = [
                r'"https://download\d+\.mediafire\.com/[^"]+"',
                r'(https://[^"\s]+mediafire\.com/download[^"\s]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, r.text)
                if match:
                    return match.group(0).strip('"')
            
            soup = BeautifulSoup(r.text, 'html.parser')
            btn = soup.find('a', {'id': 'downloadButton'})
            if btn:
                return btn.get('href')
        except:
            pass
        return None
    
    def download_file(self, url, dest, callback=None):
        direct = self.get_direct_link(url) if 'mediafire' in url else url
        if not direct:
            return False
        
        try:
            r = self._sess.get(direct, stream=True)
            total = int(r.headers.get('content-length', 0))
            
            with open(dest, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback:
                            callback(downloaded, total)
            return True
        except Exception as e:
            print(f"Download error: {e}")
            return False


class _EX:
    def __init__(self):
        self._p = base64.b64decode(_CONFIG['f']).decode()
    
    def extract(self, parts, game_dir):
        if not parts:
            return False
        
        # Find first part
        first = None
        for p in parts:
            if any(x in p.lower() for x in ['part1.', 'part01.', 'part001.', '.part1.']):
                first = p
                break
        
        if not first:
            first = sorted(parts)[0]
        
        try:
            # Try unrar
            result = subprocess.run(
                ['unrar', 'x', '-y', f'-p{self._p}', first, game_dir + os.sep],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return True
        except:
            pass
        
        # Try 7z
        try:
            result = subprocess.run(
                ['7z', 'x', f'-p{self._p}', first, f'-o{game_dir}'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return True
        except:
            pass
        
        return False


# =============================================================================
# BUILT-IN CATALOG  –  free / open-source games with direct Windows links
# =============================================================================

BUILTIN_CATALOG = [
    {
        "title": "OpenTTD",
        "description": "Open-source transport tycoon simulation. Build rail, road, air and water networks.",
        "urls": ["https://cdn.openttd.org/openttd-releases/14.1/openttd-14.1-windows-win64.exe"],
        "tags": ["simulation", "strategy"],
    },
    {
        "title": "SuperTuxKart",
        "description": "Kart racing game with Tux and friends. Single player, split-screen and online.",
        "urls": ["https://github.com/supertuxkart/stk-code/releases/download/1.4/SuperTuxKart-1.4-win-x86_64.zip"],
        "tags": ["racing", "arcade"],
    },
    {
        "title": "Warzone 2100",
        "description": "Post-apocalyptic real-time strategy game with a full campaign and skirmish modes.",
        "urls": ["https://github.com/Warzone2100/warzone2100/releases/download/4.4.2/warzone2100_4.4.2_windows_x64.exe"],
        "tags": ["rts", "strategy"],
    },
    {
        "title": "Minetest",
        "description": "Infinite-world block sandbox game with survival and creative modes, fully moddable.",
        "urls": ["https://github.com/minetest/minetest/releases/download/5.9.0/minetest-5.9.0-win64.zip"],
        "tags": ["sandbox", "survival"],
    },
    {
        "title": "Battle for Wesnoth",
        "description": "Turn-based fantasy strategy game with a huge collection of campaigns and maps.",
        "urls": ["https://sourceforge.net/projects/wesnoth/files/wesnoth-1.18/wesnoth-1.18.2/wesnoth-1.18.2-win64.exe/download"],
        "tags": ["strategy", "turn-based", "fantasy"],
    },
    {
        "title": "Xonotic",
        "description": "Fast-paced open-source first-person shooter with crisp movement and online play.",
        "urls": ["https://dl.xonotic.org/xonotic-0.8.6.zip"],
        "tags": ["fps", "shooter"],
    },
    {
        "title": "0 A.D.",
        "description": "Historical real-time strategy game spanning civilisations from 500 BC to 500 AD.",
        "urls": ["https://releases.wildfiregames.com/0ad-0.0.27-alpha-win32.exe"],
        "tags": ["rts", "historical"],
    },
    {
        "title": "FreeCiv",
        "description": "Multiplayer strategy game inspired by the history of human civilisation.",
        "urls": ["https://github.com/freeciv/freeciv/releases/download/S3_1_0/freeciv-3.1.0-win64-gtk3.22.exe"],
        "tags": ["strategy", "4x"],
    },
    {
        "title": "Teeworlds",
        "description": "Retro-style online multiplayer 2D shooter. Simple, fast and very addictive.",
        "urls": ["https://github.com/teeworlds/teeworlds/releases/download/0.7.5/teeworlds-0.7.5-win64.zip"],
        "tags": ["shooter", "2d", "multiplayer"],
    },
    {
        "title": "AssaultCube",
        "description": "Realistic-ish first-person shooter set in urban environments. Low system requirements.",
        "urls": ["https://github.com/assaultcube/AC/releases/download/v1.3.0.2/AssaultCube_v1.3.0.2.exe"],
        "tags": ["fps", "shooter"],
    },
    {
        "title": "Endless Sky",
        "description": "Space exploration and trading game in the tradition of Elite and Escape Velocity.",
        "urls": ["https://github.com/endless-sky/endless-sky/releases/download/v0.10.9/endless-sky-win64-0.10.9.exe"],
        "tags": ["space", "rpg", "trading"],
    },
    {
        "title": "FlightGear",
        "description": "Professional open-source flight simulator with hundreds of aircraft and global scenery.",
        "urls": ["https://sourceforge.net/projects/flightgear/files/release-2020.3/FlightGear-2020.3.19.exe/download"],
        "tags": ["simulation", "flight"],
    },
    {
        "title": "Veloren",
        "description": "Multiplayer voxel RPG inspired by Cube World and Legend of Zelda. Always free.",
        "urls": ["https://download.veloren.net/latest/windows/x86_64/stable"],
        "tags": ["rpg", "voxel", "multiplayer"],
    },
    {
        "title": "The Dark Mod",
        "description": "Standalone stealth game in a Victorian/steampunk world, inspired by Thief.",
        "urls": ["https://www.thedarkmod.com/download-the-mod/"],
        "tags": ["stealth", "action"],
    },
    {
        "title": "Unknown Horizons",
        "description": "Real-time strategy and city builder with a strong focus on economy and trade.",
        "urls": ["https://github.com/unknown-horizons/unknown-horizons/releases/download/2019.1/UnknownHorizons-2019.1.exe"],
        "tags": ["rts", "city-builder"],
    },
]


def get_builtin_catalog() -> list[dict]:
    """Return the built-in game catalog."""
    return BUILTIN_CATALOG


class ContentManager:
    def __init__(self):
        self._x = _X()
        self._dm = _DM()
        self._ex = _EX()
    
    def update(self, pages=None, progress_cb=None):
        self._x.scrape_mt(max_pages=pages, workers=3, progress_cb=progress_cb)
        self._x.save()
    
    def download(self, index=None):
        try:
            with open('catalog.json', 'r') as f:
                catalog = json.load(f)
        except:
            print("No catalog found")
            return
        
        if index is not None:
            games = [catalog[index]] if 0 <= index < len(catalog) else []
        else:
            games = catalog
        
        for game in games:
            print(f"\n=== {game['t']} ===")
            title = re.sub(r'[^\w\s-]', '', game['t']).strip().replace(' ', '_')
            game_dir = os.path.join('downloads', title)
            os.makedirs(game_dir, exist_ok=True)
            
            parts = []
            for i, link in enumerate(game['d']):
                dest = os.path.join(game_dir, f"part_{i+1:03d}.rar")
                print(f"Downloading part {i+1}...")
                if self._dm.download_file(link, dest):
                    parts.append(dest)
            
            if parts and self._ex.extract(parts, game_dir):
                print("Extraction complete")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['update', 'download'])
    parser.add_argument('--pages', type=int)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    
    cm = ContentManager()
    if args.action == 'update':
        cm.update(pages=args.pages)
    elif args.action == 'download':
        cm.download(index=args.index)
