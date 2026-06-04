import base64, requests, json, re, time, os, sys, subprocess, zipfile, threading, queue
from pathlib import Path
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

class UnsafePipelineError(Exception):
    pass


class ContentItem:
    def __init__(self, title: str, urls: list):
        self.title = title
        self.urls = urls

    @property
    def safe_name(self) -> str:
        return re.sub(r'[^\w]', '_', self.title)


class _X:
    def __init__(self, source: str = None):
        self._u = base64.b64decode(_CONFIG['a']).decode()
        self._s = base64.b64decode(_CONFIG['b']).decode()
        self._m = base64.b64decode(_CONFIG['c']).decode()
        self._f = base64.b64decode(_CONFIG['d']).decode()
        self._mf = base64.b64decode(_CONFIG['e']).decode()
        self._p = base64.b64decode(_CONFIG['f']).decode()
        self._source = source
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
    
    def _scrape_item(self, item_url):
        print(f"[Thread] Processing: {item_url}")
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
        
        print(f"  Bypassing protection...")
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
                print(f"  Found {len(final_links)} parts")
    
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
    
    def scrape_mt(self, max_pages=None, workers=3):
        if self._source:
            with open(self._source, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for game in data.get('games', []):
                for url in game.get('urls', []):
                    if self._s in url:
                        raise UnsafePipelineError(f"Shortener URL rejected: {url}")
            return data.get('games', [])

        page = 1
        all_links = []

        while True:
            if max_pages and page > max_pages:
                break

            print(f"[Page {page}] Fetching...")
            links = self._get_listings(page)
            if not links:
                break

            all_links.extend(links)
            page += 1
            time.sleep(1)

        print(f"\nProcessing {len(all_links)} items with {workers} workers...")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self._scrape_item, url): url for url in all_links}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error: {e}")

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


class ContentManager:
    def __init__(self, catalog_path=None):
        self._catalog_path = Path(catalog_path) if catalog_path else Path('catalog.json')
        self._dm = _DM()
        self._ex = _EX()

    def update_catalog(self, source: str) -> list:
        with open(source, 'r', encoding='utf-8') as f:
            data = json.load(f)
        items = [ContentItem(title=g['title'], urls=g.get('urls', [])) for g in data.get('games', [])]
        out = {'games': [{'title': it.title, 'urls': it.urls} for it in items]}
        self._catalog_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
        return items

    def list_games(self) -> list:
        if not self._catalog_path.exists():
            return []
        with open(self._catalog_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        items = [ContentItem(title=g['title'], urls=g.get('urls', [])) for g in data.get('games', [])]
        for item in items:
            print(item.title)
        return items

    def update(self, pages=None):
        x = _X()
        x.scrape_mt(max_pages=pages, workers=3)
        x.save()

    def download(self, index=None):
        if not self._catalog_path.exists():
            print("No catalog found")
            return
        with open(self._catalog_path, 'r') as f:
            catalog = json.load(f)
        games = catalog.get('games', catalog) if isinstance(catalog, dict) else catalog

        if index is not None:
            games = [games[index]] if 0 <= index < len(games) else []

        for game in games:
            title = game.get('title', game.get('t', 'Unknown'))
            print(f"\n=== {title} ===")
            folder = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
            game_dir = os.path.join('downloads', folder)
            os.makedirs(game_dir, exist_ok=True)

            parts = []
            for i, link in enumerate(game.get('urls', game.get('d', []))):
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
