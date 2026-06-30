# -*- coding: utf-8 -*-
"""
検索エンジン連携モジュール
Google検索で上位記事URLを取得し、PAA・関連サジェストを抽出する。
googlesearch-pythonライブラリを使用（無料・APIキー不要）。
代替として SerpAPI / Custom Search API もサポート。
"""
import os
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("factoring-diagnosis.search")


class CompetitorSearch:
    """競合記事URL・PAA・サジェストを取得"""

    def __init__(self):
        # SerpAPIキーが環境変数にあれば優先使用
        self.serp_api_key = os.environ.get("SERPAPI_KEY", "")
        # Google Custom Search API（フォールバック）
        self.google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.google_cx = os.environ.get("GOOGLE_CX", "")

    def search(self, keyword: str, num_results: int = 8, exclude_url: str = "") -> dict:
        """
        キーワードで検索し、上位記事URLリスト・PAA・サジェストを返す

        Returns:
            {"urls": [...], "paa": [...], "suggestions": [...]}
        """
        if self.serp_api_key:
            return self._search_with_serpapi(keyword, num_results, exclude_url)
        elif self.google_api_key and self.google_cx:
            return self._search_with_google_cse(keyword, num_results, exclude_url)
        else:
            return self._search_with_googlesearch(keyword, num_results, exclude_url)

    # ── SerpAPI（最も高品質・有料） ─────────────────
    def _search_with_serpapi(self, keyword: str, num_results: int, exclude_url: str) -> dict:
        logger.info("SerpAPIを使用: %s", keyword)
        params = {
            "engine": "google",
            "q": keyword,
            "num": num_results,
            "hl": "ja",
            "gl": "jp",
            "api_key": self.serp_api_key,
        }
        try:
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            data = resp.json()

            urls = []
            for result in data.get("organic_results", []):
                link = result.get("link", "")
                if link and link != exclude_url:
                    urls.append(link)

            paa = [item.get("question", "") for item in data.get("related_questions", []) if item.get("question")]
            suggestions = [item for item in data.get("related_searches", []) if isinstance(item, dict)]
            suggestions = [s.get("query", "") for s in suggestions if s.get("query")]

            return {"urls": urls[:num_results], "paa": paa, "suggestions": suggestions}
        except Exception as e:
            logger.error("SerpAPIエラー: %s — フォールバック", e)
            return self._search_with_googlesearch(keyword, num_results, exclude_url)

    # ── Google Custom Search API ───────────────────
    def _search_with_google_cse(self, keyword: str, num_results: int, exclude_url: str) -> dict:
        logger.info("Google CSEを使用: %s", keyword)
        params = {
            "key": self.google_api_key,
            "cx": self.google_cx,
            "q": keyword,
            "num": min(num_results, 10),
            "lr": "lang_ja",
            "gl": "jp",
        }
        try:
            resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=15)
            data = resp.json()

            urls = []
            for item in data.get("items", []):
                link = item.get("link", "")
                if link and link != exclude_url:
                    urls.append(link)

            # CSEはPAA/サジェストを返さないため空
            return {"urls": urls[:num_results], "paa": [], "suggestions": []}
        except Exception as e:
            logger.error("Google CSEエラー: %s — フォールバック", e)
            return self._search_with_googlesearch(keyword, num_results, exclude_url)

    # ── googlesearch-python（無料・フォールバック） ──
    def _search_with_googlesearch(self, keyword: str, num_results: int, exclude_url: str) -> dict:
        logger.info("googlesearch-pythonを使用: %s", keyword)
        urls = []
        try:
            from googlesearch import search as gsearch
            results = gsearch(keyword, num_results=num_results + 2, lang="ja")
            for url in results:
                if url != exclude_url:
                    urls.append(url)
                if len(urls) >= num_results:
                    break
        except ImportError:
            logger.error("googlesearch-pythonがインストールされていません")
        except Exception as e:
            logger.error("googlesearchエラー: %s", e)

        # PAA・サジェストは個別取得を試行
        paa = self._fetch_paa(keyword)
        suggestions = self._fetch_suggestions(keyword)

        return {"urls": urls[:num_results], "paa": paa, "suggestions": suggestions}

    # ── PAA取得（Google検索ページをスクレイプ） ──────
    def _fetch_paa(self, keyword: str) -> list[str]:
        """Google検索ページから「他の人はこちらも質問」を抽出"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            }
            resp = requests.get(
                f"https://www.google.com/search?q={keyword}&hl=ja&gl=jp",
                headers=headers,
                timeout=10,
            )
            soup = BeautifulSoup(resp.text, "lxml")

            paa = []
            # PAAセクションを探索
            for faq in soup.find_all("div", class_=lambda x: x and "related" in x.lower()):
                for item in faq.find_all(["h3", "div"], string=True):
                    text = item.get_text(strip=True)
                    if text and text.endswith("？") or text.endswith("?"):
                        paa.append(text)

            # 別パターン: data-attributeベース
            for el in soup.find_all(attrs={"data-q": True}):
                paa.append(el["data-q"])

            return list(dict.fromkeys(paa))[:8]  # 重複除去
        except Exception as e:
            logger.warning("PAA取得失敗: %s", e)
            return []

    # ── 関連サジェスト取得 ──────────────────────────
    def _fetch_suggestions(self, keyword: str) -> list[str]:
        """GoogleサジェストAPIから関連キーワードを取得"""
        try:
            resp = requests.get(
                f"https://suggestqueries.google.com/complete/search?client=firefox&hl=ja&q={keyword}",
                timeout=10,
            )
            data = resp.json()
            if len(data) >= 2 and isinstance(data[1], list):
                return data[1][:10]
        except Exception as e:
            logger.warning("サジェスト取得失敗: %s", e)
        return []
