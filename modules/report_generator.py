# -*- coding: utf-8 -*-
"""
レポート & リライト指示書ジェネレーター
診断結果を画面表示用JSONとリライト指示書テキストに変換する。
"""
import logging
from datetime import datetime

logger = logging.getLogger("factoring-diagnosis.report")


class ReportBuilder:
    """診断レポート + リライト指示書を生成"""

    def build(self, diagnosis: dict, own_article: dict,
              competitors: list[dict], keyword: str, role: str) -> dict:
        """ルールベース診断の完全レポートを構築"""
        return {
            "diagnosis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_mode": "rule_based",
            "input": {
                "url": own_article.get("url", ""),
                "keyword": keyword,
                "role": role,
                "title": own_article.get("title", ""),
                "meta_description": own_article.get("meta_description", ""),
            },
            "part1_report": self._build_part1(diagnosis, own_article, competitors, keyword),
            "part2_instructions": self._build_part2(diagnosis, own_article, competitors, keyword, role),
            "raw_data": {
                "own_headings": own_article.get("headings", []),
                "competitor_count": len(competitors),
                "competitor_urls": [c.get("url", "") for c in competitors],
                "own_word_count": own_article.get("word_count", 0),
            },
        }

    def build_llm_report(self, llm_result: dict, own_article: dict,
                         competitors: list[dict], keyword: str, role: str,
                         total_score: int, category_scores: dict) -> dict:
        """LLM診断結果の完全レポートを構築"""
        # LLM出力からスコア情報を構築
        score_labels = {
            "topic_coverage": ("トピック網羅率", 25),
            "eeat": ("E-E-A-T要素", 25),
            "title_optimization": ("タイトル最適化", 10),
            "body_comprehensiveness": ("本文の網羅性", 15),
            "internal_links": ("内部リンク", 10),
            "cv_funnel": ("CV導線", 10),
            "freshness": ("鮮度", 5),
        }
        formatted_scores = {}
        for key, (label, max_score) in score_labels.items():
            score = category_scores.get(key, 0)
            formatted_scores[key] = {
                "score": score,
                "max": max_score,
                "label": label,
                "details": "LLM評価",
            }

        return {
            "diagnosis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_mode": "llm",
            "llm_info": {
                "provider": llm_result.get("provider", ""),
                "model": llm_result.get("model", ""),
            },
            "input": {
                "url": own_article.get("url", ""),
                "keyword": keyword,
                "role": role,
                "title": own_article.get("title", ""),
                "meta_description": own_article.get("meta_description", ""),
            },
            "part1_report": {
                "total_score": total_score,
                "grade": self._get_grade(total_score),
                "category_scores": formatted_scores,
                "weak_categories": [
                    {
                        "category": key,
                        "label": val["label"],
                        "score": val["score"],
                        "max": val["max"],
                        "ratio": round(val["score"] / val["max"], 2) if val["max"] > 0 else 0,
                    }
                    for key, val in formatted_scores.items()
                    if val["score"] / val["max"] < 0.6 if val["max"] > 0
                ],
                "llm_report_text": llm_result.get("diagnosis_report", ""),
                # ルールベース要素も補助的に提供
                "missing_topics_top5": [],
                "freshness_issues": [],
                "weak_eeat": [],
                "paa_coverage": {"total": 0, "covered": 0, "uncovered": [], "coverage_ratio": 0},
                "competitor_summary": {
                    "count": len(competitors),
                    "avg_word_count": round(sum(c.get("word_count", 0) for c in competitors) / max(len(competitors), 1)),
                    "urls": [c.get("url", "") for c in competitors],
                },
            },
            "part2_instructions": llm_result.get("rewrite_instructions", ""),
            "raw_data": {
                "own_headings": own_article.get("headings", []),
                "competitor_count": len(competitors),
                "competitor_urls": [c.get("url", "") for c in competitors],
                "own_word_count": own_article.get("word_count", 0),
            },
        }

    # ════════════════════════════════════════════════
    # 第1部: 診断レポート
    # ════════════════════════════════════════════════

    def _build_part1(self, diagnosis: dict, own_article: dict,
                     competitors: list[dict], keyword: str) -> dict:
        scores = diagnosis["category_scores"]

        # 弱い項目を特定（満点の60%未満）
        weak_categories = []
        for key, val in scores.items():
            ratio = val["score"] / val["max"] if val["max"] > 0 else 0
            if ratio < 0.6:
                weak_categories.append({
                    "category": key,
                    "label": val["label"],
                    "score": val["score"],
                    "max": val["max"],
                    "ratio": round(ratio, 2),
                })

        return {
            "total_score": diagnosis["total_score"],
            "grade": self._get_grade(diagnosis["total_score"]),
            "category_scores": scores,
            "weak_categories": weak_categories,
            "missing_topics_top5": diagnosis["missing_topics"][:5],
            "freshness_issues": diagnosis["freshness_issues"],
            "weak_eeat": diagnosis["weak_eeat"],
            "title_analysis": diagnosis.get("title_analysis", {}),
            "body_analysis": diagnosis.get("body_analysis", {}),
            "paa_coverage": diagnosis.get("paa_coverage", {}),
            "competitor_summary": {
                "count": len(competitors),
                "avg_word_count": round(sum(c.get("word_count", 0) for c in competitors) / max(len(competitors), 1)),
                "urls": [c.get("url", "") for c in competitors],
            },
        }

    def _get_grade(self, score: int) -> str:
        if score >= 85:
            return "A（優秀）"
        elif score >= 70:
            return "B（良好）"
        elif score >= 50:
            return "C（要改善）"
        elif score >= 30:
            return "D（要大幅改善）"
        else:
            return "E（要再構築）"

    # ════════════════════════════════════════════════
    # 第2部: リライト指示書
    # ════════════════════════════════════════════════

    def _build_part2(self, diagnosis: dict, own_article: dict,
                     competitors: list[dict], keyword: str, role: str) -> str:
        """リライト指示書をテキストで生成"""
        scores = diagnosis["category_scores"]
        total = diagnosis["total_score"]

        lines = []
        sep = "═" * 60

        # ── ヘッダ ──
        lines.append(sep)
        lines.append("  記事リライト指示書")
        lines.append(f"  生成日: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(sep)
        lines.append("")

        # ── 記事情報 ──
        lines.append("■ 記事情報")
        lines.append(f"  URL: {own_article.get('url', '')}")
        lines.append(f"  タイトル: {own_article.get('title', '')}")
        lines.append(f"  メインキーワード: {keyword}")
        lines.append(f"  記事の役割: {role}")
        lines.append(f"  現在の文字数: {own_article.get('word_count', 0):,}文字")
        lines.append("")

        # ── 診断サマリ ──
        lines.append("■ 診断スコアサマリ")
        lines.append(f"  総合スコア: {total}/100点 ({self._get_grade(total)})")
        lines.append("")
        for key in ["topic_coverage", "eeat", "title_optimization", "body_comprehensiveness", "internal_links", "cv_funnel", "freshness"]:
            val = scores[key]
            bar = "█" * int(val["score"] / val["max"] * 20) + "░" * (20 - int(val["score"] / val["max"] * 20))
            lines.append(f"  {val['label']:　<12} {val['score']:>2}/{val['max']:>2} [{bar}]")
            lines.append(f"    → {val['details']}")
        lines.append("")

        # ── リライト優先順位 ──
        lines.append("■ リライト優先順位（スコア低い順）")
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"] / x[1]["max"])
        for i, (key, val) in enumerate(sorted_scores, 1):
            ratio = val["score"] / val["max"]
            priority = "🔴 高" if ratio < 0.4 else ("🟡 中" if ratio < 0.7 else "🟢 低")
            lines.append(f"  {i}. {priority} {val['label']} ({val['score']}/{val['max']}点)")
        lines.append("")

        # ── 1. 不足トピックの補完 ──
        lines.append("─" * 60)
        lines.append("【指指示1】不足トピックの補完")
        lines.append("─" * 60)
        missing = diagnosis["missing_topics"][:5]
        if missing:
            lines.append("以下の論点は競合上位記事が多く扱っているが、自社記事に")
            lines.append("不足しているトピックです。必要に応じて追加を検討してください。")
            lines.append("※ 競合の文章をコピー/引き写ししないこと。")
            lines.append("※ pksp.jp独自の一次情報・体験・取材データを必ず加えること。")
            lines.append("")
            for i, topic in enumerate(missing, 1):
                lines.append(f"  {i}. {topic['topic']}")
                lines.append(f"     競合カバー率: {topic['competitor_coverage_count']}/{len(competitors)}記事"
                             f"（{topic['competitor_coverage_ratio']:.0%}）")
                lines.append(f"     → pksp.jp独自の視点・事例・データを加えて新セクションとして執筆")
            lines.append("")
        else:
            lines.append("  不足トピックは検出されませんでした。トピック網羅性は良好です。")
            lines.append("")

        # ── 2. E-E-A-T強化 ──
        lines.append("─" * 60)
        lines.append("【指指示2】E-E-A-T（信頼性・専門性）の強化")
        lines.append("─" * 60)
        weak_eeat = diagnosis["weak_eeat"]
        if weak_eeat:
            lines.append("ファクタリングはYMYL領域であり、Googleは信頼性を最も厳格に")
            lines.append("評価します。以下の項目を強化してください。")
            lines.append("")
            for item in weak_eeat:
                lines.append(f"  □ {item['item']} [{item['status']}]")
                lines.append(f"    → {item['recommendation']}")
            lines.append("")
        else:
            lines.append("  E-E-A-T要素は全て検出されました。良好な状態です。")
            lines.append("")

        # ── 3. タイトル最適化 ──
        lines.append("─" * 60)
        lines.append("【指指示3】タイトル最適化")
        lines.append("─" * 60)
        title_info = diagnosis.get("title_analysis", {})
        if title_info.get("issues"):
            lines.append(f"  現タイトル: {title_info.get('title', '')}")
            lines.append(f"  文字数: {title_info.get('title_length', 0)}文字")
            lines.append("")
            for issue in title_info["issues"]:
                lines.append(f"  □ {issue}")
            lines.append("")
            lines.append("  推奨アクション:")
            lines.append(f"    - キーワード「{keyword}」を前半に配置")
            lines.append("    - 文字数を28-40文字に調整")
            lines.append("    - 数字を含める（例：「5つのポイント」「2026年最新」等）")
            lines.append("")
        else:
            lines.append("  タイトル最適化の問題は検出されませんでした。")
            lines.append("")

        # ── 4. 本文の拡充 ──
        lines.append("─" * 60)
        lines.append("【指指示4】本文の拡充・独自コンテンツ追加")
        lines.append("─" * 60)
        body_info = diagnosis.get("body_analysis", {})
        if body_info.get("issues"):
            lines.append(f"  現在の文字数: {body_info.get('word_count', 0):,}文字")
            lines.append(f"  競合平均文字数: {body_info.get('competitor_avg', 0):,}文字")
            lines.append(f"  競合比: {body_info.get('ratio', 0):.0%}")
            lines.append("")
            for issue in body_info["issues"]:
                lines.append(f"  □ {issue}")
            lines.append("")
            lines.append("  推奨アクション:")
            lines.append("    - 競合平均文字数に近づくよう加筆（ただし文字数埋めではなく質の高い内容で）")
            lines.append("    - 比較表・シミュレーション表・図解を追加し独自価値を高める")
            lines.append("    - pksp.jp独自の事例・インタビュー・データがあれば積極的に活用")
            lines.append("")
        else:
            lines.append("  本文の網羅性は競合比で良好です。")
            lines.append("")

        # ── 5. 内部リンク強化 ──
        lines.append("─" * 60)
        lines.append("【指指示5】内部リンク・サイト回遊の強化")
        lines.append("─" * 60)
        link_info = diagnosis.get("link_analysis", {})
        if link_info.get("issues"):
            lines.append(f"  現在の内部リンク数: {link_info.get('link_count', 0)}本")
            lines.append("")
            for issue in link_info["issues"]:
                lines.append(f"  □ {issue}")
            lines.append("")
            lines.append("  推奨アクション:")
            lines.append("    - 関連記事（基礎知識・用語解説・業者比較等）へのリンクを5-10本追加")
            lines.append("    - ピラーページ（ファクタリング総括・基礎ページ）への導線を明確に")
            lines.append("    - アンカーテキストはキーワードを含む自然な表現に")
            lines.append("")
        else:
            lines.append("  内部リンク構造は良好です。")
            lines.append("")

        # ── 6. CV導線 ──
        if role != "流入":
            lines.append("─" * 60)
            lines.append("【指指示6】コンバージョン導線の強化")
            lines.append("─" * 60)
            cv_info = diagnosis.get("cv_analysis", {})
            if cv_info.get("issues"):
                for issue in cv_info["issues"]:
                    lines.append(f"  □ {issue}")
                lines.append("")
                lines.append("  推奨アクション:")
                lines.append("    - 記事上部・中部・下部の3箇所にCTAを設置")
                lines.append("    - 「無料相談」「お問い合わせ」「申し込む」等の明確なボタン")
                lines.append("    - 公式フォーム・申込ページへのリンクを目立つ位置に配置")
                lines.append("")
            else:
                lines.append("  CV導線は良好です。")
                lines.append("")

        # ── 7. 鮮度・ファクトチェック ──
        lines.append("─" * 60)
        lines.append("【指指示7】鮮度の確認・ファクトチェック")
        lines.append("─" * 60)
        freshness_issues = diagnosis["freshness_issues"]
        if freshness_issues:
            lines.append("以下の数値・記述は最新情報か確認が必要です。")
            lines.append("※ ツールは数値の正誤を断定しません。最終確認は人間が")
            lines.append("  公式ソース（金融庁・業者公式サイト等）で行ってください。")
            lines.append("")
            for issue in freshness_issues[:10]:
                desc = issue.get("description", str(issue))
                lines.append(f"  □ {desc}")
            lines.append("")
            lines.append("  推奨アクション:")
            lines.append("    - 各数値を公式ソースで最新値に更新")
            lines.append("    - 更新日を明記し直す")
            lines.append("    - 古い法令・制度情報がないか確認")
            lines.append("")
        else:
            lines.append("  鮮度の問題は検出されませんでした。")
            lines.append("")

        # ── 8. PAA対応 ──
        paa_info = diagnosis.get("paa_coverage", {})
        if paa_info.get("total", 0) > 0:
            lines.append("─" * 60)
            lines.append("【指指示8】「他の人はこちらも質問」(PAA) への対応")
            lines.append("─" * 60)
            uncovered = paa_info.get("uncovered", [])
            if uncovered:
                lines.append(f"  PAA {paa_info['total']}件中、{len(uncovered)}件が記事内で未カバーの可能性:")
                lines.append("")
                for q in uncovered:
                    lines.append(f"  □ {q}")
                lines.append("")
                lines.append("  推奨アクション:")
                lines.append("    - 上記の質問に回答するセクション・FAQを追加")
                lines.append("    - 各質問に見出し（h2/h3）を立て、簡潔に回答")
                lines.append("    - 回答にはpksp.jp独自の知見を加える")
                lines.append("")
            else:
                lines.append("  PAAの質問は全て記事内でカバーされている可能性が高いです。")
                lines.append("")

        # ── 9. 関連サジェスト ──
        suggestions = diagnosis.get("related_suggestions", [])
        if suggestions:
            lines.append("─" * 60)
            lines.append("【参考】関連サジェストキーワード")
            lines.append("─" * 60)
            for s in suggestions:
                lines.append(f"  ・{s}")
            lines.append("")

        # ── 注意事項 ──
        lines.append("─" * 60)
        lines.append("【重要】リライト時の注意事項")
        lines.append("─" * 60)
        lines.append("  1. 競合記事の文章をコピー・引き写ししないこと")
        lines.append("  2. 不足トピックは「埋めるべき候補」であり、")
        lines.append("     必ずpksp.jp独自の一次情報・知見を加えること")
        lines.append("  3. 数値の正誤はツールが断定しない。最終チェックは人間が")
        lines.append("     公式ソースで行うこと")
        lines.append("  4. 本指示書は競合との差分可視化と方向性示唆が目的であり、")
        lines.append("     上位表示を保証するものではない")
        lines.append("")
        lines.append(sep)
        lines.append("  以上")
        lines.append(sep)

        return "\n".join(lines)
