# -*- coding: utf-8 -*-
"""
期間差分エンジン
7日 / 28日 / 3か月 のデータを横断比較し、
「良い変化」「悪い変化」を抽出する。

すべての比較は日次平均で正規化して行う（公平な比較）。
"""
import pandas as pd
import logging

logger = logging.getLogger("gsc.diff")


class DiffEngine:
    """期間差分の検出ロジック"""

    # しきい値（チューニング可能）
    SIGNIFICANT_IMP_DIFF = 5         # 日次表示数の差がこれ以上で有意とみなす
    SIGNIFICANT_CLICK_DIFF = 0.3     # 日次クリック数の差がこれ以上で有意
    MIN_IMP_FOR_COMPARISON = 10      # 比較対象とする最低表示数（ノイズ除外）
    POSITION_CHANGE_THRESHOLD = 3    # 順位変動の有意しきい値（位）

    def compare_periods(self, period_7d, period_28d, period_3m) -> dict:
        """
        3期間の総合比較

        Returns:
            {
                summary_comparison: 期間サマリ比較,
                good_changes: 良い変化リスト,
                bad_changes: 悪い変化リスト,
                query_diffs: クエリレベル差分,
                page_diffs: ページレベル差分,
            }
        """
        # ── サマリ比較 ──
        summary = self._compare_summary(period_7d, period_28d, period_3m)

        # ── クエリ差分 ──
        query_diffs = self._compare_queries(period_7d, period_28d, period_3m)

        # ── ページ差分 ──
        page_diffs = self._compare_pages(period_7d, period_28d, period_3m)

        # ── 良い変化・悪い変化 を仕分け ──
        good_changes, bad_changes = self._classify_changes(
            summary, query_diffs, page_diffs
        )

        return {
            "summary_comparison": summary,
            "query_diffs": query_diffs,
            "page_diffs": page_diffs,
            "good_changes": good_changes,
            "bad_changes": bad_changes,
        }

    # ════════════════════════════════════════════════
    # サマリ比較
    # ════════════════════════════════════════════════

    def _compare_summary(self, p7, p28, p3m) -> dict:
        """期間サマリの比較（日次平均で正規化）"""
        s7 = p7.summary_dict() if p7 else None
        s28 = p28.summary_dict() if p28 else None
        s3m = p3m.summary_dict() if p3m else None

        # 7日 vs 28日
        comp_7_vs_28 = self._calc_delta(s7, s28) if s7 and s28 else None
        # 28日 vs 3か月
        comp_28_vs_3m = self._calc_delta(s28, s3m) if s28 and s3m else None
        # 7日 vs 3か月
        comp_7_vs_3m = self._calc_delta(s7, s3m) if s7 and s3m else None

        return {
            "p7": s7,
            "p28": s28,
            "p3m": s3m,
            "diff_7d_vs_28d": comp_7_vs_28,
            "diff_28d_vs_3m": comp_28_vs_3m,
            "diff_7d_vs_3m": comp_7_vs_3m,
        }

    def _calc_delta(self, recent: dict, baseline: dict) -> dict:
        """日次平均ベースで差分を計算"""
        clicks_recent = recent["daily_avg_clicks"]
        clicks_base = baseline["daily_avg_clicks"]
        imp_recent = recent["daily_avg_impressions"]
        imp_base = baseline["daily_avg_impressions"]
        pos_recent = recent["avg_position"]
        pos_base = baseline["avg_position"]
        ctr_recent = recent["avg_ctr"]
        ctr_base = baseline["avg_ctr"]

        return {
            "clicks_diff": round(clicks_recent - clicks_base, 2),
            "clicks_ratio": round(clicks_recent / clicks_base * 100, 0) if clicks_base > 0 else None,
            "imp_diff": round(imp_recent - imp_base, 0),
            "imp_ratio": round(imp_recent / imp_base * 100, 0) if imp_base > 0 else None,
            "position_diff": round(pos_recent - pos_base, 1),  # +は悪化、-は改善
            "ctr_diff": round(ctr_recent - ctr_base, 2),
        }

    # ════════════════════════════════════════════════
    # クエリ差分
    # ════════════════════════════════════════════════

    def _compare_queries(self, p7, p28, p3m) -> dict:
        """クエリレベルの差分検出"""
        result = {
            "growing": [],         # 表示が伸びているクエリ
            "declining": [],       # 表示が落ちているクエリ
            "new_appearing": [],   # 新たに上位表示されたクエリ
            "disappearing": [],    # 表示されなくなったクエリ
            "position_improved": [],  # 順位が改善したクエリ
            "position_dropped": [],   # 順位が下がったクエリ
            "almost_top10": [],    # 11-20位の押し上げ候補
            "ctr_lost": [],        # 高表示・低CTR（タイトル改善余地）
        }

        if p7 is None or p28 is None or p7.query is None or p28.query is None:
            return result

        q7 = p7.query.copy()
        q28 = p28.query.copy()

        # 日次平均で正規化
        q7["imp_per_day"] = q7["表示回数"] / max(p7.days, 1)
        q28["imp_per_day"] = q28["表示回数"] / max(p28.days, 1)

        # マージ
        merged = pd.merge(
            q7[["上位のクエリ", "imp_per_day", "表示回数", "クリック数", "掲載順位"]].rename(
                columns={"imp_per_day": "imp_per_day_7d", "表示回数": "imp_7d", "クリック数": "clicks_7d", "掲載順位": "pos_7d"}
            ),
            q28[["上位のクエリ", "imp_per_day", "表示回数", "クリック数", "掲載順位"]].rename(
                columns={"imp_per_day": "imp_per_day_28d", "表示回数": "imp_28d", "クリック数": "clicks_28d", "掲載順位": "pos_28d"}
            ),
            on="上位のクエリ", how="outer"
        ).fillna({
            "imp_per_day_7d": 0, "imp_7d": 0, "clicks_7d": 0,
            "imp_per_day_28d": 0, "imp_28d": 0, "clicks_28d": 0,
        })

        # 順位は欠損時 NaN のまま（比較から除外）
        merged["imp_diff_per_day"] = merged["imp_per_day_7d"] - merged["imp_per_day_28d"]

        # ── 伸びているクエリ ──
        growing = merged[
            (merged["imp_diff_per_day"] >= self.SIGNIFICANT_IMP_DIFF / 4)  # 1日あたり1.25以上の増
            & (merged["imp_per_day_28d"] >= 1)
        ].sort_values("imp_diff_per_day", ascending=False).head(15)
        result["growing"] = growing.to_dict("records")

        # ── 落ちているクエリ ──
        declining = merged[
            (merged["imp_diff_per_day"] <= -self.SIGNIFICANT_IMP_DIFF / 4)
            & (merged["imp_per_day_28d"] >= 1)
        ].sort_values("imp_diff_per_day", ascending=True).head(15)
        result["declining"] = declining.to_dict("records")

        # ── 新たに表示されたクエリ ──
        new = merged[
            (merged["imp_28d"] == 0)
            & (merged["imp_7d"] >= 3)
        ].sort_values("imp_7d", ascending=False).head(10)
        result["new_appearing"] = new.to_dict("records")

        # ── 表示されなくなったクエリ（前期間に多かったのに今期間0） ──
        disappear = merged[
            (merged["imp_7d"] == 0)
            & (merged["imp_per_day_28d"] >= 1)
        ].sort_values("imp_28d", ascending=False).head(10)
        result["disappearing"] = disappear.to_dict("records")

        # ── 順位改善 ──
        pos_changed = merged.dropna(subset=["pos_7d", "pos_28d"])
        pos_changed = pos_changed[
            (pos_changed["imp_7d"] >= self.MIN_IMP_FOR_COMPARISON)
            & (pos_changed["imp_28d"] >= self.MIN_IMP_FOR_COMPARISON)
        ].copy()
        pos_changed["pos_diff"] = pos_changed["pos_7d"] - pos_changed["pos_28d"]  # 負=改善

        improved = pos_changed[pos_changed["pos_diff"] <= -self.POSITION_CHANGE_THRESHOLD].sort_values("pos_diff").head(10)
        result["position_improved"] = improved.to_dict("records")

        dropped = pos_changed[pos_changed["pos_diff"] >= self.POSITION_CHANGE_THRESHOLD].sort_values("pos_diff", ascending=False).head(10)
        result["position_dropped"] = dropped.to_dict("records")

        # ── 「あと一歩」11-20位（3か月データで） ──
        if p3m and p3m.query is not None:
            q3m = p3m.query
            almost = q3m[
                (q3m["掲載順位"] >= 11)
                & (q3m["掲載順位"] <= 20)
                & (q3m["表示回数"] >= 20)
            ].sort_values("表示回数", ascending=False).head(10)
            result["almost_top10"] = almost.to_dict("records")

            # ── 高表示・低CTR ──
            ctr_lost = q3m[
                (q3m["表示回数"] >= 100)
                & (q3m["クリック数"] == 0)
            ].sort_values("表示回数", ascending=False).head(10)
            result["ctr_lost"] = ctr_lost.to_dict("records")

        return result

    # ════════════════════════════════════════════════
    # ページ差分
    # ════════════════════════════════════════════════

    def _compare_pages(self, p7, p28, p3m) -> dict:
        """ページレベルの差分検出"""
        result = {
            "growing": [],
            "declining": [],
            "top_performers": [],
            "underperformers": [],
            "rewrite_priority": [],
        }

        if p28 is None or p28.page is None:
            return result

        # ── 28日 vs 3か月 で伸び/減衰判定 ──
        if p3m and p3m.page is not None:
            p28d = p28.page.copy()
            p3md = p3m.page.copy()
            p28d["imp_per_day"] = p28d["表示回数"] / max(p28.days, 1)
            p28d["clicks_per_day"] = p28d["クリック数"] / max(p28.days, 1)
            p3md["imp_per_day"] = p3md["表示回数"] / max(p3m.days, 1)
            p3md["clicks_per_day"] = p3md["クリック数"] / max(p3m.days, 1)

            merged = pd.merge(
                p28d[["上位のページ", "imp_per_day", "clicks_per_day", "表示回数", "クリック数", "掲載順位"]].rename(
                    columns={"imp_per_day": "ipd_28", "clicks_per_day": "cpd_28",
                             "表示回数": "imp_28", "クリック数": "clk_28", "掲載順位": "pos_28"}
                ),
                p3md[["上位のページ", "imp_per_day", "clicks_per_day", "表示回数", "クリック数", "掲載順位"]].rename(
                    columns={"imp_per_day": "ipd_3m", "clicks_per_day": "cpd_3m",
                             "表示回数": "imp_3m", "クリック数": "clk_3m", "掲載順位": "pos_3m"}
                ),
                on="上位のページ", how="outer"
            ).fillna(0)

            merged["imp_diff_per_day"] = merged["ipd_28"] - merged["ipd_3m"]
            merged["click_diff_per_day"] = merged["cpd_28"] - merged["cpd_3m"]

            growing = merged[
                (merged["imp_diff_per_day"] >= 2)
                & (merged["ipd_3m"] >= 1)
            ].sort_values("imp_diff_per_day", ascending=False).head(10)
            result["growing"] = growing.to_dict("records")

            declining = merged[
                (merged["imp_diff_per_day"] <= -2)
                & (merged["ipd_3m"] >= 1)
            ].sort_values("imp_diff_per_day").head(10)
            result["declining"] = declining.to_dict("records")

        # ── トップパフォーマー（3か月のクリック数順） ──
        if p3m and p3m.page is not None:
            top = p3m.page.sort_values("クリック数", ascending=False).head(10)
            result["top_performers"] = top.to_dict("records")

            # ── アンダーパフォーマー（表示多・クリック少） ──
            under = p3m.page[
                (p3m.page["表示回数"] >= 200)
                & (p3m.page["クリック数"] <= 2)
            ].sort_values("表示回数", ascending=False).head(10)
            result["underperformers"] = under.to_dict("records")

            # ── リライト優先度スコア計算 ──
            result["rewrite_priority"] = self._calc_rewrite_priority(p3m.page)

        return result

    def _calc_rewrite_priority(self, page_df: pd.DataFrame) -> list:
        """
        リライト優先度スコア = 「機会損失の大きさ」
        スコア = 表示数 × (期待CTR - 実CTR)  ※順位による期待CTR表を使用

        同一ページのアンカーリンク（#toc1等）は集約してカウントする。
        """
        # アンカーを除去してページ単位で集計
        df = page_df.copy()
        df["ページbase"] = df["上位のページ"].str.split("#").str[0]
        # 同一ページbaseごとに集約（表示とクリックは合計、順位は表示加重平均）
        if df["ページbase"].nunique() < len(df):
            df["_weighted_pos"] = df["掲載順位"] * df["表示回数"]
            agg = df.groupby("ページbase", as_index=False).agg({
                "クリック数": "sum",
                "表示回数": "sum",
                "_weighted_pos": "sum",
            })
            agg["掲載順位"] = agg["_weighted_pos"] / agg["表示回数"]
            agg["CTR"] = agg["クリック数"] / agg["表示回数"] * 100
            agg = agg.rename(columns={"ページbase": "上位のページ"})
            page_df = agg[["上位のページ", "クリック数", "表示回数", "CTR", "掲載順位"]]
        # 順位ごとの期待CTR（業界一般的な目安）
        expected_ctr_by_position = {
            1: 30, 2: 17, 3: 11, 4: 8, 5: 6, 6: 4.5, 7: 3.5, 8: 3, 9: 2.5, 10: 2.5,
            11: 1.8, 12: 1.5, 13: 1.2, 14: 1.0, 15: 0.9,
            16: 0.7, 17: 0.6, 18: 0.5, 19: 0.45, 20: 0.4,
        }

        rows = []
        for _, row in page_df.iterrows():
            pos = row.get("掲載順位", 100)
            imp = row.get("表示回数", 0)
            clicks = row.get("クリック数", 0)
            actual_ctr = (clicks / imp * 100) if imp > 0 else 0

            # 期待CTR取得（順位を四捨五入）
            pos_int = int(round(pos))
            expected_ctr = expected_ctr_by_position.get(pos_int, 0.3)  # 21位以下は0.3%

            # 「あと一歩で1ページ目」ボーナス
            in_top20_bonus = 1.5 if 11 <= pos <= 20 else 1.0

            # 機会損失スコア
            missed_clicks = imp * (expected_ctr - actual_ctr) / 100
            score = max(0, missed_clicks) * in_top20_bonus

            # リライト推奨理由
            reasons = []
            if 11 <= pos <= 20 and imp >= 50:
                reasons.append("11-20位の押し上げ候補（1ページ目射程）")
                category = "押し上げ"
            elif pos <= 10 and actual_ctr < expected_ctr * 0.7:
                reasons.append(f"1ページ目だがCTRが期待値の{actual_ctr/expected_ctr*100:.0f}%")
                category = "CTR改善"
            elif imp >= 300 and clicks == 0:
                reasons.append("大量表示だがクリック0（メタ/タイトル改善）")
                category = "タイトル改善"
            elif imp >= 200 and actual_ctr < 1 and pos > 20:
                reasons.append("内容拡充で順位押し上げ余地")
                category = "リライト"
            elif imp >= 100 and pos > 30:
                reasons.append("順位が大きく遠い・検索意図再設計")
                category = "再設計"
            else:
                continue  # スコアリング対象外

            rows.append({
                "url": row.get("上位のページ", ""),
                "impressions": int(imp),
                "clicks": int(clicks),
                "ctr": round(actual_ctr, 2),
                "position": round(pos, 1),
                "expected_ctr": expected_ctr,
                "missed_clicks_per_period": round(missed_clicks, 1),
                "priority_score": round(score, 1),
                "category": category,
                "reason": " / ".join(reasons),
            })

        rows.sort(key=lambda x: x["priority_score"], reverse=True)
        return rows[:15]

    # ════════════════════════════════════════════════
    # 良い/悪い変化の仕分け
    # ════════════════════════════════════════════════

    def _classify_changes(self, summary: dict, query_diffs: dict, page_diffs: dict) -> tuple:
        """サマリ・差分から「良い変化」「悪い変化」を構造化リストにまとめる"""
        good = []
        bad = []

        # ── サマリ変化（7日 vs 28日 をメインに使う） ──
        d = summary.get("diff_7d_vs_28d") or {}
        if d:
            # クリック
            if d.get("clicks_ratio") is not None:
                ratio = d["clicks_ratio"]
                if ratio >= 120:
                    good.append({
                        "category": "全体クリック",
                        "title": f"日次クリック数が28日平均より{ratio - 100:.0f}%増加",
                        "detail": f"{summary['p28']['daily_avg_clicks']} → {summary['p7']['daily_avg_clicks']} clicks/日",
                    })
                elif ratio <= 70:
                    bad.append({
                        "category": "全体クリック",
                        "severity": "high" if ratio < 50 else "mid",
                        "title": f"日次クリック数が28日平均比{ratio:.0f}%まで低下",
                        "detail": f"{summary['p28']['daily_avg_clicks']} → {summary['p7']['daily_avg_clicks']} clicks/日",
                    })

            # 表示数
            if d.get("imp_ratio") is not None:
                ratio = d["imp_ratio"]
                if ratio >= 115:
                    good.append({
                        "category": "全体表示数",
                        "title": f"日次表示回数が28日平均より{ratio - 100:.0f}%増加",
                        "detail": f"{summary['p28']['daily_avg_impressions']:.0f} → {summary['p7']['daily_avg_impressions']:.0f} 表示/日",
                    })
                elif ratio <= 80:
                    bad.append({
                        "category": "全体表示数",
                        "severity": "mid",
                        "title": f"日次表示回数が28日平均比{ratio:.0f}%まで低下",
                        "detail": f"{summary['p28']['daily_avg_impressions']:.0f} → {summary['p7']['daily_avg_impressions']:.0f} 表示/日",
                    })

            # 順位
            if d.get("position_diff") is not None:
                pd_val = d["position_diff"]
                if pd_val <= -3:
                    good.append({
                        "category": "平均順位",
                        "title": f"平均掲載順位が{abs(pd_val):.1f}位改善",
                        "detail": f"{summary['p28']['avg_position']} → {summary['p7']['avg_position']}位",
                    })
                elif pd_val >= 3:
                    bad.append({
                        "category": "平均順位",
                        "severity": "high" if pd_val >= 5 else "mid",
                        "title": f"平均掲載順位が{pd_val:.1f}位悪化",
                        "detail": f"{summary['p28']['avg_position']} → {summary['p7']['avg_position']}位",
                    })

            # CTR
            if d.get("ctr_diff") is not None:
                ctr_d = d["ctr_diff"]
                if ctr_d >= 0.2:
                    good.append({
                        "category": "CTR",
                        "title": f"平均CTRが+{ctr_d:.2f}pt向上",
                        "detail": f"{summary['p28']['avg_ctr']}% → {summary['p7']['avg_ctr']}%",
                    })
                elif ctr_d <= -0.2:
                    bad.append({
                        "category": "CTR",
                        "severity": "mid",
                        "title": f"平均CTRが{ctr_d:.2f}pt低下",
                        "detail": f"{summary['p28']['avg_ctr']}% → {summary['p7']['avg_ctr']}%",
                    })

        # ── 新規出現クエリ ──
        if query_diffs["new_appearing"]:
            queries = [q["上位のクエリ"] for q in query_diffs["new_appearing"][:5]]
            good.append({
                "category": "新規表示クエリ",
                "title": f"直近7日に新たに表示されたクエリが{len(query_diffs['new_appearing'])}件",
                "detail": "例: " + " / ".join(queries),
                "queries": queries,
            })

        # ── 表示が伸びたクエリ ──
        if query_diffs["growing"]:
            queries = [q["上位のクエリ"] for q in query_diffs["growing"][:5]]
            good.append({
                "category": "クエリ表示増",
                "title": f"表示が伸びているクエリ {len(query_diffs['growing'])}件",
                "detail": "例: " + " / ".join(queries),
                "queries": queries,
            })

        # ── 順位改善クエリ ──
        if query_diffs["position_improved"]:
            queries = [f"{q['上位のクエリ']} ({q['pos_28d']:.0f}→{q['pos_7d']:.0f}位)" for q in query_diffs["position_improved"][:5]]
            good.append({
                "category": "順位改善",
                "title": f"順位が改善したクエリ {len(query_diffs['position_improved'])}件",
                "detail": " / ".join(queries),
            })

        # ── 表示が落ちたクエリ ──
        if query_diffs["declining"]:
            queries = [q["上位のクエリ"] for q in query_diffs["declining"][:5]]
            bad.append({
                "category": "クエリ表示減",
                "severity": "mid",
                "title": f"表示が落ちているクエリ {len(query_diffs['declining'])}件",
                "detail": "例: " + " / ".join(queries),
                "queries": queries,
            })

        # ── 消えたクエリ ──
        if query_diffs["disappearing"]:
            queries = [q["上位のクエリ"] for q in query_diffs["disappearing"][:5]]
            bad.append({
                "category": "クエリ消失",
                "severity": "high",
                "title": f"前期間に表示されていたが7日では表示0のクエリ {len(query_diffs['disappearing'])}件",
                "detail": "例: " + " / ".join(queries),
                "queries": queries,
            })

        # ── 順位下落クエリ ──
        if query_diffs["position_dropped"]:
            queries = [f"{q['上位のクエリ']} ({q['pos_28d']:.0f}→{q['pos_7d']:.0f}位)" for q in query_diffs["position_dropped"][:5]]
            bad.append({
                "category": "順位下落",
                "severity": "high",
                "title": f"順位が下落したクエリ {len(query_diffs['position_dropped'])}件",
                "detail": " / ".join(queries),
            })

        # ── ページレベル（28日 vs 3か月） ──
        if page_diffs["growing"]:
            urls = [p["上位のページ"] for p in page_diffs["growing"][:3]]
            good.append({
                "category": "ページ表示増",
                "title": f"表示が伸びているページ {len(page_diffs['growing'])}件",
                "detail": " / ".join(urls),
            })

        if page_diffs["declining"]:
            urls = [p["上位のページ"] for p in page_diffs["declining"][:3]]
            bad.append({
                "category": "ページ表示減",
                "severity": "mid",
                "title": f"表示が落ちているページ {len(page_diffs['declining'])}件",
                "detail": " / ".join(urls),
            })

        return good, bad
