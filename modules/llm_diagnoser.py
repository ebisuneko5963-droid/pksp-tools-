# -*- coding: utf-8 -*-
"""
LLM 診断モジュール
プロンプトテンプレートにデータを流し込み、LLM API（OpenAI / Anthropic）に
送信して診断レポート＋リライト指示書を取得する。

APIキーが設定されていない場合はルールベース診断にフォールバックする。
"""
import os
import re
import json
import logging
import requests

from modules.prompt_template import PromptBuilder
from modules.analyzer import DiagnosisEngine

logger = logging.getLogger("factoring-diagnosis.llm")


class LLMDiagnoser:
    """
    LLM API を呼び出して記事診断を実行する。
    OpenAI (GPT-4) / Anthropic (Claude) の両方に対応。
    APIキー未設定時はルールベース診断にフォールバック。
    """

    def __init__(self):
        self.prompt_builder = PromptBuilder()
        self.rule_engine = DiagnosisEngine()

        # API設定を環境変数から読み込み
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        # モデル名（デフォルト: 各社最新高性能モデル）
        self.openai_model = os.environ.get("LLM_MODEL_OPENAI", "gpt-4o")
        self.anthropic_model = os.environ.get("LLM_MODEL_ANTHROPIC", "claude-sonnet-4-20250514")
        # タイムアウト
        self.timeout = int(os.environ.get("LLM_TIMEOUT", "120"))

    @property
    def is_available(self) -> bool:
        """LLM APIが利用可能か"""
        return bool(self.openai_api_key or self.anthropic_api_key)

    @property
    def provider(self) -> str:
        """使用するプロバイダ名"""
        if self.anthropic_api_key:
            return "anthropic"
        elif self.openai_api_key:
            return "openai"
        return "none"

    def diagnose(self, own_article: dict, competitors: list[dict],
                 keyword: str, role: str,
                 paa_questions: list[str] = None,
                 related_suggestions: list[str] = None) -> dict:
        """
        診断を実行する。

        LLM API利用可能 → LLM診断
        LLM API不可    → ルールベース診断（フォールバック）

        Returns:
            {
                mode: "llm" | "rule_based",
                provider: "openai" | "anthropic" | "none",
                llm_response: str (LLMの場合の生レスポンス),
                diagnosis_report: str (第1部: 診断レポート),
                rewrite_instructions: str (第2部: リライト指示書),
                rule_based_diagnosis: dict (フォールバック時のルールベース結果),
                error: str | None
            }
        """
        paa_questions = paa_questions or []
        related_suggestions = related_suggestions or []

        if not self.is_available:
            logger.info("LLM APIキー未設定 — ルールベース診断にフォールバック")
            return self._fallback_to_rule_based(
                own_article, competitors, keyword, role,
                paa_questions, related_suggestions
            )

        # ── プロンプト生成 ──
        prompt = self.prompt_builder.build_prompt(
            own_article=own_article,
            competitors=competitors,
            keyword=keyword,
            role=role,
            paa_questions=paa_questions,
            related_suggestions=related_suggestions,
        )
        logger.info("LLMプロンプト生成: %d文字 (provider=%s)", len(prompt), self.provider)

        # ── LLM API呼び出し ──
        try:
            if self.provider == "anthropic":
                raw_response = self._call_anthropic(prompt)
            else:
                raw_response = self._call_openai(prompt)

            if not raw_response:
                logger.warning("LLMレスポンスが空 — フォールバック")
                return self._fallback_to_rule_based(
                    own_article, competitors, keyword, role,
                    paa_questions, related_suggestions,
                    error="LLMレスポンスが空でした"
                )

            # ── レスポンスを第1部・第2部に分割 ──
            report_part, instructions_part = self._split_response(raw_response)

            # ── スコア抽出（LLM出力から数値をパース） ──
            scores = self._extract_scores(raw_response)

            return {
                "mode": "llm",
                "provider": self.provider,
                "model": self.anthropic_model if self.provider == "anthropic" else self.openai_model,
                "llm_response": raw_response,
                "diagnosis_report": report_part,
                "rewrite_instructions": instructions_part,
                "extracted_scores": scores,
                "rule_based_diagnosis": None,
                "error": None,
            }

        except Exception as e:
            logger.error("LLM APIエラー: %s — フォールバック", e)
            return self._fallback_to_rule_based(
                own_article, competitors, keyword, role,
                paa_questions, related_suggestions,
                error=str(e)
            )

    # ════════════════════════════════════════════════
    # OpenAI API 呼び出し
    # ════════════════════════════════════════════════

    def _call_openai(self, prompt: str) -> str:
        """OpenAI Chat Completions API を呼び出す"""
        logger.info("OpenAI API呼び出し: model=%s", self.openai_model)

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": "あなたはYMYL領域（金融）専門のSEO編集者です。指示に従い、正確で実用的な診断レポートとリライト指示書を作成してください。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # 分析系タスクなので低めに設定
            "max_tokens": 4096,
        }

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("OpenAI応答: %d文字", len(content))
        return content

    # ════════════════════════════════════════════════
    # Anthropic API 呼び出し
    # ════════════════════════════════════════════════

    def _call_anthropic(self, prompt: str) -> str:
        """Anthropic Messages API を呼び出す"""
        logger.info("Anthropic API呼び出し: model=%s", self.anthropic_model)

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.anthropic_model,
            "max_tokens": 4096,
            "system": "あなたはYMYL領域（金融）専門のSEO編集者です。指示に従い、正確で実用的な診断レポートとリライト指示書を作成してください。",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
        }

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        # Anthropic のレスポンス形式: data["content"][0]["text"]
        content = data["content"][0]["text"]
        logger.info("Anthropic応答: %d文字", len(content))
        return content

    # ════════════════════════════════════════════════
    # レスポンス解析
    # ════════════════════════════════════════════════

    def _split_response(self, response: str) -> tuple[str, str]:
        """
        LLMレスポンスを第1部（診断レポート）と第2部（リライト指示書）に分割。

        プロンプトの出力フォーマットに従い、
        "## 診断レポート" → "## リライト指示書" で分割する。
        """
        # 分割マーカーを探す（複数パターンに対応）
        split_patterns = [
            r"##\s*リライト指示書",
            r"■\s*リライト指示書",
            r"#\s*リライト指示書",
            r"リライト指示書",
        ]

        split_pos = -1
        for pat in split_patterns:
            m = re.search(pat, response)
            if m:
                split_pos = m.start()
                break

        if split_pos > 0:
            report_part = response[:split_pos].strip()
            instructions_part = response[split_pos:].strip()
        else:
            # 分割できない場合は全体をレポートとして返す
            report_part = response.strip()
            instructions_part = "（リライト指示書のセクションが見つかりませんでした。LLMレスポンス全体を確認してください。）"

        return report_part, instructions_part

    def _extract_scores(self, response: str) -> dict:
        """
        LLMレスポンスからスコアを抽出する。
        「総合スコア：◯◯/100」や「トピック網羅率：25点」等のパターンをパース。

        Returns:
            {
                total_score: int | None,
                category_scores: {category_name: score},
            }
        """
        scores = {"total_score": None, "category_scores": {}}

        # 総合スコア
        total_match = re.search(r"総合スコア[：:]\s*(\d+)\s*/\s*100", response)
        if total_match:
            scores["total_score"] = int(total_match.group(1))

        # 各項目スコア（複数表現に対応）
        category_patterns = [
            (r"トピック網羅率[：:]\s*(\d+)\s*点?", "topic_coverage"),
            (r"E-E-A-T要素?[：:]\s*(\d+)\s*点?", "eeat"),
            (r"タイトル最適化[：:]\s*(\d+)\s*点?", "title_optimization"),
            (r"本文の網羅性(?:・独自性)?[：:]\s*(\d+)\s*点?", "body_comprehensiveness"),
            (r"内部リンク[：:]\s*(\d+)\s*点?", "internal_links"),
            (r"CV導線[：:]\s*(\d+)\s*点?", "cv_funnel"),
            (r"鮮度[：:]\s*(\d+)\s*点?", "freshness"),
        ]
        for pat, key in category_patterns:
            m = re.search(pat, response)
            if m:
                scores["category_scores"][key] = int(m.group(1))

        return scores

    # ════════════════════════════════════════════════
    # フォールバック
    # ════════════════════════════════════════════════

    def _fallback_to_rule_based(self, own_article: dict, competitors: list[dict],
                                keyword: str, role: str,
                                paa_questions: list[str],
                                related_suggestions: list[str],
                                error: str = None) -> dict:
        """ルールベース診断にフォールバック"""
        diagnosis = self.rule_engine.run_diagnosis(
            own_article=own_article,
            competitors=competitors,
            keyword=keyword,
            role=role,
            paa_questions=paa_questions,
            related_suggestions=related_suggestions,
        )
        return {
            "mode": "rule_based",
            "provider": "none",
            "model": None,
            "llm_response": None,
            "diagnosis_report": None,
            "rewrite_instructions": None,
            "extracted_scores": None,
            "rule_based_diagnosis": diagnosis,
            "error": error,
        }
