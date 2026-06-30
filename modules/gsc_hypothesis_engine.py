# -*- coding: utf-8 -*-
"""
原因仮説エンジン
「悪い変化」から、可能性の高い原因仮説を推定する。

pksp.jp（ファクタリング情報サイト）の特性を考慮:
- YMYL領域
- 業種別キーワード（運送業・製造業等）が主力
- 業者口コミ系（pmg・olta・ラボル等）も主要
"""
import logging

logger = logging.getLogger("gsc.hypothesis")


class HypothesisEngine:
    """悪い変化から原因仮説を生成する"""

    def generate(self, diff_result: dict, period_7d, period_28d, period_3m) -> list:
        """
        悪い変化リストを分析し、原因仮説を構造化リストで返す

        Returns:
            [
                {
                    hypothesis: 仮説テキスト,
                    confidence: low/mid/high,
                    evidence: 根拠リスト,
                    related_signals: 関連する変化のリスト,
                    suggested_action: 次のアクション,
                },
                ...
            ]
        """
        hypotheses = []
        summary = diff_result.get("summary_comparison", {})
        query_diffs = diff_result.get("query_diffs", {})
        page_diffs = diff_result.get("page_diffs", {})
        bad_changes = diff_result.get("bad_changes", [])

        # ────────────────────────────────────────
        # 仮説1: アルゴリズム変動の可能性
        # ────────────────────────────────────────
        # 順位下落クエリと表示減クエリが同時に多発している場合
        n_pos_dropped = len(query_diffs.get("position_dropped", []))
        n_declining = len(query_diffs.get("declining", []))
        n_disappearing = len(query_diffs.get("disappearing", []))

        if n_pos_dropped >= 3 and n_declining >= 3:
            severity = "high" if n_pos_dropped >= 5 else "mid"
            hypotheses.append({
                "hypothesis": "Googleアルゴリズム変動 / コアアップデートの影響",
                "confidence": "mid",
                "severity": severity,
                "evidence": [
                    f"順位下落クエリが {n_pos_dropped} 件発生",
                    f"表示減クエリが {n_declining} 件発生",
                    f"複数クエリで同時に変動が起きている = サイト固有ではなく外部要因の可能性",
                ],
                "suggested_action": "Google検索セントラルの最新アップデート情報を確認。YMYL領域では E-E-A-T 強化が常時推奨。",
            })

        # ────────────────────────────────────────
        # 仮説2: 特定ページのインデックス問題 / 大幅順位下落
        # ────────────────────────────────────────
        # 表示減ページが3件以上ある場合
        declining_pages = page_diffs.get("declining", [])
        if len(declining_pages) >= 3:
            urls = [p["上位のページ"] for p in declining_pages[:5]]
            hypotheses.append({
                "hypothesis": "特定ページでインデックス問題 / 順位大幅下落",
                "confidence": "mid",
                "severity": "high",
                "evidence": [
                    f"表示が落ちているページが {len(declining_pages)} 件",
                    f"対象URL: " + ", ".join(u.split("/")[-2] for u in urls[:3]),
                ],
                "suggested_action": "GSCの「ページ」レポートで該当URLのインデックス状況を確認。サイトマップ再送信・URLインスペクションを実行。",
            })

        # ────────────────────────────────────────
        # 仮説3: 季節要因 / 検索需要の変動
        # ────────────────────────────────────────
        # 表示数自体が大きく減っている場合（順位は維持 or 軽微）
        d = summary.get("diff_7d_vs_28d") or {}
        imp_ratio = d.get("imp_ratio")
        pos_diff = d.get("position_diff")

        if imp_ratio is not None and imp_ratio <= 80 and (pos_diff is None or abs(pos_diff) < 3):
            hypotheses.append({
                "hypothesis": "検索需要そのものが減少（季節要因・市場動向）",
                "confidence": "mid",
                "severity": "low",
                "evidence": [
                    f"表示回数が28日平均比 {imp_ratio:.0f}% に低下",
                    f"順位はほぼ維持（{pos_diff:+.1f}位）",
                    "順位は変わらないので、市場の検索需要が落ちている可能性",
                ],
                "suggested_action": "Googleトレンドで主要キーワード（ファクタリング 運送業 等）の検索ボリューム推移を確認。需要は戻る前提で、その間にE-E-A-T強化・記事ストック増を進める。",
            })

        # ────────────────────────────────────────
        # 仮説4: CTR悪化（タイトル/メタの問題）
        # ────────────────────────────────────────
        ctr_diff = d.get("ctr_diff")
        if ctr_diff is not None and ctr_diff <= -0.2 and (imp_ratio is None or imp_ratio >= 90):
            hypotheses.append({
                "hypothesis": "タイトル/メタディスクリプションのCTR悪化",
                "confidence": "mid",
                "severity": "mid",
                "evidence": [
                    f"CTRが{ctr_diff:.2f}pt低下",
                    "表示数は維持されているのにクリック率だけ落ちている",
                    "競合のスニペット改善で相対的にCTRが落ちた可能性",
                ],
                "suggested_action": "上位表示クエリで実際の検索結果を確認。競合のタイトル・メタを比較し、自社のタイトルを再設計。",
            })

        # ────────────────────────────────────────
        # 仮説5: 1ページ目に乗ったが力不足（11-20位停滞）
        # ────────────────────────────────────────
        almost = query_diffs.get("almost_top10", [])
        if len(almost) >= 5:
            hypotheses.append({
                "hypothesis": "11-20位の押し上げが進まず、機会損失が拡大",
                "confidence": "high",
                "severity": "mid",
                "evidence": [
                    f"11-20位帯に {len(almost)} クエリが滞留",
                    f"代表例: " + " / ".join(q["上位のクエリ"] for q in almost[:3]),
                    "1ページ目（10位以内）に入るとCTRが約5-10倍になるため、機会損失が大きい",
                ],
                "suggested_action": "該当ページをリライト診断ツールに投入し、E-E-A-T強化・トピック網羅・八木氏の一次情報追加を実施。",
            })

        # ────────────────────────────────────────
        # 仮説6: 業種別キーワードの停滞（pksp.jp固有）
        # ────────────────────────────────────────
        # 「ファクタリング 〇〇業」系のクエリで0クリック・順位悪化があるか
        ctr_lost = query_diffs.get("ctr_lost", [])
        industry_queries = [
            q for q in ctr_lost
            if any(kw in q["上位のクエリ"] for kw in ["運送業", "製造業", "飲食店", "建設", "介護", "医療", "物流", "it"])
        ]
        if len(industry_queries) >= 3:
            queries = [q["上位のクエリ"] for q in industry_queries[:5]]
            hypotheses.append({
                "hypothesis": "業種別キーワードで競合に差をつけられている",
                "confidence": "high",
                "severity": "mid",
                "evidence": [
                    f"業種系キーワード {len(industry_queries)} 件で表示はあるがクリック0",
                    f"代表例: " + " / ".join(queries[:3]),
                    "業種別ファクタリングは pksp.jp の主力カテゴリ — ここで取れていないのは課題",
                ],
                "suggested_action": "業種別ページ（funding-by-industry/）を優先的にリライト。八木氏の銀行員時代の業種知見を一次情報として追加。",
            })

        # ────────────────────────────────────────
        # 仮説7: 業者口コミ系の停滞
        # ────────────────────────────────────────
        review_queries = [
            q for q in ctr_lost
            if any(kw in q["上位のクエリ"].lower() for kw in ["口コミ", "評判", "pmg", "olta", "オルタ", "ラボル", "アクセルファクター", "ペイトナー", "ピーエムジー"])
        ]
        if len(review_queries) >= 3:
            queries = [q["上位のクエリ"] for q in review_queries[:5]]
            hypotheses.append({
                "hypothesis": "業者口コミ・評判系キーワードで競合（口コミサイト等）に押されている",
                "confidence": "high",
                "severity": "mid",
                "evidence": [
                    f"口コミ/評判系キーワード {len(review_queries)} 件で表示はあるがクリック0",
                    f"代表例: " + " / ".join(queries[:3]),
                    "口コミ系は信頼性が決め手 — 八木氏の専門家視点が差別化要素になる",
                ],
                "suggested_action": "factoring-review/ 配下のページを優先リライト。八木氏の「銀行員時代に見た優良業者の特徴」を一次情報として加える。",
            })

        # ────────────────────────────────────────
        # 仮説8: 単純に「リライト未着手の記事が古くなった」
        # ────────────────────────────────────────
        underperformers = page_diffs.get("underperformers", [])
        if len(underperformers) >= 5:
            urls = [p["上位のページ"].split("/")[-2] for p in underperformers[:5]]
            hypotheses.append({
                "hypothesis": "記事の鮮度・網羅性不足による相対的下落",
                "confidence": "mid",
                "severity": "low",
                "evidence": [
                    f"表示は多いがクリックが少ないページが {len(underperformers)} 件",
                    f"対象例: " + ", ".join(urls[:3]),
                    "YMYL領域では更新日・情報の鮮度が信頼性に直結",
                ],
                "suggested_action": "これらのページをリライト診断ツールに投入し、E-E-A-T要素・最新数値・八木氏視点を追加。",
            })

        # ────────────────────────────────────────
        # 仮説9: 7日の最終日が観測未完了
        # ────────────────────────────────────────
        # 7日の最終日の表示数が他日の平均と比べて極端に少ない場合
        if period_7d and period_7d.chart is not None and len(period_7d.chart) >= 7:
            last_day = period_7d.chart.iloc[-1]
            other_days = period_7d.chart.iloc[:-1]
            avg_other = other_days["表示回数"].mean()
            if last_day["表示回数"] < avg_other * 0.2:
                hypotheses.append({
                    "hypothesis": "GSCデータの観測ラグ（最終日が未確定）",
                    "confidence": "high",
                    "severity": "low",
                    "evidence": [
                        f"最終日（{last_day['日付'].strftime('%Y-%m-%d') if hasattr(last_day['日付'], 'strftime') else last_day['日付']}）の表示数 {int(last_day['表示回数'])} は他日平均 {avg_other:.0f} の{last_day['表示回数']/avg_other*100:.0f}%",
                        "GSCは2-3日のタイムラグがあるため、直近日のデータは過小評価される",
                    ],
                    "suggested_action": "最終日を除いた6日間で再評価することを推奨。",
                })

        # 仮説が一つもない場合はデフォルト
        if not hypotheses:
            hypotheses.append({
                "hypothesis": "目立った悪化シグナルなし",
                "confidence": "high",
                "severity": "low",
                "evidence": ["主要KPIに大きな変動なし"],
                "suggested_action": "現状の運用を継続。中長期視点で11-20位帯クエリのリライトを進める。",
            })

        return hypotheses
