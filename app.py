# -*- coding: utf-8 -*-
"""
pksp.jp 統合SEOツールスイート
- ファクタリング記事リライト診断ツール
- GSC定期分析テンプレート
Render.com / Railway / Fly.io 等のPaaSにそのままデプロイ可能。
"""
import os
import io
import json
import logging
import tempfile
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, Response

# ── ファクタリング診断モジュール ──
from modules.crawler import PageAnalyzer
from modules.search_engine import CompetitorSearch
from modules.analyzer import DiagnosisEngine
from modules.report_generator import ReportBuilder
from modules.llm_diagnoser import LLMDiagnoser

# ── GSC分析モジュール ──
from modules.gsc_csv_loader import CSVLoader, PeriodDataset
from modules.gsc_diff_engine import DiffEngine
from modules.gsc_hypothesis_engine import HypothesisEngine
from modules.gsc_rewrite_recommender import RewriteRecommender
from modules.gsc_report_builder import ReportBuilder as GSCReportBuilder

# ── ロギング ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pksp-tools")

# ── Flask ──
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


# ════════════════════════════════════════════════════
# Basic 認証（環境変数 BASIC_AUTH_USER / BASIC_AUTH_PASS が
# 設定されている場合のみ有効。未設定なら公開モード）
# ════════════════════════════════════════════════════
def check_auth(username, password):
    expected_user = os.environ.get("BASIC_AUTH_USER", "")
    expected_pass = os.environ.get("BASIC_AUTH_PASS", "")
    if not expected_user or not expected_pass:
        return True  # 環境変数未設定なら認証スキップ
    return username == expected_user and password == expected_pass


def authenticate():
    return Response(
        "認証が必要です。", 401,
        {"WWW-Authenticate": 'Basic realm="pksp.jp Tools"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not os.environ.get("BASIC_AUTH_USER"):
            return f(*args, **kwargs)  # 認証無効
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════
# トップページ（ツール選択）
# ════════════════════════════════════════════════════
@app.route("/")
@requires_auth
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    """Render / Railway 等のヘルスチェック用"""
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/api/status")
def status():
    """LLM / SerpAPI 等の設定状況を返す"""
    llm = LLMDiagnoser()
    return jsonify({
        "llm_available": llm.is_available,
        "llm_provider": llm.provider,
        "serpapi_configured": bool(os.environ.get("SERPAPI_KEY")),
        "google_cse_configured": bool(os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_CX")),
        "basic_auth_enabled": bool(os.environ.get("BASIC_AUTH_USER")),
    })


# ════════════════════════════════════════════════════
# ① ファクタリング記事リライト診断ツール
# ════════════════════════════════════════════════════
@app.route("/factoring")
@requires_auth
def factoring_index():
    return render_template("factoring.html")


@app.route("/api/factoring/diagnose", methods=["POST"])
@requires_auth
def factoring_diagnose():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    role = (data.get("role") or "流入").strip()
    llm_mode = (data.get("llm_mode") or "auto").strip()

    if not url or not keyword:
        return jsonify({"error": "記事URLとメインキーワードは必須です。"}), 400

    logger.info("[factoring] 診断開始: url=%s keyword=%s", url, keyword)

    try:
        page_analyzer = PageAnalyzer()
        own_article = page_analyzer.analyze(url)

        searcher = CompetitorSearch()
        search_result = searcher.search(keyword, num_results=8, exclude_url=url)
        competitor_urls = search_result.get("urls", [])
        paa_questions = search_result.get("paa", [])
        related_suggestions = search_result.get("suggestions", [])

        competitors = []
        for c_url in competitor_urls:
            try:
                comp = page_analyzer.analyze(c_url)
                if comp.get("headings"):
                    competitors.append(comp)
            except Exception as e:
                logger.warning("競合クロール失敗 %s: %s", c_url, e)

        # LLM or ルールベース
        use_llm = llm_mode != "rule"
        llm_diagnoser = LLMDiagnoser() if use_llm else None

        if use_llm and llm_diagnoser and llm_diagnoser.is_available:
            llm_result = llm_diagnoser.diagnose(
                own_article=own_article,
                competitors=competitors,
                keyword=keyword,
                role=role,
                paa_questions=paa_questions,
                related_suggestions=related_suggestions,
            )
            if llm_result.get("mode") == "llm":
                scores = llm_result.get("extracted_scores", {})
                builder = ReportBuilder()
                report = builder.build_llm_report(
                    llm_result=llm_result,
                    own_article=own_article,
                    competitors=competitors,
                    keyword=keyword,
                    role=role,
                    total_score=scores.get("total_score") or 0,
                    category_scores=scores.get("category_scores", {}),
                )
                return jsonify({"success": True, "report": report})

        # ルールベース
        engine = DiagnosisEngine()
        diagnosis = engine.run_diagnosis(
            own_article=own_article,
            competitors=competitors,
            keyword=keyword,
            role=role,
            paa_questions=paa_questions,
            related_suggestions=related_suggestions,
        )
        builder = ReportBuilder()
        report = builder.build(
            diagnosis=diagnosis,
            own_article=own_article,
            competitors=competitors,
            keyword=keyword,
            role=role,
        )
        return jsonify({"success": True, "report": report})

    except Exception as e:
        logger.exception("[factoring] 診断エラー")
        return jsonify({"error": f"診断中にエラーが発生しました: {str(e)}"}), 500


# ════════════════════════════════════════════════════
# ② GSC定期分析テンプレート
# ════════════════════════════════════════════════════
@app.route("/gsc")
@requires_auth
def gsc_index():
    return render_template("gsc.html")


@app.route("/api/gsc/analyze", methods=["POST"])
@requires_auth
def gsc_analyze():
    """3期間のCSVをアップロードして分析"""
    try:
        loader = CSVLoader()
        datasets = {}
        period_map = {
            "7d": "7日間",
            "28d": "28日間",
            "3m": "3か月",
        }

        for period_key, label in period_map.items():
            ds = PeriodDataset(label)
            field = f"period_{period_key}_files"
            files = request.files.getlist(field)
            if not files:
                continue
            for f in files:
                if not f.filename:
                    continue
                content = f.read()
                try:
                    text = content.decode("utf-8-sig")
                except UnicodeDecodeError:
                    try:
                        text = content.decode("shift-jis")
                    except UnicodeDecodeError:
                        text = content.decode("utf-8", errors="ignore")
                result = loader.load_from_text(text, f.filename)
                if result.get("df") is not None:
                    ds.set(result["type"], result["df"])
            datasets[period_key] = ds
            logger.info("[gsc] %s: clicks=%s imp=%s", label, ds.total_clicks, ds.total_impressions)

        if not any(ds.has_data() for ds in datasets.values()):
            return jsonify({"error": "有効なCSVファイルがアップロードされませんでした。"}), 400

        ds_7d = datasets.get("7d") or PeriodDataset("7日間")
        ds_28d = datasets.get("28d") or PeriodDataset("28日間")
        ds_3m = datasets.get("3m") or PeriodDataset("3か月")

        de = DiffEngine()
        diff = de.compare_periods(ds_7d, ds_28d, ds_3m)

        he = HypothesisEngine()
        hypos = he.generate(diff, ds_7d, ds_28d, ds_3m)

        rr = RewriteRecommender()
        recs = rr.recommend(diff, ds_3m, top_n=10)

        rb = GSCReportBuilder()
        report = rb.build(ds_7d, ds_28d, ds_3m, diff, hypos, recs)

        # 履歴保存
        history_path = os.path.join(DATA_DIR, "gsc_history.json")
        history = []
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError):
                history = []
        history.append({
            "date": datetime.now().isoformat(),
            "7d_clicks": ds_7d.total_clicks,
            "28d_clicks": ds_28d.total_clicks,
            "3m_clicks": ds_3m.total_clicks,
        })
        history = history[-100:]  # 直近100件のみ保持
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "report": report})

    except Exception as e:
        logger.exception("[gsc] 分析エラー")
        return jsonify({"error": f"分析中にエラーが発生しました: {str(e)}"}), 500


@app.route("/api/gsc/history")
@requires_auth
def gsc_history():
    history_path = os.path.join(DATA_DIR, "gsc_history.json")
    if not os.path.exists(history_path):
        return jsonify({"success": True, "history": []})
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return jsonify({"success": True, "history": json.load(f)})
    except (json.JSONDecodeError, OSError):
        return jsonify({"success": True, "history": []})


# ════════════════════════════════════════════════════
# 起動
# ════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
