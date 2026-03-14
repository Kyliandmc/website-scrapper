import os
import re
import time
import base64
import hashlib
from collections import deque
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from PySide6.QtCore import Signal, QObject


class CrawlerSignals(QObject):
    """Thread-safe bridge between the crawler thread and the Qt UI."""
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    complete_signal = Signal(int, int)


class CrawlerEngine:
    """BFS web crawler that mirrors a website locally."""

    ASSET_EXTENSIONS = {
        "images":  {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp", ".tiff"},
        "styles":  {".css"},
        "scripts": {".js"},
        "fonts":   {".woff", ".woff2", ".ttf", ".eot", ".otf"},
        "media":   {".mp4", ".mp3", ".wav", ".ogg", ".webm", ".avi"},
        "docs":    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"},
    }

    MIME_TO_EXT = {
        "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/gif": ".gif", "image/svg+xml": ".svg", "image/webp": ".webp",
        "image/x-icon": ".ico", "image/bmp": ".bmp", "image/tiff": ".tiff",
    }

    def __init__(self, url, output_dir, depth=2, same_domain=True,
                 download_images=True, download_css=True, download_js=True,
                 download_fonts=True, download_media=False, download_docs=False,
                 on_progress=None, on_log=None, on_complete=None):
        self.start_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
        self.output_dir = output_dir
        self.max_depth = depth
        self.same_domain = same_domain
        self.download_images = download_images
        self.download_css = download_css
        self.download_js = download_js
        self.download_fonts = download_fonts
        self.download_media = download_media
        self.download_docs = download_docs
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_complete = on_complete

        self.base_domain = urlparse(self.start_url).netloc
        self.visited = set()
        self.downloaded_assets = set()
        self.queue = deque()
        self.total_files = 0
        self.total_size = 0
        self.running = False
        self.paused = False

        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def log(self, msg, level="INFO"):
        if self.on_log:
            self.on_log(f"[{level}] {msg}")

    def _notify_progress(self):
        if self.on_progress:
            self.on_progress(self.total_files, self.total_size)

    def _wait_if_paused(self):
        while self.paused:
            time.sleep(0.2)

    def should_download_asset(self, url):
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        mapping = {
            "images": self.download_images,
            "styles": self.download_css,
            "scripts": self.download_js,
            "fonts": self.download_fonts,
            "media": self.download_media,
            "docs": self.download_docs,
        }
        return any(ext in self.ASSET_EXTENSIONS[cat] and enabled
                    for cat, enabled in mapping.items())

    def url_to_filepath(self, url):
        parsed = urlparse(url)
        path = unquote(parsed.path)

        if not path or path == "/":
            path = "/index.html"
        elif path.endswith("/"):
            path += "index.html"
        elif "." not in os.path.basename(path):
            path += "/index.html"

        path = re.sub(r'[<>"|?*]', '_', path.lstrip("/"))

        if parsed.query:
            qhash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            base, ext = os.path.splitext(path)
            path = f"{base}_{qhash}{ext}"

        return os.path.join(self.output_dir, parsed.netloc, path)

    def download_file(self, url, filepath):
        if url in self.downloaded_assets:
            return True
        try:
            resp = self.session.get(url, timeout=10, stream=True)
            resp.raise_for_status()
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            content = resp.content
            with open(filepath, "wb") as f:
                f.write(content)
            self.downloaded_assets.add(url)
            self.total_files += 1
            self.total_size += len(content)
            return True
        except Exception as e:
            self.log(f"Failed: {url} ({e})", "ERROR")
            return False

    def _collect_asset_urls(self, soup, page_url):
        assets = []
        if self.download_css:
            for tag in soup.find_all("link", rel="stylesheet"):
                if tag.get("href"):
                    assets.append(urljoin(page_url, tag["href"]))
        if self.download_images:
            for tag in soup.find_all("img"):
                if tag.get("src"):
                    assets.append(urljoin(page_url, tag["src"]))
            for tag in soup.find_all(style=True):
                for u in re.findall(r'url\(["\']?([^"\')\s]+)["\']?\)', tag["style"]):
                    assets.append(urljoin(page_url, u))
        if self.download_js:
            for tag in soup.find_all("script", src=True):
                assets.append(urljoin(page_url, tag["src"]))
        for tag in soup.find_all("link"):
            href = tag.get("href")
            if href and self.should_download_asset(urljoin(page_url, href)):
                assets.append(urljoin(page_url, href))
        for tag in soup.find_all("link", rel=lambda x: x and "icon" in x):
            if tag.get("href"):
                assets.append(urljoin(page_url, tag["href"]))
        return assets

    def _save_data_uris(self, data_uris, page_url):
        for uri in data_uris:
            if not self.running:
                return
            try:
                header, encoded = uri.split(",", 1)
                mime = header.split(":")[1].split(";")[0]
                ext = self.MIME_TO_EXT.get(mime, ".bin")
                img_hash = hashlib.md5(encoded[:64].encode()).hexdigest()[:10]
                filename = f"base64_{img_hash}{ext}"
                domain = urlparse(page_url).netloc
                filepath = os.path.join(self.output_dir, domain, "base64_images", filename)
                if filepath not in self.downloaded_assets:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    img_data = base64.b64decode(encoded)
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    self.downloaded_assets.add(filepath)
                    self.total_files += 1
                    self.total_size += len(img_data)
                    self.log(f"Base64 image: {filename} ({self.format_size(len(img_data))})")
                    self._notify_progress()
            except Exception as e:
                self.log(f"Failed base64 image: {e}", "ERROR")

    def extract_and_download_assets(self, soup, page_url):
        all_urls = self._collect_asset_urls(soup, page_url)
        data_uris = [u for u in all_urls if u.startswith("data:")]
        remote_urls = [u for u in all_urls if not u.startswith("data:")]

        self._save_data_uris(data_uris, page_url)

        for url in remote_urls:
            if not self.running:
                return
            self._wait_if_paused()
            if url not in self.downloaded_assets:
                filepath = self.url_to_filepath(url)
                if self.download_file(url, filepath):
                    self.log(f"Asset: {url}")
                self._notify_progress()

    def extract_links(self, soup, page_url):
        links = []
        for tag in soup.find_all("a", href=True):
            full_url = urljoin(page_url, tag["href"])
            parsed = urlparse(full_url)
            if self.same_domain and parsed.netloc != self.base_domain:
                continue
            if parsed.scheme not in ("http", "https"):
                continue
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += f"?{parsed.query}"
            if clean not in self.visited:
                links.append(clean)
        return links

    def crawl_page(self, url, depth):
        if url in self.visited or depth > self.max_depth or not self.running:
            return []
        self._wait_if_paused()
        self.visited.add(url)
        self.log(f"Crawling (depth {depth}): {url}")

        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            self.log(f"Failed to fetch: {url} ({e})", "ERROR")
            return []

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            filepath = self.url_to_filepath(url)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            self.total_files += 1
            self.total_size += len(resp.content)
            self._notify_progress()
            return []

        # Force proper encoding detection
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        if soup.head and not soup.find("meta", charset=True):
            soup.head.insert(0, soup.new_tag("meta", charset="utf-8"))

        filepath = self.url_to_filepath(url)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        html_bytes = str(soup).encode("utf-8")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(str(soup))
        self.total_files += 1
        self.total_size += len(html_bytes)
        self.log(f"Saved: {filepath}")
        self._notify_progress()

        self.extract_and_download_assets(soup, url)
        return self.extract_links(soup, url)

    def start(self):
        self.running = True
        self.paused = False
        self.log(f"Starting crawl: {self.start_url}")
        self.log(f"Output: {self.output_dir}")
        self.log(f"Max depth: {self.max_depth}")

        self.queue.append((self.start_url, 0))
        while self.queue and self.running:
            self._wait_if_paused()
            url, depth = self.queue.popleft()
            for link in self.crawl_page(url, depth):
                if link not in self.visited:
                    self.queue.append((link, depth + 1))

        self.log(f"Crawl complete! {self.total_files} files, {self.format_size(self.total_size)}")
        if self.on_complete:
            self.on_complete(self.total_files, self.total_size)

    def stop(self):
        self.running = False
        self.log("Crawl stopped by user.", "WARN")

    def pause(self):
        self.paused = True
        self.log("Crawl paused.", "WARN")

    def resume(self):
        self.paused = False
        self.log("Crawl resumed.")

    @staticmethod
    def format_size(size_bytes):
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
