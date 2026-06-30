# -*- coding: utf-8 -*-
"""
リライト推奨エンジン
「次に直すべき記事」を優先順位付きでリストアップする。

各記事に対して、
- リライトの種類（タイトル改善 / 内容拡充 / 検索意図再設計）
- pksp.jp 独自の打ち手（八木氏視点を含む）
- 推定インパクト（機会損失クリック数）
を付与する。
"""
import logging

logger = logging.getLogger("gsc.rewriter")


class RewriteRecommender:
    """次に直すべき記事を推奨する"""

    def recommend(self, diff_result: dict, period_3m, top_n: int = 10) -> list:
        """
        診断ツールへの投入優先順位付きリストを返す

        Returns:
            [
                {
                    rank: 順位,
                    url: URL,
                    category: 改善カテゴリ,
                    current_state: 現状指標,
                    related_queries: そのページが取得しているクエリ,
                    rewrite_focus: リライトの焦点,
                    pksp_unique_angle: pksp独自の打ち手,
                    estimated_impact: 推定インパクト,
                    next_step: 次のアクション,
                }
            ]
        """
        page_diffs = diff_result.get("page_diffs", {})
        priority = page_diffs.get("rewrite_priority", [])

        # クエリ-ページの関連を取得
        related_query_map = self._build_query_page_map(period_3m)

        recommendations = []
        for i, item in enumerate(priority[:top_n], 1):
            url = item["url"]
            category = item["category"]

            # そのページに関連するクエリ
            related_queries = related_query_map.get(url, [])[:5]

            # リライトの焦点
            rewrite_focus = self._generate_rewrite_focus(item)

            # pksp.jp 独自の打ち手
            pksp_angle = self._generate_pksp_angle(item, related_queries)

            # 推定インパクト
            impact = self._estimate_impact(item)

            recommendations.append({
                "rank": i,
                "url": url,
                "category": category,
                "current_state": {
                    "impressions": item["impressions"],
                    "clicks": item["clicks"],
                    "ctr": item["ctr"],
                    "position": item["position"],
                },
                "missed_clicks": item.get("missed_clicks_per_period", 0),
                "priority_score": item.get("priority_score", 0),
                "reason": item.get("reason", ""),
                "related_queries": related_queries,
                "rewrite_focus": rewrite_focus,
                "pksp_unique_angle": pksp_angle,
                "estimated_impact": impact,
                "next_step": self._next_step(item),
            })

        return recommendations

    def _build_query_page_map(self, period_3m) -> dict:
        """
        どのページがどのクエリで表示されているかのマップを作る。
        GSCのCSVは page と query が別々なので厳密な対応は不可だが、
        URLスラッグからクエリの関連を推測する。
        """
        result = {}
        if period_3m is None or period_3m.query is None or period_3m.page is None:
            return result

        pages = period_3m.page
        queries = period_3m.query.sort_values("表示回数", ascending=False)

        for _, page_row in pages.iterrows():
            url = page_row["上位のページ"]
            slug = url.rstrip("/").split("/")[-1]
            slug_words = self._extract_url_keywords(url)

            # URLに含まれるキーワードに関連するクエリを探す
            matched = []
            for _, q_row in queries.iterrows():
                q = q_row["上位のクエリ"]
                # スラッグキーワードがクエリに含まれているか
                if any(word in q for word in slug_words):
                    matched.append({
                        "query": q,
                        "impressions": int(q_row["表示回数"]),
                        "clicks": int(q_row["クリック数"]),
                        "position": round(q_row["掲載順位"], 1),
                    })
                if len(matched) >= 5:
                    break
            result[url] = matched

        return result

    def _extract_url_keywords(self, url: str) -> list:
        """URLからキーワード推測（ディレクトリ名・スラッグ番号）"""
        keywords = []
        # ディレクトリ名から推測
        if "funding-by-industry" in url:
            keywords.extend(["業種", "業界"])
            # 番号で具体的業種までは分からないが、業種系のクエリを優先候補に
            keywords.extend(["運送業", "製造業", "飲食店", "建設", "介護", "医療", "物流", "it"])
        elif "factoring-review" in url:
            keywords.extend(["口コミ", "評判", "レビュー"])
            keywords.extend(["pmg", "olta", "ラボル", "アクセルファクター", "ペイトナー", "ピーエムジー"])
        elif "factoring" in url:
            keywords.extend(["ファクタリング"])
        elif "author" in url:
            keywords.extend(["八木", "執筆者", "ライター"])
        return keywords

    def _generate_rewrite_focus(self, item: dict) -> list:
        """改善の焦点を構造化して返す"""
        category = item["category"]
        focus = []

        if category == "押し上げ":
            focus.append("競合上位記事との論点差分を埋める（不足トピックの追加）")
            focus.append("見出し階層の整理（h2/h3）と検索意図への明確な答え")
            focus.append("E-E-A-T要素の強化（執筆者・出典・更新日・デメリット）")
            focus.append("内部リンクの強化（ピラーページ・関連記事への導線）")
        elif category == "CTR改善":
            focus.append("タイトルの再設計（キーワード前方配置・数字・ベネフィット）")
            focus.append("メタディスクリプションの改善（120-140文字・行動を促す表現）")
            focus.append("構造化データ（FAQ・HowTo等）の追加でリッチリザルト狙い")
        elif category == "タイトル改善":
            focus.append("タイトル再設計が最優先（現状クリック0は致命的）")
            focus.append("検索意図の再確認（同じKWで上位記事は何を答えているか）")
        elif category == "リライト":
            focus.append("内容の網羅性向上（競合が扱う論点を漏れなくカバー）")
            focus.append("独自情報の追加でコンテンツ価値を高める")
            focus.append("文字数を競合平均レベルまで拡充")
        elif category == "再設計":
            focus.append("検索意図の再分析 — そもそも今の構成が読者ニーズに合っているか")
            focus.append("URL構成・カテゴリ配置の妥当性を再検討")
            focus.append("場合によっては記事統合 or 新規作成も視野に")

        return focus

    def _generate_pksp_angle(self, item: dict, related_queries: list) -> list:
        """pksp.jp 独自の打ち手（八木氏視点）を生成"""
        url = item["url"]
        angles = []

        # 業種ページ
        if "funding-by-industry" in url:
            angles.append("八木氏の銀行員時代の業種知見（業種ごとの売掛金サイクル特性）を一次情報として追加")
            angles.append("「銀行融資が通りにくい業種」と「ファクタリングが向く業種」の比較表")
            angles.append("業種特有のキャッシュフロー問題と、その解決策の専門家解説")

        # 業者レビューページ
        elif "factoring-review" in url:
            angles.append("八木氏の「銀行員時代に取引先として見た優良/要注意業者の特徴」を加える")
            angles.append("業者選びで本当に重要な指標（資金力・契約透明性等）を専門家視点で解説")
            angles.append("公開されている情報（登記・資本金・取引実績）から優良業者を見抜く方法")

        # 一般ファクタリング解説
        elif "/factoring/" in url:
            angles.append("元都市銀行法人営業として、銀行融資とファクタリングの実務的な使い分けを解説")
            angles.append("銀行から見た「ファクタリング利用企業」の評価実態（与信への影響）")
            angles.append("八木氏自身が見てきた成功事例・失敗事例の一次情報")

        # 執筆者ページ
        elif "/author" in url:
            angles.append("プロフィールの強化（経歴・実績・専門領域を具体化）")
            angles.append("出版・登壇・取材実績の追加でE-E-A-T強化")

        # それ以外
        else:
            angles.append("八木氏の銀行員視点を最低1つの見出しに加える")
            angles.append("YMYL領域に必要な出典明記（金融庁・法務省等）")

        # クエリベースの追加打ち手
        if related_queries:
            top_query = related_queries[0]["query"]
            angles.append(f"主要流入クエリ「{top_query}」の検索意図に明確に答える見出しを冒頭近くに配置")

        return angles

    def _estimate_impact(self, item: dict) -> dict:
        """改善した場合の推定インパクト"""
        impressions = item["impressions"]
        current_clicks = item["clicks"]
        current_ctr = item["ctr"]
        position = item["position"]

        # 期待CTR
        expected_ctr_by_position = {
            (1, 3): 18,
            (4, 5): 7,
            (6, 10): 3.5,
            (11, 15): 1.5,
            (16, 20): 0.6,
            (21, 30): 0.3,
        }
        expected_ctr = 0.2
        for (lo, hi), ctr in expected_ctr_by_position.items():
            if lo <= position <= hi:
                expected_ctr = ctr
                break

        # 押し上げシナリオ（11-20位 → 8位を想定）
        if 11 <= position <= 20:
            target_ctr = 4
            potential_clicks = int(impressions * target_ctr / 100)
            return {
                "scenario": "リライトで11位以下→8位以内に押し上げ",
                "current_clicks": current_clicks,
                "potential_clicks_per_period": potential_clicks,
                "uplift": potential_clicks - current_clicks,
            }
        # CTR改善シナリオ
        elif position <= 10 and current_ctr < expected_ctr * 0.7:
            potential_clicks = int(impressions * expected_ctr / 100)
            return {
                "scenario": "タイトル/メタ改善で期待CTRに到達",
                "current_clicks": current_clicks,
                "potential_clicks_per_period": potential_clicks,
                "uplift": potential_clicks - current_clicks,
            }
        # その他
        else:
            target_ctr = max(expected_ctr, 1.0)
            potential_clicks = int(impressions * target_ctr / 100)
            return {
                "scenario": "リライトで内容を改善し競争力強化",
                "current_clicks": current_clicks,
                "potential_clicks_per_period": potential_clicks,
                "uplift": potential_clicks - current_clicks,
            }

    def _next_step(self, item: dict) -> str:
        """次のアクションの一言"""
        category = item["category"]
        if category == "押し上げ":
            return "リライト診断ツールに投入 → 競合との論点差分を抽出 → 八木氏の一次情報を加えてリライト"
        elif category == "CTR改善":
            return "競合のタイトル/メタを実検索で確認 → タイトル再設計 → スニペット最適化"
        elif category == "タイトル改善":
            return "タイトルA/Bテスト3案作成 → メタディスクリプション同時改善"
        elif category == "リライト":
            return "リライト診断ツールで競合比較 → 不足トピック洗い出し → 八木氏の独自視点で埋める"
        elif category == "再設計":
            return "検索意図の再分析（実際のSERPを確認） → 構成案再作成 → 新規作成も検討"
        return "リライト診断ツールに投入"
