# -*- coding: utf-8 -*-
"""
ページクローラー & アナライザー
記事URLをクロールし、タイトル・メタ・見出し構造・本文文字数・
内部リンク・画像・表・執筆者情報・出典・更新日を抽出する。
"""
import re
import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("factoring-diagnosis.crawler")

# ── 共通ヘッダー ──────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT = 15


class PageAnalyzer:
    """単一ページを解析し、構造化データを返す"""

    def analyze(self, url: str) -> dict:
        """
        URL をクロールして記事データを抽出

        Returns:
            {
                url, title, meta_description, headings[{level,text}],
                body_text, word_count, internal_links[{text,url}],
                image_count, table_count, author, sources, updated_date,
                has_demerits, has_numbers
            }
        """
        html = self._fetch(url)
        if not html:
            logger.warning("HTML取得失敗: %s", url)
            return {"url": url, "error": "HTML取得失敗"}

        soup = BeautifulSoup(html, "lxml")

        result = {
            "url": url,
            "title": self._extract_title(soup),
            "meta_description": self._extract_meta_description(soup),
            "headings": self._extract_headings(soup),
            "body_text": "",
            "word_count": 0,
            "internal_links": self._extract_internal_links(soup, url),
            "image_count": self._count_images(soup),
            "table_count": self._count_tables(soup),
            "author": self._extract_author(soup),
            "sources": self._extract_sources(soup),
            "updated_date": self._extract_updated_date(soup),
            "has_demerits": self._check_demerits(soup),
            "has_numbers": self._check_numbers(soup),
        }

        result["body_text"] = self._extract_body_text(soup)
        result["word_count"] = len(result["body_text"])
        return result

    # ── HTTP取得 ──────────────────────────────────
    def _fetch(self, url: str) -> str | None:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                logger.warning("HTTP %d: %s", resp.status_code, url)
                return None
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            logger.error("取得エラー %s: %s", url, e)
            return None

    # ── タイトル ──────────────────────────────────
    def _extract_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return ""

    # ── メタディスクリプション ────────────────────
    def _extract_meta_description(self, soup: BeautifulSoup) -> str:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return og["content"].strip()
        return ""

    # ── 見出し構造 ────────────────────────────────
    def _extract_headings(self, soup: BeautifulSoup) -> list[dict]:
        headings = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
            level = int(tag.name[1])
            text = tag.get_text(strip=True)
            if text and level <= 3:
                headings.append({"level": level, "text": text})
        return headings

    # ── 本文テキスト（見出し・段落を結合） ──────────
    def _extract_body_text(self, soup: BeautifulSoup) -> str:
        # script, style, nav, footer, header を除去
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        article = soup.find("article") or soup.find("main") or soup.find(class_=re.compile(r"post|article|content", re.I)) or soup
        return article.get_text(separator="\n", strip=True)

    # ── 内部リンク ────────────────────────────────
    def _extract_internal_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc == base_domain:
                if full_url not in seen and full_url != base_url:
                    seen.add(full_url)
                    links.append({
                        "text": a.get_text(strip=True)[:60],
                        "url": full_url,
                    })
        return links

    # ── 画像数 ────────────────────────────────────
    def _count_images(self, soup: BeautifulSoup) -> int:
        imgs = soup.find_all("img")
        # 意味のある画像のみ（幅・高さ1pxのトラッキング等を除外）
        count = 0
        for img in imgs:
            w = img.get("width", "")
            h = img.get("height", "")
            if w in ("1", "1px") or h in ("1", "1px"):
                continue
            count += 1
        return count

    # ── 表数 ──────────────────────────────────────
    def _count_tables(self, soup: BeautifulSoup) -> int:
        return len(soup.find_all("table"))

    # ── 執筆者情報 ────────────────────────────────
    def _extract_author(self, soup: BeautifulSoup) -> str:
        # 1. metaタグ
        for selector in [
            ("meta", {"name": "author"}),
            ("meta", {"property": "article:author"}),
            ("meta", {"name": "twitter:creator"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                return tag["content"].strip()

        # 2. class/id から推測
        for pattern in ["author", "writer", "byline", "post-author", "article-author"]:
            el = soup.find(class_=re.compile(pattern, re.I))
            if el:
                text = el.get_text(strip=True)
                if text and len(text) < 100:
                    return text
            el = soup.find(attrs={"id": re.compile(pattern, re.I)})
            if el:
                text = el.get_text(strip=True)
                if text and len(text) < 100:
                    return text

        # 3. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    author = data.get("author", {})
                    if isinstance(author, dict) and author.get("name"):
                        return author["name"]
                    if isinstance(author, str):
                        return author
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            author = item.get("author", {})
                            if isinstance(author, dict) and author.get("name"):
                                return author["name"]
            except (json.JSONDecodeError, TypeError):
                pass

        return ""

    # ── 出典・参照元 ──────────────────────────────
    def _extract_sources(self, soup: BeautifulSoup) -> list[str]:
        sources = []
        # 引用・出典を示す要素
        for pattern in ["source", "reference", "出典", "参照", "引用元", "source-list"]:
            el = soup.find(class_=re.compile(pattern, re.I))
            if el:
                sources.append(el.get_text(strip=True)[:200])

        # 外部リンクで出典と思われるもの
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(d in href for d in ["go.jp", "gov.jp", "metro.tokyo", "court"]):
                sources.append(a.get_text(strip=True)[:100])

        # JSON-LD の references / citation
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    for key in ("references", "citation"):
                        refs = data.get(key, [])
                        if isinstance(refs, list):
                            for ref in refs:
                                if isinstance(ref, dict):
                                    sources.append(ref.get("name", ref.get("url", "")))
                                elif isinstance(ref, str):
                                    sources.append(ref)
            except (json.JSONDecodeError, TypeError):
                pass

        return [s for s in sources if s][:10]

    # ── 更新日 ────────────────────────────────────
    def _extract_updated_date(self, soup: BeautifulSoup) -> str:
        # 1. metaタグ
        for selector in [
            ("meta", {"property": "article:modified_time"}),
            ("meta", {"name": "dcterms.modified"}),
            ("meta", {"itemprop": "dateModified"}),
        ]:
            tag = soup.find(*selector)
            if tag and tag.get("content"):
                return tag["content"].strip()

        # 2. class/id から推測
        for pattern in ["updated", "modified", "post-date", "publish", "date"]:
            el = soup.find(class_=re.compile(pattern, re.I))
            if el:
                text = el.get_text(strip=True)
                if text and len(text) < 80:
                    return text
            el = soup.find(attrs={"id": re.compile(pattern, re.I)})
            if el:
                text = el.get_text(strip=True)
                if text and len(text) < 80:
                    return text

        # 3. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    for key in ("dateModified", "datePublished"):
                        val = data.get(key)
                        if val:
                            return str(val)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for key in ("dateModified", "datePublished"):
                                val = item.get(key)
                                if val:
                                    return str(val)
            except (json.JSONDecodeError, TypeError):
                pass

        # 4. 正規表現で日付パターンを探索
        page_text = soup.get_text()
        date_patterns = [
            r"20\d{2}[年/.\-]\s*\d{1,2}[月/.\-]\s*\d{1,2}日?\s*(?:更新|修订|modified|updated)?",
            r"(?:更新|最終更新)\s*[:：]?\s*20\d{2}[年/.\-]\s*\d{1,2}[月/.\-]\s*\d{1,2}",
        ]
        for pat in date_patterns:
            m = re.search(pat, page_text)
            if m:
                return m.group(0).strip()

        return ""

    # ── デメリット記載チェック ────────────────────
    def _check_demerits(self, soup: BeautifulSoup) -> bool:
        demerit_keywords = [
            "デメリット", "注意点", "注意事項", "リスク", "欠点",
            "失敗", "失敗例", "注意", "気をつけ", "注意すべき",
            "やめとけ", "後悔", "罠", "落とし穴", "ひっかけ",
            "悪徳", "トラブル", "NG", "してはいけない",
        ]
        text = soup.get_text()
        return any(kw in text for kw in demerit_keywords)

    # ── 数値含有チェック ──────────────────────────
    def _check_numbers(self, soup: BeautifulSoup) -> bool:
        text = soup.get_text()
        # 手数料率、金額、利率等の数値パターン
        number_patterns = [
            r"\d+\.?\d*\s*[%％]",          # パーセント
            r"\d{1,3}(?:,\d{3})*\s*円",     # 金額
            r"\d+\.?\d*\s*倍",              # 倍率
            r"\d+\.?\d*\s*日",              # 日数
        ]
        return any(re.search(pat, text) for pat in number_patterns)
