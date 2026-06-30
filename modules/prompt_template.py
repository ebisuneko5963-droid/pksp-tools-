# -*- coding: utf-8 -*-
"""
プロンプトテンプレートモジュール
パートBのLLM診断プロンプトを定義し、
クロール済みデータを {{ }} プレースホルダに流し込む。

このプロンプトはツールの「診断の中核」として使用され、
LLM (Claude / GPT) に送信される。
"""
import json
import logging
from textwrap import dedent

logger = logging.getLogger("factoring-diagnosis.prompt")


# ════════════════════════════════════════════════
# プロンプトテンプレート本体
# {{ }} 内はツールが取得したデータで置換される
# ════════════════════════════════════════════════

PROMPT_TEMPLATE = r"""あなたはYMYL領域（金融）専門のSEO編集者です。
ファクタリング情報サイト「pksp.jp」の記事を、検索上位を狙うために
リライト診断します。以下のデータを分析し、指定の形式で出力してください。

# 前提
- ファクタリングはYMYL領域であり、信頼性・専門性・正確性が最重要。
- このサイトの強みは執筆者が元都市銀行法人営業（八木健介氏）であること。
  リライトでは必ずこの「元銀行員ならではの一次情報・視点」を活かす。
- 競合のコピーは厳禁。不足論点は「pksp.jp独自の情報で埋める」前提で提案する。

# 入力データ
## 自社記事
- URL：{{own_url}}
- メインキーワード：{{keyword}}
- 記事の役割：{{role}}
- タイトル：{{own_title}}
- メタディスクリプション：{{own_meta_description}}
- 見出し構造：
{{own_headings}}
- 文字数：{{own_word_count}}
- 内部リンク：
{{own_internal_links}}
- 執筆者/出典/更新日の有無：{{own_eeat_status}}
- 画像数：{{own_image_count}} / 表数：{{own_table_count}}
- 本文：
{{own_body_text}}

## 競合上位記事（検索上位{{competitor_count}}件）
{{competitor_headings}}

## 検索ユーザーの疑問
- 他の人はこちらも質問(PAA)：
{{paa_list}}
- 関連サジェスト：
{{suggestion_list}}

# 分析タスク
1. 競合の見出しを横断し、上位の多くが扱うのに自社記事にない
   「不足トピック」を出現頻度順に抽出する。
2. PAA・サジェストのうち、自社記事が答えていない疑問を特定する。
3. 自社記事の数値・サービス情報のうち、古い可能性がある記述を
   「要ファクトチェック」として挙げる（正誤の断定はしない）。
4. E-E-A-T観点で弱い点（執筆者証明・出典・デメリット記載・
   誇大表現の有無）を指摘する。
5. 下記スコアリング基準で採点する。

# スコアリング基準（100点満点）
- トピック網羅率：25点
- E-E-A-T要素：25点
- タイトル最適化：10点
- 本文の網羅性・独自性：15点
- 内部リンク：10点
- CV導線（役割がCV/収益の場合）：10点
- 鮮度：5点

# 出力フォーマット（必ずこの形で）

## 診断レポート
- 総合スコア：◯◯/100
- 項目別スコア：（各項目の点数と一言コメント）
- 不足トピック TOP5：（論点名＋なぜ必要か＋pksp.jpならどう独自化するか）
- 要ファクトチェック項目：（該当箇所のリスト）
- 弱いE-E-A-T項目：（具体的な指摘）

## リライト指示書
■ 対象記事：{{own_url}}／メインKW：{{keyword}}／役割：{{role}}
■ リライトの目的：（現状の弱点を踏まえた一文）
■ ターゲット読者：（このキーワードで検索する人物像を1人に specifically）
■ 網羅すべき検索意図（追加する論点）：
　・（不足トピックを列挙。各々に「ここに元銀行員の一次情報を足す」と明記）
■ 必ず入れる独自要素：
　・元銀行員・八木氏の視点を各見出しに最低1つ
　・（記事に合った独自データ/実例の提案）
■ 事実・数値の更新：（要ファクトチェック項目を列挙）
■ E-E-A-T要件：（断定・誇大表現の禁止、出典明記、デメリット記載）
■ 構成・形式：（タイトル案、リード文方針、内部リンク、CTA位置）
■ してはいけないこと：（既存の良い部分を消さない／競合コピー禁止／KW詰め込み禁止）

# 注意
- 競合と同じ見出しを並べるだけの提案をしないこと。
- すべての改善提案に「pksp.jpらしい独自化（元銀行員視点・一次情報）」を必ず添えること。
- 数値の正誤は断定せず「要確認」とすること。
"""


class PromptBuilder:
    """クロールデータをプロンプトテンプレートに流し込む"""

    def build_prompt(self, own_article: dict, competitors: list[dict],
                     keyword: str, role: str,
                     paa_questions: list[str] = None,
                     related_suggestions: list[str] = None) -> str:
        """
        プロンプトテンプレートの {{ }} を実データで置換し、
        LLM に送信する完全プロンプトを生成する。

        Args:
            own_article: 自社記事のクロール結果
            competitors: 競合記事のクロール結果リスト
            keyword: メインキーワード
            role: 記事の役割（流入/CV/収益）
            paa_questions: PAA質問リスト
            related_suggestions: 関連サジェストリスト

        Returns:
            LLMに送信する完成プロンプト文字列
        """
        paa_questions = paa_questions or []
        related_suggestions = related_suggestions or []

        # ── 自社記事データのフォーマット ──
        own_headings_text = self._format_headings(own_article.get("headings", []))
        own_internal_links_text = self._format_internal_links(own_article.get("internal_links", []))
        own_eeat_status = self._format_eeat_status(own_article)
        own_body_text = self._truncate_body(own_article.get("body_text", ""), max_chars=8000)

        # ── 競合記事データのフォーマット ──
        competitor_headings_text = self._format_competitors(competitors)

        # ── PAA・サジェスト ──
        paa_text = "\n".join(f"  ・{q}" for q in paa_questions) if paa_questions else "  （取得できませんでした）"
        suggestion_text = "\n".join(f"  ・{s}" for s in related_suggestions) if related_suggestions else "  （取得できませんでした）"

        # ── プレースホルダ置換 ──
        replacements = {
            "own_url": own_article.get("url", ""),
            "keyword": keyword,
            "role": role,
            "own_title": own_article.get("title", "(取得失敗)"),
            "own_meta_description": own_article.get("meta_description", "(取得失敗)"),
            "own_headings": own_headings_text,
            "own_word_count": f"{own_article.get('word_count', 0):,}文字",
            "own_internal_links": own_internal_links_text,
            "own_eeat_status": own_eeat_status,
            "own_image_count": str(own_article.get("image_count", 0)),
            "own_table_count": str(own_article.get("table_count", 0)),
            "own_body_text": own_body_text,
            "competitor_count": str(len(competitors)),
            "competitor_headings": competitor_headings_text,
            "paa_list": paa_text,
            "suggestion_list": suggestion_text,
        }

        prompt = PROMPT_TEMPLATE
        for key, value in replacements.items():
            placeholder = "{{" + key + "}}"
            prompt = prompt.replace(placeholder, value)

        logger.info("プロンプト生成完了: %d文字", len(prompt))
        return prompt

    # ── フォーマットヘルパ ──────────────────────

    def _format_headings(self, headings: list[dict]) -> str:
        """見出しリストをインデント付きテキストに変換"""
        if not headings:
            return "  （見出し構造が取得できませんでした）"
        lines = []
        for h in headings:
            level = h.get("level", 2)
            indent = "  " * (level - 1) if level <= 3 else "      "
            lines.append(f"{indent}h{level}: {h.get('text', '')}")
        return "\n".join(lines)

    def _format_internal_links(self, links: list[dict]) -> str:
        """内部リンクリストをテキストに変換"""
        if not links:
            return "  （内部リンクが検出されませんでした）"
        lines = []
        for link in links:
            lines.append(f"  ・[{link.get('text', '')}] → {link.get('url', '')}")
        return "\n".join(lines)

    def _format_eeat_status(self, own_article: dict) -> str:
        """E-E-A-T関連情報の有無をテキストに変換"""
        author = own_article.get("author", "")
        sources = own_article.get("sources", [])
        updated = own_article.get("updated_date", "")
        has_demerits = own_article.get("has_demerits", False)

        parts = []
        parts.append(f"執筆者: {'あり（' + author[:30] + '）' if author else 'なし'}")
        if sources:
            source_names = ', '.join(s[:50] for s in sources[:3])
            parts.append(f"出典: あり（{len(sources)}件: {source_names}）")
        else:
            parts.append("出典: なし")
        parts.append(f"更新日: {'あり（' + updated[:30] + '）' if updated else 'なし'}")
        parts.append(f"デメリット記載: {'あり' if has_demerits else 'なし'}")
        return " / ".join(parts)

    def _truncate_body(self, body_text: str, max_chars: int = 8000) -> str:
        """本文が長すぎる場合はトランケート（LLMトークン制限対策）"""
        if len(body_text) <= max_chars:
            return body_text
        truncated = body_text[:max_chars]
        # 最後の完全な文で切る
        last_period = max(truncated.rfind("。"), truncated.rfind("．"), truncated.rfind("\n"))
        if last_period > max_chars * 0.8:
            truncated = truncated[:last_period + 1]
        return truncated + "\n\n（※ 本文が長いため最初の{}文字のみ表示。以降省略）".format(len(truncated))

    def _format_competitors(self, competitors: list[dict]) -> str:
        """競合記事リストをフォーマット"""
        if not competitors:
            return "（競合記事が取得できませんでした）"

        blocks = []
        for i, comp in enumerate(competitors, 1):
            url = comp.get("url", "")
            title = comp.get("title", "(タイトル取得失敗)")
            headings = comp.get("headings", [])
            word_count = comp.get("word_count", 0)

            heading_lines = []
            for h in headings:
                level = h.get("level", 2)
                indent = "    " * (level - 1) if level <= 3 else "        "
                heading_lines.append(f"{indent}h{level}: {h.get('text', '')}")

            block = f"""### 競合{i}: {title}
URL: {url}
文字数: {word_count:,}文字
見出し構造:
{chr(10).join(heading_lines) if heading_lines else "  （見出し取得失敗）"}"""
            blocks.append(block)

        return "\n\n".join(blocks)
