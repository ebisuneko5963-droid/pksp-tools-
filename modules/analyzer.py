# -*- coding: utf-8 -*-
"""
診断エンジン
自社記事と競合記事を比較し、スコアリング・不足トピック抽出・
鮮度チェック・E-E-A-T評価を行う。

スコアリング基準（100点満点・YMYL重み付け）:
  トピック網羅率     : 25点
  E-E-A-T要素        : 25点  ←重い
  タイトル最適化     : 10点
  本文の網羅性        : 15点
  内部リンク         : 10点
  CV導線             : 10点
  鮮度               :  5点
"""
import re
import logging
from collections import Counter
from datetime import datetime

logger = logging.getLogger("factoring-diagnosis.analyzer")


class DiagnosisEngine:
    """診断中核エンジン"""

    # ファクタリング領域の頻出論点マスタ（見出しクラスタリング用）
    TOPIC_PATTERNS = [
        ("ファクタリングの基礎・仕組み", [r"仕組み", r"とは", r"基礎", r"概要", r"初心者", r" 基本"]),
        ("手数料・料金", [r"手数料", r"料金", r"費用", r"コスト", r"相場", r"_rate"]),
        ("審査・通過率", [r"審査", r"通過", r"審査通過率", r"通りやすい", r"審査基準"]),
        ("即日・スピード", [r"即日", r"スピード", r"最短", r"早い", r"当日"]),
        ("2社間・3社間", [r"2社間", r"3社間", r"二者間", r"三者間"]),
        ("償却請求権", [r"償却", r"請求権", r"ノンリコース", r"With recourse", r"Without recourse"]),
        ("対象債権・業種", [r"対象", r"業種", r"債権", r"個人事業主", r"法人", r"フリーランス"]),
        ("必要書類", [r"書類", r"必要書類", r"準備するもの", r"提出"]),
        ("メリット", [r"メリット", r"利点", r"良い点", r"長所", r"良いところ"]),
        ("デメリット・リスク", [r"デメリット", r"注意点", r"リスク", r"欠点", r"注意", r"やめとけ"]),
        ("業者比較", [r"比較", r"おすすめ", r"ランキング", r"選び方", r"優良", r"業者"]),
        ("悪徳業者・詐欺", [r"悪徳", r"詐欺", r"トラブル", r"違法", r"グレーゾーン"]),
        ("銀行融資との比較", [r"銀行", r"融資", r"借入", r"審査が厳", r"ノンバンク"]),
        ("資金繰り改善", [r"資金繰り", r"キャッシュフロー", r"資金不足", r"つなぎ資金"]),
        ("契約・手続きの流れ", [r"契約", r"手続き", r"流れ", r"ステップ", r"手順"]),
        ("入金タイミング", [r"入金", r"振込", r"資金化", r"タイミング"]),
        ("税務・会計処理", [r"税務", r"会計", r"課税", r"経費", r"消費税", r"売掛債権"]),
        ("法律・規制", [r"法律", r"規制", r"貸金業法", r"割賦購入", r"債権譲渡登記"]),
        ("個人事業主向け", [r"個人事業主", r"フリーランス", r"個人"]),
        ("審査落ち・審査不可", [r"審査落ち", r"審査不可", r"通りにくい", r"却下"]),
        ("乗り換え・リファイナンス", [r"乗り換え", r"他社", r"リファイナンス", r"見直し"]),
        ("口コミ・評判", [r"口コミ", r"評判", r"レビュー", r"体験談", r"事例"]),
        ("Q&A・よくある質問", [r"よくある質問", r"FAQ", r"Q&A", r"質問"]),
        ("まとめ", [r"まとめ", r"結論", r"総括", r"最後に"]),
    ]

    # スコアリング重み
    SCORE_WEIGHTS = {
        "topic_coverage": 25,
        "eeat": 25,
        "title_optimization": 10,
        "body_comprehensiveness": 15,
        "internal_links": 10,
        "cv_funnel": 10,
        "freshness": 5,
    }

    def run_diagnosis(self, own_article: dict, competitors: list[dict],
                      keyword: str, role: str,
                      paa_questions: list[str] = None,
                      related_suggestions: list[str] = None) -> dict:
        """
        診断を実行し、スコア・不足トピック・弱点リストを返す

        Returns:
            {
                total_score: int,
                category_scores: {category: {score, max, details}},
                missing_topics: [{topic, competitor_coverage_count, competitor_urls}],
                freshness_issues: [{description, reason}],
                weak_eeat: [{item, status, recommendation}],
                title_analysis: {...},
                body_analysis: {...},
                link_analysis: {...},
                cv_analysis: {...},
                paa_coverage: {...},
            }
        """
        paa_questions = paa_questions or []
        related_suggestions = related_suggestions or []

        # ── 見出しクラスタリング ────────────────────
        own_topics = self._extract_topics_from_headings(own_article.get("headings", []))
        competitor_topic_map = {}  # {topic_name: [urls that have it]}
        for comp in competitors:
            comp_topics = self._extract_topics_from_headings(comp.get("headings", []))
            for topic in comp_topics:
                if topic not in competitor_topic_map:
                    competitor_topic_map[topic] = []
                competitor_topic_map[topic].append(comp["url"])

        # ── トピック網羅率 ──────────────────────────
        topic_result = self._score_topic_coverage(own_topics, competitor_topic_map, competitors)

        # ── E-E-A-T ────────────────────────────────
        eeat_result = self._score_eeat(own_article)

        # ── タイトル最適化 ──────────────────────────
        title_result = self._score_title(own_article.get("title", ""), keyword)

        # ── 本文の網羅性 ────────────────────────────
        body_result = self._score_body(own_article, competitors)

        # ── 内部リンク ──────────────────────────────
        link_result = self._score_internal_links(own_article)

        # ── CV導線 ──────────────────────────────────
        cv_result = self._score_cv_funnel(own_article, role)

        # ── 鮮度 ────────────────────────────────────
        freshness_result = self._score_freshness(own_article)

        # ── PAAカバー率 ─────────────────────────────
        paa_result = self._analyze_paa_coverage(own_article, paa_questions)

        # ── 合計スコア ──────────────────────────────
        category_scores = {
            "topic_coverage": {
                "score": topic_result["score"],
                "max": self.SCORE_WEIGHTS["topic_coverage"],
                "label": "トピック網羅率",
                "details": topic_result["details"],
            },
            "eeat": {
                "score": eeat_result["score"],
                "max": self.SCORE_WEIGHTS["eeat"],
                "label": "E-E-A-T要素",
                "details": eeat_result["details"],
            },
            "title_optimization": {
                "score": title_result["score"],
                "max": self.SCORE_WEIGHTS["title_optimization"],
                "label": "タイトル最適化",
                "details": title_result["details"],
            },
            "body_comprehensiveness": {
                "score": body_result["score"],
                "max": self.SCORE_WEIGHTS["body_comprehensiveness"],
                "label": "本文の網羅性",
                "details": body_result["details"],
            },
            "internal_links": {
                "score": link_result["score"],
                "max": self.SCORE_WEIGHTS["internal_links"],
                "label": "内部リンク",
                "details": link_result["details"],
            },
            "cv_funnel": {
                "score": cv_result["score"],
                "max": self.SCORE_WEIGHTS["cv_funnel"],
                "label": "CV導線",
                "details": cv_result["details"],
            },
            "freshness": {
                "score": freshness_result["score"],
                "max": self.SCORE_WEIGHTS["freshness"],
                "label": "鮮度",
                "details": freshness_result["details"],
            },
        }

        total_score = sum(c["score"] for c in category_scores.values())

        return {
            "total_score": total_score,
            "category_scores": category_scores,
            "missing_topics": topic_result["missing_topics"],
            "freshness_issues": freshness_result["issues"],
            "weak_eeat": eeat_result["weak_items"],
            "title_analysis": title_result,
            "body_analysis": body_result,
            "link_analysis": link_result,
            "cv_analysis": cv_result,
            "paa_coverage": paa_result,
            "own_topics": own_topics,
            "competitor_topics": list(competitor_topic_map.keys()),
            "paa_questions": paa_questions,
            "related_suggestions": related_suggestions,
        }

    # ════════════════════════════════════════════════
    # トピック抽出・クラスタリング
    # ════════════════════════════════════════════════

    def _extract_topics_from_headings(self, headings: list[dict]) -> list[str]:
        """見出しリストから論点名（クラスタ名）を抽出"""
        topics = set()
        for h in headings:
            text = h.get("text", "")
            for topic_name, patterns in self.TOPIC_PATTERNS:
                if any(re.search(pat, text, re.IGNORECASE) for pat in patterns):
                    topics.add(topic_name)
        return list(topics)

    # ════════════════════════════════════════════════
    # スコアリング: トピック網羅率 (25点)
    # ════════════════════════════════════════════════

    def _score_topic_coverage(self, own_topics: list[str],
                              competitor_topic_map: dict,
                              competitors: list[dict]) -> dict:
        total_competitors = max(len(competitors), 1)

        # 競合が扱っている全トピック
        all_comp_topics = set(competitor_topic_map.keys())
        if not all_comp_topics:
            return {
                "score": self.SCORE_WEIGHTS["topic_coverage"],
                "details": "競合記事が取得できなかったため、満点扱い",
                "missing_topics": [],
            }

        # 自社が押さえているトピック
        covered = set(own_topics) & all_comp_topics
        coverage_ratio = len(covered) / len(all_comp_topics)

        # 不足トピック（出現頻度順）
        missing = []
        for topic in all_comp_topics:
            if topic not in own_topics:
                comp_urls = competitor_topic_map[topic]
                missing.append({
                    "topic": topic,
                    "competitor_coverage_count": len(comp_urls),
                    "competitor_coverage_ratio": round(len(comp_urls) / total_competitors, 2),
                    "competitor_urls": comp_urls[:5],
                })
        missing.sort(key=lambda x: x["competitor_coverage_count"], reverse=True)

        score = round(coverage_ratio * self.SCORE_WEIGHTS["topic_coverage"])

        return {
            "score": score,
            "details": f"競合が扱う{len(all_comp_topics)}論点中、自社がカバー:{len(covered)}（網羅率{coverage_ratio:.0%}）",
            "missing_topics": missing[:10],
        }

    # ════════════════════════════════════════════════
    # スコアリング: E-E-A-T (25点) ← 重い
    # ════════════════════════════════════════════════

    def _score_eeat(self, own_article: dict) -> dict:
        """
        E-E-A-T要素:
          1. 執筆者明示 (7点)
          2. 出典明記 (7点)
          3. 更新日 (6点)
          4. デメリット記載 (5点)
        """
        weak_items = []
        score = 0
        details_parts = []

        # 1. 執筆者明示 (7点)
        author = own_article.get("author", "")
        if author:
            score += 7
            details_parts.append(f"執筆者: {author[:30]} ✓")
        else:
            weak_items.append({
                "item": "執筆者情報の明示",
                "status": "未検出",
                "recommendation": "執筆者名・資格・プロフィールを明記。YMYL領域では専門性の証明が必須。",
            })
            details_parts.append("執筆者: 未検出 ✗")

        # 2. 出典明記 (7点)
        sources = own_article.get("sources", [])
        if sources:
            score += 7
            details_parts.append(f"出典: {len(sources)}件 ✓")
        else:
            weak_items.append({
                "item": "出典・参照元の明記",
                "status": "未検出",
                "recommendation": "金融庁・法務省等の公式ソース、法的根拠（条文等）へのリンクを明記。",
            })
            details_parts.append("出典: 未検出 ✗")

        # 3. 更新日 (6点)
        updated = own_article.get("updated_date", "")
        if updated:
            score += 6
            details_parts.append(f"更新日: {updated[:30]} ✓")
        else:
            weak_items.append({
                "item": "更新日の明示",
                "status": "未検出",
                "recommendation": "最終更新日を明記。YMYL領域では情報の鮮度が信頼性に直結。",
            })
            details_parts.append("更新日: 未検出 ✗")

        # 4. デメリット記載 (5点)
        if own_article.get("has_demerits"):
            score += 5
            details_parts.append("デメリット記載: あり ✓")
        else:
            weak_items.append({
                "item": "デメリット・注意点の記載",
                "status": "未検出",
                "recommendation": "手数料の高さ・償却請求リスク・悪徳業者の存在等、デメリットを必ず記載。",
            })
            details_parts.append("デメリット記載: 未検出 ✗")

        return {
            "score": score,
            "details": " / ".join(details_parts),
            "weak_items": weak_items,
        }

    # ════════════════════════════════════════════════
    # スコアリング: タイトル最適化 (10点)
    # ════════════════════════════════════════════════

    def _score_title(self, title: str, keyword: str) -> dict:
        """
        1. キーワード前方配置 (4点)
        2. 文字数32文字前後 (3点)
        3. 数字含有 (3点)
        """
        if not title:
            return {"score": 0, "details": "タイトル取得失敗", "title": "", "issues": ["タイトルが取得できませんでした"]}

        score = 0
        issues = []
        title_len = len(title)

        # 1. キーワード前方配置 (4点)
        # キーワードが前半（前から60%以内）に配置されているか
        keyword_pos = title.find(keyword)
        if keyword_pos == -1:
            # キーワードの一部（形態素レベル）をチェック
            keyword_parts = keyword.split()
            found_pos = -1
            for part in keyword_parts:
                pos = title.find(part)
                if pos != -1:
                    found_pos = pos if found_pos == -1 else min(found_pos, pos)
            keyword_pos = found_pos

        if keyword_pos >= 0:
            if keyword_pos <= len(title) * 0.4:
                score += 4
            elif keyword_pos <= len(title) * 0.6:
                score += 2
                issues.append(f"キーワード「{keyword}」がやや後方（{keyword_pos}文字目）に配置")
            else:
                score += 1
                issues.append(f"キーワード「{keyword}」が後方に配置（{keyword_pos}文字目）。前方配置を推奨")
        else:
            issues.append(f"キーワード「{keyword}」がタイトルに含まれていない可能性")

        # 2. 文字数32文字前後 (3点)
        if 28 <= title_len <= 40:
            score += 3
        elif 25 <= title_len <= 45:
            score += 2
            issues.append(f"タイトル文字数{title_len}文字（推奨28-40文字）")
        else:
            score += 0
            if title_len < 25:
                issues.append(f"タイトルが短い（{title_len}文字）。28-40文字を推奨")
            else:
                issues.append(f"タイトルが長い（{title_len}文字）。28-40文字を推奨（検索結果で省略される可能性）")

        # 3. 数字含有 (3点)
        if re.search(r"\d", title):
            score += 3
        else:
            issues.append("タイトルに数字なし。数字入りタイトルはCTR向上が期待できる")

        return {
            "score": score,
            "details": f"「{title[:40]}...」({title_len}文字) — {score}/10点",
            "title": title,
            "title_length": title_len,
            "issues": issues,
        }

    # ════════════════════════════════════════════════
    # スコアリング: 本文の網羅性 (15点)
    # ════════════════════════════════════════════════

    def _score_body(self, own_article: dict, competitors: list[dict]) -> dict:
        own_wc = own_article.get("word_count", 0)
        comp_wcs = [c.get("word_count", 0) for c in competitors if c.get("word_count", 0) > 0]

        score = 0
        issues = []

        if not comp_wcs:
            # 競合データがない場合の基準評価
            if own_wc >= 3000:
                score = 15
            elif own_wc >= 2000:
                score = 10
            elif own_wc >= 1000:
                score = 7
            else:
                score = 3
                issues.append(f"文字数{own_wc}文字は少なめ。YMYL領域では2,000-5,000文字以上が目安")
            return {
                "score": score,
                "details": f"文字数{own_wc:,}（競合比較データなし、絶対基準で評価）",
                "word_count": own_wc,
                "competitor_avg": 0,
                "issues": issues,
            }

        avg_wc = sum(comp_wcs) / len(comp_wcs)
        median_wc = sorted(comp_wcs)[len(comp_wcs) // 2]
        max_wc = max(comp_wcs)

        # 競合平均との比較 (10点)
        ratio = own_wc / avg_wc if avg_wc > 0 else 0
        if ratio >= 1.0:
            score += 10
        elif ratio >= 0.8:
            score += 7
            issues.append(f"競合平均{avg_wc:,.0f}文字に対し自社{own_wc:,}文字（{ratio:.0%}）。あと{int(avg_wc - own_wc):,}文字程度追加を検討")
        elif ratio >= 0.6:
            score += 4
            issues.append(f"競合平均{avg_wc:,.0f}文字に対し自社{own_wc:,}文字（{ratio:.0%}）。大幅な加筆を推奨")
        else:
            score += 1
            issues.append(f"競合平均{avg_wc:,.0f}文字に対し自社{own_wc:,}文字（{ratio:.0%}）。内容の大幅拡充が必要")

        # 独自情報の有無（表・画像の有無で簡易判定）(5点)
        has_tables = own_article.get("table_count", 0) > 0
        has_images = own_article.get("image_count", 0) > 0
        has_unique = has_tables or has_images

        if has_tables and has_images:
            score += 5
        elif has_tables or has_images:
            score += 3
            if not has_tables:
                issues.append("表が未使用。比較表・シミュレーション表など独自コンテンツの追加を推奨")
            if not has_images:
                issues.append("画像が未使用（または少ない）。図解・イラストで理解度向上を推奨")
        else:
            score += 0
            issues.append("表・画像ともに未使用。独自コンテンツ（比較表・図解・事例）の追加を強く推奨")

        return {
            "score": score,
            "details": f"文字数{own_wc:,}（競合平均{avg_wc:,.0f}文字、比{ratio:.0%}）/ 表{own_article.get('table_count',0)}・画像{own_article.get('image_count',0)}",
            "word_count": own_wc,
            "competitor_avg": round(avg_wc),
            "competitor_median": median_wc,
            "competitor_max": max_wc,
            "ratio": round(ratio, 2),
            "issues": issues,
        }

    # ════════════════════════════════════════════════
    # スコアリング: 内部リンク (10点)
    # ════════════════════════════════════════════════

    def _score_internal_links(self, own_article: dict) -> dict:
        links = own_article.get("internal_links", [])
        link_count = len(links)
        score = 0
        issues = []

        # リンク数による評価
        if link_count >= 10:
            score += 5
        elif link_count >= 5:
            score += 4
        elif link_count >= 3:
            score += 2
            issues.append(f"内部リンク{link_count}本。関連記事・ピラーページへの導線を増やすことを推奨（目安5-10本）")
        else:
            score += 0
            issues.append(f"内部リンク{link_count}本のみ。YMYL領域では関連コンテンツへの導線がE-E-A-T強化に寄与。5本以上を推奨")

        # ピラーページ・ハブページへの導線チェック
        pillar_indicators = []
        for link in links:
            text = link.get("text", "").lower()
            url = link.get("url", "").lower()
            if any(kw in text or kw in url for kw in ["基礎", "とは", "初心者", "ガイド", "まとめ", "一覧", "基礎知識"]):
                pillar_indicators.append(link)

        if pillar_indicators:
            score += 5
        else:
            score += 2
            issues.append("ピラーページ（基礎・総括ページ）へのリンクが未確認。サイト内回遊強化を推奨")

        return {
            "score": score,
            "details": f"内部リンク{link_count}本（ピラーページ導線{'あり' if pillar_indicators else '未確認'}）",
            "link_count": link_count,
            "pillar_links": pillar_indicators,
            "issues": issues,
        }

    # ════════════════════════════════════════════════
    # スコアリング: CV導線 (10点)
    # ════════════════════════════════════════════════

    def _score_cv_funnel(self, own_article: dict, role: str) -> dict:
        body_text = own_article.get("body_text", "")
        score = 0
        issues = []

        if role == "流入":
            # 流入記事はCV導線の比重を下げる（内部リンクで評価済みのため）
            # 最低限のCTAがあればOK
            if self._has_cta(body_text):
                score += 7
            else:
                score += 3
                issues.append("流入記事でも簡易CTA（「詳細はこちら」「お問い合わせ」等）の設置を推奨")
            # 関連導線
            links = own_article.get("internal_links", [])
            if len(links) >= 3:
                score += 3
            else:
                issues.append("関連記事への導線が少ない。CV・収益ページへの回遊導線を強化を推奨")
        else:
            # CV / 収益記事 — 厳しく評価
            if self._has_application_button(body_text):
                score += 5
            else:
                issues.append("申込ボタン・CTAが未検出。「申し込む」「無料診断」「お問い合わせ」等の明確なCTAを設置")

            if self._has_official_link(body_text, own_article.get("internal_links", [])):
                score += 3
            else:
                issues.append("公式リンク・申込フォームへの導線が未確認。コンバージョン導線を明確に")

            if self._has_multiple_cta(body_text):
                score += 2
            else:
                issues.append("CTAが1箇所のみの可能性。記事上部・中部・下部の3箇所設置を推奨")

        # 流入以外でスコアが低い場合、追加調整
        if role != "流入" and score < 4:
            issues.append("CV導線が著しく弱い。リライト時にCTA設計を見直すことを強く推奨")

        return {
            "score": score,
            "details": f"役割: {role} — CTA{'検出' if self._has_cta(body_text) else '未検出'}",
            "issues": issues,
        }

    def _has_cta(self, text: str) -> bool:
        cta_keywords = ["申し込", "申込", "お問い合わせ", "お問合せ", "無料", "診断", "相談", "見積", "資料請求", "click", "cta", "詳細はこちら", "もっと詳しく"]
        return any(kw in text.lower() for kw in cta_keywords)

    def _has_application_button(self, text: str) -> bool:
        app_keywords = ["申し込む", "申込む", "今すぐ申し込", "無料で申し込", "お申し込み", "apply", "お問い合わせする", "相談する", "見積もりを取"]
        return any(kw in text for kw in app_keywords)

    def _has_official_link(self, text: str, links: list[dict]) -> bool:
        # 本文に公式を示す記述、またはリンク先にform/contactが含まれる
        if any(kw in text for kw in ["公式", "公式サイト", "公式ページ", "フォーム"]):
            return True
        for link in links:
            url = link.get("url", "").lower()
            if any(kw in url for kw in ["form", "contact", "apply", "inquiry", "consult"]):
                return True
        return False

    def _has_multiple_cta(self, text: str) -> bool:
        # CTA関連キーワードの出現回数で判定
        cta_keywords = ["申し込", "申込", "お問い合わせ", "お問合せ", "相談", "見積", "資料請求", "診断"]
        count = sum(1 for kw in cta_keywords if kw in text)
        return count >= 3

    # ════════════════════════════════════════════════
    # スコアリング: 鮮度 (5点)
    # ════════════════════════════════════════════════

    def _score_freshness(self, own_article: dict) -> dict:
        """
        数値・サービス情報が最新かを簡易チェック。
        数値の正誤は断定せず「要確認」フラグとする。
        """
        score = 0
        issues = []

        body_text = own_article.get("body_text", "")
        updated_date = own_article.get("updated_date", "")

        # 更新日が新しいか (3点)
        if updated_date:
            year_match = re.search(r"20(2\d)", updated_date)
            if year_match:
                year = int("20" + year_match.group(1))
                current_year = datetime.now().year
                if year >= current_year - 1:
                    score += 3
                elif year >= current_year - 2:
                    score += 2
                    issues.append({"description": f"更新日が{year}年。半年以上更新がない可能性。最新情報への更新を推奨", "reason": "更新日が古い"})
                else:
                    score += 0
                    issues.append({"description": f"更新日が{year}年。YMYL領域では最新情報の維持が重要", "reason": "更新日が古い"})
            else:
                score += 1
                issues.append({"description": f"更新日「{updated_date[:30]}」から年が特定できない。明確な日付表記を推奨", "reason": "更新日が不明瞭"})
        else:
            score += 0
            issues.append({"description": "更新日が未検出。最終更新日を明記し、最新情報であることを示すべき", "reason": "更新日なし"})

        # 数値含有 (2点) — 数値があれば「要ファクトチェック」として記録
        if own_article.get("has_numbers"):
            score += 2
            # 数値箇所を抽出して「要確認」フラグ
            number_issues = self._extract_number_mentions(body_text)
            issues.extend(number_issues)
        else:
            issues.append({"description": "具体的な数値（手数料率・金額等）が未検出。ファクタリング記事では数値提示が信頼性に直結", "reason": "数値なし"})

        return {
            "score": min(score, self.SCORE_WEIGHTS["freshness"]),
            "details": f"更新日: {updated_date[:20] if updated_date else '未検出'} / 数値: {'あり' if own_article.get('has_numbers') else 'なし'}",
            "issues": issues,
        }

    def _extract_number_mentions(self, text: str) -> list[dict]:
        """本文から数値記述を抽出し「要ファクトチェック」項目として返す"""
        issues = []
        patterns = [
            (r"(\d+\.?\d*)\s*[%％]\s*(?:の手数料|の手数料|前後|程度)?", "手数料率"),
            (r"手数料(?:は|が)?\s*(\d+\.?\d*)\s*[%％]", "手数料率"),
            (r"(\d{1,3}(?:,\d{3})*)\s*円", "金額"),
            (r"最短(\d+)日", "入金日数"),
            (r"即日", "即日入金"),
            (r"(\d+\.?\d*)\s*倍", "倍率"),
            (r"審査通過率\s*(\d+\.?\d*)\s*[%％]", "審査通過率"),
        ]
        seen = set()
        for pat, label in patterns:
            for m in re.finditer(pat, text):
                snippet = text[max(0, m.start() - 20):m.end() + 20].replace("\n", " ").strip()
                if snippet not in seen:
                    seen.add(snippet)
                    issues.append({
                        "description": f"[{label}] 「{snippet}」 — 公式ソースで最新数値を確認してください",
                        "reason": f"数値の鮮度要確認: {label}",
                        "snippet": snippet,
                        "type": label,
                    })
        return issues[:10]  # 最大10件

    # ════════════════════════════════════════════════
    # PAAカバー率分析
    # ════════════════════════════════════════════════

    def _analyze_paa_coverage(self, own_article: dict, paa_questions: list[str]) -> dict:
        if not paa_questions:
            return {"total": 0, "covered": 0, "uncovered": [], "coverage_ratio": 0}

        body_text = own_article.get("body_text", "")
        headings_text = " ".join(h.get("text", "") for h in own_article.get("headings", []))
        full_text = body_text + " " + headings_text

        covered = []
        uncovered = []
        for q in paa_questions:
            # 質問のキーワードが本文に含まれるか簡易判定
            q_keywords = self._extract_query_keywords(q)
            if any(kw in full_text for kw in q_keywords):
                covered.append(q)
            else:
                uncovered.append(q)

        return {
            "total": len(paa_questions),
            "covered": len(covered),
            "uncovered": uncovered,
            "coverage_ratio": round(len(covered) / len(paa_questions), 2) if paa_questions else 0,
        }

    def _extract_query_keywords(self, query: str) -> list[str]:
        """質問文から検索用キーワードを抽出（簡易形態素分析）"""
        # 助詞・助動詞等を除去
        stop_words = ["は", "が", "を", "に", "で", "と", "の", "から", "まで", "より", "について", "か", "です", "ます", "れる", "られる", "どう", "なぜ", "どの", "どんな", "どこ", "いつ", "誰"]
        text = query.rstrip("？?")
        for sw in stop_words:
            text = text.replace(sw, " ")
        parts = [p.strip() for p in text.split() if len(p.strip()) >= 2]
        if not parts:
            parts = [query]
        return parts
