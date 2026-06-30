# -*- coding: utf-8 -*-
"""
レポートビルダー
分析結果から、定型フォーマットのレポート（テキスト・Markdown・JSON）を生成する。
"""
import logging
from datetime import datetime

logger = logging.getLogger("gsc.report")


class ReportBuilder:
    """定期分析レポートを組み立てる"""

    def build(self, period_7d, period_28d, period_3m,
              diff_result: dict, hypotheses: list,
              recommendations: list) -> dict:
        """
        完全レポートを構築

        Returns:
            {
                json: 構造化データ,
                markdown: Markdown形式テキスト,
                text: プレーンテキスト,
            }
        """
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── サマリ整形 ──
        summary = diff_result.get("summary_comparison", {})

        # ── JSON ──
        json_report = {
            "report_date": report_date,
            "site": "pksp.jp",
            "summary": summary,
            "good_changes": diff_result.get("good_changes", []),
            "bad_changes": diff_result.get("bad_changes", []),
            "hypotheses": hypotheses,
            "recommendations": recommendations,
            "raw_data": {
                "query_diffs": {
                    k: len(v) if isinstance(v, list) else v
                    for k, v in diff_result.get("query_diffs", {}).items()
                },
                "page_diffs": {
                    k: len(v) if isinstance(v, list) else v
                    for k, v in diff_result.get("page_diffs", {}).items()
                },
            },
        }

        # ── Markdown ──
        markdown_report = self._build_markdown(json_report, summary)

        # ── プレーンテキスト ──
        text_report = self._build_text(json_report, summary)

        return {
            "json": json_report,
            "markdown": markdown_report,
            "text": text_report,
        }

    # ════════════════════════════════════════════════
    # Markdownレポート（GitHub・Slack・docs等で使いやすい）
    # ════════════════════════════════════════════════

    def _build_markdown(self, data: dict, summary: dict) -> str:
        lines = []

        lines.append(f"# 📊 pksp.jp Search Console 定期分析レポート")
        lines.append(f"")
        lines.append(f"**生成日**: {data['report_date']}")
        lines.append(f"")

        # ── サマリ表 ──
        lines.append(f"## 📈 期間サマリ")
        lines.append("")
        lines.append("| 指標 | 直近7日 | 直近28日 | 直近3か月 |")
        lines.append("|------|---------|----------|-----------|")
        p7 = summary.get("p7") or {}
        p28 = summary.get("p28") or {}
        p3m = summary.get("p3m") or {}
        lines.append(f"| 総クリック | {p7.get('total_clicks', '-')} | {p28.get('total_clicks', '-')} | {p3m.get('total_clicks', '-')} |")
        lines.append(f"| 総表示回数 | {p7.get('total_impressions', '-'):,} | {p28.get('total_impressions', '-'):,} | {p3m.get('total_impressions', '-'):,} |")
        lines.append(f"| 平均CTR | {p7.get('avg_ctr', '-')}% | {p28.get('avg_ctr', '-')}% | {p3m.get('avg_ctr', '-')}% |")
        lines.append(f"| 平均掲載順位 | {p7.get('avg_position', '-')}位 | {p28.get('avg_position', '-')}位 | {p3m.get('avg_position', '-')}位 |")
        lines.append(f"| 日次平均クリック | {p7.get('daily_avg_clicks', '-')} | {p28.get('daily_avg_clicks', '-')} | {p3m.get('daily_avg_clicks', '-')} |")
        lines.append(f"| 日次平均表示 | {p7.get('daily_avg_impressions', '-'):.0f} | {p28.get('daily_avg_impressions', '-'):.0f} | {p3m.get('daily_avg_impressions', '-'):.0f} |")
        lines.append("")

        # ── 期間比較（7日 vs 28日） ──
        d = summary.get("diff_7d_vs_28d")
        if d:
            lines.append("### 7日 vs 28日（日次平均ベース）")
            lines.append("")
            lines.append(f"- **クリック**: {d['clicks_diff']:+.2f}/日（28日比 {d['clicks_ratio']:.0f}%）" if d.get('clicks_ratio') is not None else "")
            lines.append(f"- **表示数**: {d['imp_diff']:+.0f}/日（28日比 {d['imp_ratio']:.0f}%）" if d.get('imp_ratio') is not None else "")
            lines.append(f"- **掲載順位**: {d['position_diff']:+.1f}位（負=改善）")
            lines.append(f"- **CTR**: {d['ctr_diff']:+.2f}pt")
            lines.append("")

        # ── 良い変化 ──
        lines.append(f"## ✅ 良い変化")
        lines.append("")
        good = data.get("good_changes", [])
        if not good:
            lines.append("- _目立った良い変化なし_")
        else:
            for g in good:
                lines.append(f"### {g['title']}")
                lines.append(f"- **カテゴリ**: {g['category']}")
                if g.get('detail'):
                    lines.append(f"- **詳細**: {g['detail']}")
                lines.append("")

        # ── 悪い変化 ──
        lines.append(f"## ⚠️ 悪い変化")
        lines.append("")
        bad = data.get("bad_changes", [])
        if not bad:
            lines.append("- _目立った悪い変化なし_")
        else:
            for b in bad:
                sev_icon = {"high": "🔴", "mid": "🟡", "low": "🟢"}.get(b.get("severity", "mid"), "🟡")
                lines.append(f"### {sev_icon} {b['title']}")
                lines.append(f"- **カテゴリ**: {b['category']}")
                lines.append(f"- **重要度**: {b.get('severity', 'mid')}")
                if b.get('detail'):
                    lines.append(f"- **詳細**: {b['detail']}")
                lines.append("")

        # ── 原因仮説 ──
        lines.append(f"## 🔍 原因仮説")
        lines.append("")
        hypos = data.get("hypotheses", [])
        if not hypos:
            lines.append("- _仮説生成対象の悪化シグナルなし_")
        else:
            for i, h in enumerate(hypos, 1):
                conf_icon = {"high": "🟢 確度高", "mid": "🟡 確度中", "low": "⚪ 確度低"}.get(h.get("confidence"), "")
                lines.append(f"### 仮説{i}: {h['hypothesis']}")
                lines.append(f"- **確度**: {conf_icon}")
                lines.append(f"- **重要度**: {h.get('severity', 'mid')}")
                lines.append("- **根拠**:")
                for e in h.get("evidence", []):
                    lines.append(f"  - {e}")
                lines.append(f"- **次のアクション**: {h.get('suggested_action', '')}")
                lines.append("")

        # ── 次に直すべき記事 ──
        lines.append(f"## 🎯 次に直すべき記事（リライト推奨）")
        lines.append("")
        recs = data.get("recommendations", [])
        if not recs:
            lines.append("- _リライト推奨記事なし_")
        else:
            for r in recs:
                cs = r["current_state"]
                impact = r["estimated_impact"]
                lines.append(f"### {r['rank']}. {r['url']}")
                lines.append(f"- **カテゴリ**: {r['category']}")
                lines.append(f"- **現状**: 表示{cs['impressions']:,} / クリック{cs['clicks']} / CTR{cs['ctr']}% / 順位{cs['position']}位")
                lines.append(f"- **機会損失**: 期間内 約{r.get('missed_clicks', 0):.1f}クリック（推定）")
                lines.append(f"- **推奨理由**: {r.get('reason', '')}")

                if r.get("related_queries"):
                    lines.append(f"- **主要流入クエリ（推定）**:")
                    for q in r["related_queries"]:
                        lines.append(f"  - {q['query']} (表示{q['impressions']} / 順位{q['position']})")

                lines.append(f"- **リライトの焦点**:")
                for f in r.get("rewrite_focus", []):
                    lines.append(f"  - {f}")

                lines.append(f"- **pksp.jp 独自の打ち手（八木氏視点）**:")
                for a in r.get("pksp_unique_angle", []):
                    lines.append(f"  - {a}")

                lines.append(f"- **推定インパクト**: {impact['scenario']}")
                lines.append(f"  - 現在 {impact['current_clicks']}クリック → 改善後 {impact['potential_clicks_per_period']}クリック（+{impact['uplift']}）")

                lines.append(f"- **次のアクション**: {r.get('next_step', '')}")
                lines.append("")

        # ── フッタ ──
        lines.append("---")
        lines.append("")
        lines.append("### ⚠️ レポートの注意事項")
        lines.append("- 期間比較は日次平均で正規化して算出")
        lines.append("- GSCデータは2-3日のタイムラグあり。直近日のデータは過小評価される可能性")
        lines.append("- 「機会損失クリック数」は順位・期待CTRからの推定値")
        lines.append("- リライト推奨は機械的判定 — 最終判断は人間が記事内容を確認の上で")

        return "\n".join(lines)

    # ════════════════════════════════════════════════
    # プレーンテキストレポート（メール・Slackへ貼り付け用）
    # ════════════════════════════════════════════════

    def _build_text(self, data: dict, summary: dict) -> str:
        lines = []
        sep = "═" * 60
        sub = "─" * 60

        lines.append(sep)
        lines.append("  pksp.jp Search Console 定期分析レポート")
        lines.append(f"  生成日: {data['report_date']}")
        lines.append(sep)
        lines.append("")

        # サマリ
        p7 = summary.get("p7") or {}
        p28 = summary.get("p28") or {}
        p3m = summary.get("p3m") or {}
        lines.append("■ 期間サマリ")
        lines.append("")
        lines.append(f"  指標               7日       28日      3か月")
        lines.append(f"  総クリック         {p7.get('total_clicks', 0):>6}    {p28.get('total_clicks', 0):>6}    {p3m.get('total_clicks', 0):>6}")
        lines.append(f"  総表示回数      {p7.get('total_impressions', 0):>8,}  {p28.get('total_impressions', 0):>8,}  {p3m.get('total_impressions', 0):>8,}")
        lines.append(f"  平均CTR(%)        {p7.get('avg_ctr', 0):>5.2f}     {p28.get('avg_ctr', 0):>5.2f}     {p3m.get('avg_ctr', 0):>5.2f}")
        lines.append(f"  平均掲載順位       {p7.get('avg_position', 0):>5.1f}     {p28.get('avg_position', 0):>5.1f}     {p3m.get('avg_position', 0):>5.1f}")
        lines.append("")

        # 良い変化
        lines.append(sub)
        lines.append("【良い変化】")
        lines.append(sub)
        good = data.get("good_changes", [])
        if not good:
            lines.append("  目立った良い変化なし")
        else:
            for g in good:
                lines.append(f"  ✓ [{g['category']}] {g['title']}")
                if g.get('detail'):
                    lines.append(f"    → {g['detail']}")
        lines.append("")

        # 悪い変化
        lines.append(sub)
        lines.append("【悪い変化】")
        lines.append(sub)
        bad = data.get("bad_changes", [])
        if not bad:
            lines.append("  目立った悪い変化なし")
        else:
            for b in bad:
                sev = {"high": "🔴", "mid": "🟡", "low": "🟢"}.get(b.get("severity", "mid"), "■")
                lines.append(f"  {sev} [{b['category']}] {b['title']}")
                if b.get('detail'):
                    lines.append(f"    → {b['detail']}")
        lines.append("")

        # 原因仮説
        lines.append(sub)
        lines.append("【原因仮説】")
        lines.append(sub)
        hypos = data.get("hypotheses", [])
        for i, h in enumerate(hypos, 1):
            lines.append(f"  仮説{i}: {h['hypothesis']}")
            lines.append(f"    確度: {h.get('confidence', '')}  重要度: {h.get('severity', '')}")
            lines.append(f"    根拠:")
            for e in h.get("evidence", []):
                lines.append(f"      - {e}")
            lines.append(f"    → アクション: {h.get('suggested_action', '')}")
            lines.append("")

        # 次に直すべき記事
        lines.append(sub)
        lines.append("【次に直すべき記事（リライト推奨）】")
        lines.append(sub)
        for r in data.get("recommendations", []):
            cs = r["current_state"]
            impact = r["estimated_impact"]
            lines.append(f"  {r['rank']}. {r['url']}")
            lines.append(f"     カテゴリ: {r['category']}")
            lines.append(f"     現状: 表示{cs['impressions']:,} / クリック{cs['clicks']} / CTR{cs['ctr']}% / 順位{cs['position']}位")
            lines.append(f"     リライトの焦点:")
            for f in r.get("rewrite_focus", []):
                lines.append(f"       - {f}")
            lines.append(f"     pksp独自の打ち手（八木氏視点）:")
            for a in r.get("pksp_unique_angle", []):
                lines.append(f"       - {a}")
            lines.append(f"     推定インパクト: {impact['scenario']}")
            lines.append(f"       {impact['current_clicks']}クリック → {impact['potential_clicks_per_period']}クリック (+{impact['uplift']})")
            lines.append(f"     次のアクション: {r.get('next_step', '')}")
            lines.append("")

        # フッタ
        lines.append(sep)
        lines.append("  注意事項:")
        lines.append("  - 期間比較は日次平均で正規化")
        lines.append("  - GSCデータは2-3日のタイムラグあり")
        lines.append("  - 機会損失クリック数は推定値")
        lines.append("  - 最終判断は人間が記事内容を確認の上で")
        lines.append(sep)

        return "\n".join(lines)
