import base64, requests, json, re, time, os, sys, subprocess, zipfile, rarfile, threading, queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import hashlib

# ============================================================================
# OBFUSCATED CONFIGURATION - DECODE AT RUNTIME
# ============================================================================

_CONFIG = {
    'a': 'aHR0cHM6Ly93d3cub3ZhZ2FtZXMuY29t',  # base64 encoded target
    'b': 'c2hyaW5rbWUuY2xpY2s=',  # shrinkme
    'c': 'bXJwcm9ibG9nZ2VyLmNvbQ==',  # mrproblogger
    'd': 'ZmlsZWNyeXB0LmNj',  # filecrypt
    'e': 'bWVkaWFmaXJlLmNvbQ==',  # mediafire
    'f': 'd3d3Lm92YWdhbWVzLmNvbQ==',  # rar password
    'g': 'P2Q9ZG93bmxvYWQmc2VjdGlvbj0=',  # download section param
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
        self._q = queue.Queue()
        
    def _g(self, url, retries=3):
        for _ in range(retries):
            try:
                r = self._sess.get(url, timeout=30)
                r.raise_for_status()
                return r.text
            except:
                time.sleep(2)
        return None
    
    def _e(self, soup):
        links = []
        for a in soup.find_all('a', href=True):
            h = a['href']
            if self._mf in h or 'mediafire' in h:
                links.append({'u': h, 't': 'mf', 'n': a.get_text(strip=True)})
        return links
    
    def _bypass_shrinkme(self, url):
        """Bypass shrinkme.click and mrproblogger chain"""
        try:
            # Initial request to shrinkme
            r = self._sess.get(url, allow_redirects=True)
            time.sleep(12)  # Wait for timer
            
            # Look for continue button or redirect
            soup = BeautifulSoup(r.text, 'html.parser')
            continue_btn = soup.find('a', class_=re.compile('btn|continue|get'))
            if continue_btn and continue_btn.get('href'):
                next_url = continue_btn['href']
                if not next_url.startswith('http'):
                    next_url = 'https://' + self._m + next_url
                return self._bypass_mrpro(next_url)
            return None
        except:
            return None
    
    def _bypass_mrpro(self, url):
        """Bypass mrproblogger wait"""
        try:
            time.sleep(12)  # Required wait
            r = self._sess.get(url)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Find get link button
            for a in soup.find_all('a'):
                if 'get' in a.get_text(strip=True).lower() or 'link' in a.get_text(strip=True).lower():
                    return a['href']
            return None
        except:
            return None
    
    def _solve_filecrypt(self, url):
        """Use selenium to solve filecrypt circle captcha"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 30)
            
            # Wait for circle captcha to load
            time.sleep(3)
            
            # Find and click the open circle (usually has specific class or is clickable)
            circles = driver.find_elements(By.CSS_SELECTOR, 'circle, .circle, [class*="circle"]')
            for circle in circles:
                try:
                    circle.click()
                    time.sleep(2)
                    break
                except:
                    continue
            
            # Wait for download links to appear
            time.sleep(3)
            
            # Extract mediafire links
            links = []
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                href = a.get_attribute('href')
                if href and ('mediafire' in href or self._mf in href):
                    links.append(href)
            
            return links
        finally:
            driver.quit()
    
    def _scrape_item(self, item_url):
        """Scrape single item page"""
        print(f"[Thread] Processing: {item_url}")
        html = self._g(item_url)
        if not html:
            return
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get title
        title = soup.find('h1', class_='entry-title')
        title = title.get_text(strip=True) if title else "Unknown"
        
        # Find mediafire button/link
        dl_section = None
        for a in soup.find_all('a'):
            text = a.get_text(strip=True).lower()
            if 'mediafire' in text or 'mf' in text:
                dl_section = a['href']
                break
        
        if not dl_section:
            return
        
        # Follow the chain
        print(f"  Bypassing shortener chain...")
        filecrypt_url = self._bypass_shrinkme(dl_section)
        if not filecrypt_url:
            return
        
        print(f"  Solving captcha...")
        final_links = self._solve_filecrypt(filecrypt_url)
        
        item_data = {
            't': title,
            'u': item_url,
            'd': final_links,
            'p': self._p  # extraction password
        }
        
        with self._lock:
            self._catalog.append(item_data)
            print(f"  Found {len(final_links)} parts")
        
        return item_data
    
    def _get_listings(self, page=1):
        """Get all item links from listing page"""
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
    
    def scrape_mt(self, max_pages=None, workers=5):
        """Multithreaded scraper"""
        page = 1
        all_links = []
        
        while True:
            if max_pages and page > max_pages:
                break
            
            print(f"[Page {page}] Fetching listings...")
            links = self._get_listings(page)
            
            if not links:
                break
            
            all_links.extend(links)
            page += 1
            time.sleep(1)
        
        print(f"\nTotal items to process: {len(all_links)}")
        
        # Process with thread pool
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
        print(f"\nSaved {len(self._catalog)} items to {fn}")


# ============================================================================
# DOWNLOAD MANAGER WITH MULTIPART SUPPORT
# ============================================================================

class _DM:
    def __init__(self, chunks=8):
        self.chunks = chunks
        self._sess = requests.Session()
        
    def get_direct_link(self, mediafire_url):
        """Extract direct download link from mediafire page"""
        try:
            r = self._sess.get(mediafire_url)
            # Look for direct link pattern
            match = re.search(r'"https://download\d+\.mediafire\.com/[^"]+"', r.text)
            if match:
                return match.group(0).strip('"')
            
            # Alternative: find download button
            soup = BeautifulSoup(r.text, 'html.parser')
            btn = soup.find('a', {'id': 'downloadButton'})
            if btn and btn.get('href'):
                return btn['href']
        except:
            pass
        return None
    
    def download_part(self, url, dest, callback=None):
        """Download single part with progress"""
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
    
    def download_game(self, game_data, output_dir='downloads'):
        """Download all parts for a game"""
        title = re.sub(r'[^\w\s-]', '', game_data['t']).strip().replace(' ', '_')
        game_dir = os.path.join(output_dir, title)
        os.makedirs(game_dir, exist_ok=True)
        
        parts = []
        for i, link in enumerate(game_data['d']):
            filename = f"part_{i+1:03d}.rar"
            dest = os.path.join(game_dir, filename)
            
            print(f"Downloading {filename}...")
            if self.download_part(link, dest):
                parts.append(dest)
        
        return parts, game_data.get('p')


# ============================================================================
# EXTRACTION & INSTALLER
# ============================================================================

class _EX:
    def __init__(self):
        self._p = base64.b64decode(_CONFIG['f']).decode()
    
    def extract(self, parts, game_dir):
        """Extract multipart rar"""
        if not parts:
            return False
        
        # Find first part
        first_part = None
        for p in parts:
            if 'part01' in p or 'part1' in p or 'part001' in p:
                first_part = p
                break
        
        if not first_part:
            first_part = sorted(parts)[0]
        
        try:
            # Try unrar first
            result = subprocess.run([
                'unrar', 'x', '-p' + self._p, first_part, game_dir
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("Extraction successful")
                return True
        except:
            pass
        
        # Fallback to Python rarfile
        try:
            with rarfile.RarFile(first_part) as rf:
                rf.extractall(game_dir, pwd=self._p.encode())
            return True
        except Exception as e:
            print(f"Extraction failed: {e}")
            return False
    
    def find_installer(self, game_dir):
        """Find setup executable in extracted files"""
        installers = []
        for root, dirs, files in os.walk(game_dir):
            for f in files:
                if f.lower() in ['setup.exe', 'install.exe', 'autorun.exe', 'start.exe']:
                    installers.append(os.path.join(root, f))
                elif f.endswith('.exe') and 'setup' in f.lower():
                    installers.append(os.path.join(root, f))
        return installers


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class ContentManager:
    def __init__(self):
        self._x = _X()
        self._dm = _DM()
        self._ex = _EX()
    
    def update_catalog(self, pages=None):
        """Scrape and update catalog"""
        self._x.scrape_mt(max_pages=pages, workers=5)
        self._x.save()
        return self._x._catalog
    
    def download(self, game_index=None, title_filter=None):
        """Download specific game or all"""
        catalog = self._x._catalog
        if not catalog:
            try:
                with open('catalog.json', 'r') as f:
                    catalog = json.load(f)
            except:
                print("No catalog found. Run update first.")
                return
        
        to_download = []
        if game_index is not None:
            to_download = [catalog[game_index]]
        elif title_filter:
            to_download = [g for g in catalog if title_filter.lower() in g['t'].lower()]
        else:
            to_download = catalog
        
        for game in to_download:
            print(f"\n{'='*50}")
            print(f"Processing: {game['t']}")
            print(f"{'='*50}")
            
            parts, pwd = self._dm.download_game(game)
            if parts:
                game_dir = os.path.dirname(parts[0])
                if self._ex.extract(parts, game_dir):
                    installers = self._ex.find_installer(game_dir)
                    if installers:
                        print(f"\nFound installers: {installers}")
                        # Optionally auto-run: subprocess.run([installers[0]])
    
    def list_games(self):
        """List all games in catalog"""
        try:
            with open('catalog.json', 'r') as f:
                catalog = json.load(f)
            for i, g in enumerate(catalog):
                print(f"[{i}] {g['t']} - {len(g['d'])} parts")
        except:
            print("No catalog found")


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Digital Content Manager')
    parser.add_argument('action', choices=['update', 'download', 'list'])
    parser.add_argument('--pages', '-p', type=int, help='Max pages to scrape')
    parser.add_argument('--index', '-i', type=int, help='Game index to download')
    parser.add_argument('--filter', '-f', help='Filter by title')
    
    args = parser.parse_args()
    
    cm = ContentManager()
    
    if args.action == 'update':
        cm.update_catalog(pages=args.pages)
    elif args.action == 'download':
        cm.download(game_index=args.index, title_filter=args.filter)
    elif args.action == 'list':
        cm.list_games()
