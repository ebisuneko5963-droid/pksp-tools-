# -*- coding: utf-8 -*-
"""
GSC CSV ローダー
Search Consoleからエクスポートした各種CSVを読み込み、
共通形式のDataFrameに変換する。
"""
import pandas as pd
import io
import logging
import re

logger = logging.getLogger("gsc.loader")


class CSVLoader:
    """GSC CSVファイルを読み込み、正規化する"""

    # CSVタイプの自動判定
    CSV_TYPES = {
        "query": ["上位のクエリ"],
        "page": ["上位のページ"],
        "chart": ["日付"],
        "country": ["国"],
        "device": ["デバイス"],
        "appearance": ["検索での見え方"],
        "filter": ["フィルタ"],
    }

    def detect_type(self, content: str) -> str:
        """CSV内容から種類を自動判定する"""
        first_line = content.split("\n")[0]
        for csv_type, keywords in self.CSV_TYPES.items():
            for kw in keywords:
                if kw in first_line:
                    return csv_type
        return "unknown"

    def load_from_content(self, content: str, csv_type: str = None) -> dict:
        """
        CSV文字列を読み込み、{type, df} を返す

        Args:
            content: CSV文字列
            csv_type: 明示する場合（任意、なければ自動判定）
        """
        if csv_type is None:
            csv_type = self.detect_type(content)

        if csv_type == "unknown":
            logger.warning("CSV種別が判定できません")
            return {"type": "unknown", "df": None}

        try:
            df = pd.read_csv(io.StringIO(content))
            df = self._normalize(df)
            return {"type": csv_type, "df": df, "rows": len(df)}
        except Exception as e:
            logger.error(f"CSV読み込みエラー ({csv_type}): {e}")
            return {"type": csv_type, "df": None, "error": str(e)}

    def load_from_file(self, file_path: str, csv_type: str = None) -> dict:
        """ファイルパスから読み込み"""
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        return self.load_from_content(content, csv_type)

    def load_from_text(self, content: str, filename: str = "") -> dict:
        """テキスト内容＋ファイル名ヒントから読み込み（アップロード用）"""
        # ファイル名による判定優先（日本語ファイル名対応）
        name_lower = filename.lower() if filename else ""
        csv_type = None
        if "クエリ" in filename or "query" in name_lower:
            csv_type = "query"
        elif "ページ" in filename or "page" in name_lower:
            csv_type = "page"
        elif "チャート" in filename or "chart" in name_lower or "日付" in filename:
            csv_type = "chart"
        elif "国" in filename or "country" in name_lower:
            csv_type = "country"
        elif "デバイス" in filename or "device" in name_lower:
            csv_type = "device"
        return self.load_from_content(content, csv_type)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """共通の正規化（CTR を float に等）"""
        if "CTR" in df.columns:
            df["CTR"] = df["CTR"].astype(str).str.rstrip("%").str.strip()
            df["CTR"] = pd.to_numeric(df["CTR"], errors="coerce").fillna(0)
        if "クリック数" in df.columns:
            df["クリック数"] = pd.to_numeric(df["クリック数"], errors="coerce").fillna(0).astype(int)
        if "表示回数" in df.columns:
            df["表示回数"] = pd.to_numeric(df["表示回数"], errors="coerce").fillna(0).astype(int)
        if "掲載順位" in df.columns:
            df["掲載順位"] = pd.to_numeric(df["掲載順位"], errors="coerce")
        if "日付" in df.columns:
            df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        return df


class PeriodDataset:
    """1期間分のGSCデータ（query/page/chart/device/country）をまとめて保持"""

    def __init__(self, period_label: str):
        self.period_label = period_label  # "7日間" / "28日間" / "3か月"
        self.query = None       # クエリDF
        self.page = None        # ページDF
        self.chart = None       # 日次推移DF
        self.device = None      # デバイスDF
        self.country = None     # 国DF

    def set(self, csv_type: str, df: pd.DataFrame):
        if csv_type == "query":
            self.query = df
        elif csv_type == "page":
            self.page = df
        elif csv_type == "chart":
            self.chart = df
        elif csv_type == "device":
            self.device = df
        elif csv_type == "country":
            self.country = df

    @property
    def total_clicks(self) -> int:
        if self.chart is not None:
            return int(self.chart["クリック数"].sum())
        if self.query is not None:
            return int(self.query["クリック数"].sum())
        return 0

    @property
    def total_impressions(self) -> int:
        if self.chart is not None:
            return int(self.chart["表示回数"].sum())
        if self.query is not None:
            return int(self.query["表示回数"].sum())
        return 0

    @property
    def avg_ctr(self) -> float:
        if self.total_impressions == 0:
            return 0
        return round(self.total_clicks / self.total_impressions * 100, 2)

    @property
    def avg_position(self) -> float:
        if self.chart is not None and "掲載順位" in self.chart.columns:
            return round(self.chart["掲載順位"].mean(), 1)
        return 0

    @property
    def days(self) -> int:
        if self.chart is not None:
            return len(self.chart)
        return 0

    @property
    def daily_avg_clicks(self) -> float:
        if self.days == 0:
            return 0
        return round(self.total_clicks / self.days, 2)

    @property
    def daily_avg_impressions(self) -> float:
        if self.days == 0:
            return 0
        return round(self.total_impressions / self.days, 0)

    def has_data(self) -> bool:
        """このデータセットに有効なデータが含まれているか"""
        return any([
            self.query is not None,
            self.page is not None,
            self.chart is not None,
        ])

    def summary_dict(self) -> dict:
        return {
            "period_label": self.period_label,
            "days": self.days,
            "total_clicks": self.total_clicks,
            "total_impressions": self.total_impressions,
            "avg_ctr": self.avg_ctr,
            "avg_position": self.avg_position,
            "daily_avg_clicks": self.daily_avg_clicks,
            "daily_avg_impressions": self.daily_avg_impressions,
        }
