/* ════════════════════════════════════════════════
   ファクタリング記事リライト診断ツール
   フロントエンド JavaScript
   ════════════════════════════════════════════════ */

let currentReport = null;

/* ── 診断開始 ──────────────────────────────── */
function startDiagnosis() {
    const url = document.getElementById('urlInput').value.trim();
    const keyword = document.getElementById('keywordInput').value.trim();
    const role = document.getElementById('roleInput').value;
    const llmMode = document.getElementById('llmProviderInput') ? document.getElementById('llmProviderInput').value : 'auto';

    // バリデーション
    if (!url) {
        alert('記事URLを入力してください。');
        return;
    }
    if (!keyword) {
        alert('メインキーワードを入力してください。');
        return;
    }
    if (!url.match(/^https?:\/\//)) {
        alert('記事URLは http:// または https:// で始まる必要があります。');
        return;
    }

    // UI切替
    document.getElementById('inputSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('loadingSection').style.display = 'block';

    // ステップアニメーション開始
    animateSteps();

    // API呼び出し
    fetch('/api/factoring/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, keyword, role, llm_mode: llmMode }),
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
        } else if (data.success && data.report) {
            currentReport = data.report;
            displayReport(data.report);
        } else {
            showError('予期しないレスポンス形式です。');
        }
    })
    .catch(err => {
        showError('通信エラー: ' + err.message);
    });
}

/* ── ステップアニメーション ──────────────────── */
function animateSteps() {
    const steps = document.querySelectorAll('.step');
    steps.forEach(s => { s.classList.remove('active', 'done'); });

    let current = 0;
    const interval = setInterval(() => {
        if (current > 0) steps[current - 1].classList.add('done');
        if (current < steps.length) {
            steps[current].classList.add('active');
            current++;
        } else {
            clearInterval(interval);
        }
    }, 1100);
}

/* ── レポート表示 ────────────────────────────── */
function displayReport(report) {
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('resultSection').style.display = 'block';

    // 診断日
    document.getElementById('diagnosisDate').textContent = '診断日: ' + report.diagnosis_date;

    // 診断モードバッジ
    const modeBadge = document.getElementById('diagnosisModeBadge');
    const mode = report.diagnosis_mode || 'rule_based';
    if (mode === 'llm') {
        const llmInfo = report.llm_info || {};
        modeBadge.innerHTML = `🤖 LLM診断 (${llmInfo.provider || ''} / ${llmInfo.model || ''})`;
        modeBadge.className = 'mode-badge llm';
        modeBadge.style.display = 'inline-block';
    } else {
        modeBadge.innerHTML = '⚙️ ルールベース診断';
        modeBadge.className = 'mode-badge rule';
        modeBadge.style.display = 'inline-block';
    }

    // LLMフォールバック警告
    const fallbackWarning = document.getElementById('llmFallbackWarning');
    if (report.llm_error) {
        fallbackWarning.innerHTML = `⚠️ LLM APIエラーによりルールベース診断にフォールバックしました: ${report.llm_error}`;
        fallbackWarning.style.display = 'block';
    } else {
        fallbackWarning.style.display = 'none';
    }

    // 前回比較
    if (report.previous_comparison) {
        const cmp = report.previous_comparison;
        const bar = document.getElementById('comparisonBar');
        const diff = cmp.score_diff;
        const diffClass = diff > 0 ? 'diff-up' : 'diff-down';
        const diffSign = diff > 0 ? '+' : '';
        bar.innerHTML = `
            <span>📊 前回診断（${cmp.previous_date}）との比較:</span>
            <span>前回 ${cmp.previous_score}点 → 今回 ${report.part1_report.total_score}点</span>
            <span class="${diffClass}">(${diffSign}${diff}点)</span>
        `;
        bar.style.display = 'flex';
    }

    displayTotalScore(report.part1_report);
    displayScoreBreakdown(report.part1_report);

    // モード別表示切替
    if (mode === 'llm') {
        // LLMモード: LLMレポート全文表示、ルールベース要素は非表示
        displayLLMReport(report.part1_report);
        document.getElementById('missingTopicsSection').style.display = 'none';
        document.getElementById('freshnessSection').style.display = 'none';
        document.getElementById('weakEeatSection').style.display = 'none';
        document.getElementById('paaSection').style.display = 'none';
        // 指示書モードラベル
        document.getElementById('instructionModeLabel').textContent = '🤖 LLM生成（' + (report.llm_info.model || '') + '）';
    } else {
        // ルールベースモード: 従来通り
        document.getElementById('llmReportSection').style.display = 'none';
        document.getElementById('missingTopicsSection').style.display = 'block';
        document.getElementById('freshnessSection').style.display = 'block';
        document.getElementById('weakEeatSection').style.display = 'block';
        displayMissingTopics(report.part1_report);
        displayFreshnessIssues(report.part1_report);
        displayWeakEeat(report.part1_report);
        displayPaaCoverage(report.part1_report);
        document.getElementById('instructionModeLabel').textContent = '⚙️ ルールベース生成';
    }

    displayCompetitorSummary(report.part1_report);
    displayInstructions(report.part2_instructions);
}

/* ── LLMレポート表示 ─────────────────────────── */
function displayLLMReport(part1) {
    const section = document.getElementById('llmReportSection');
    const textEl = document.getElementById('llmReportText');
    const llmText = part1.llm_report_text || '';
    if (llmText) {
        textEl.textContent = llmText;
        section.style.display = 'block';
    } else {
        section.style.display = 'none';
    }
}

/* ── 総合スコア ──────────────────────────────── */
function displayTotalScore(part1) {
    const score = part1.total_score;
    document.getElementById('totalScoreNumber').textContent = score;

    const grade = part1.grade;
    const gradeClass = 'grade-' + grade.charAt(0);
    const gradeEl = document.getElementById('totalScoreGrade');
    gradeEl.textContent = grade;
    gradeEl.className = 'total-score-grade ' + gradeClass;

    // スコアに応じて数字の色を変更
    const numEl = document.getElementById('totalScoreNumber');
    if (score >= 70) numEl.style.color = 'var(--success)';
    else if (score >= 50) numEl.style.color = 'var(--warning)';
    else numEl.style.color = 'var(--danger)';
}

/* ── スコア内訳 ──────────────────────────────── */
function displayScoreBreakdown(part1) {
    const container = document.getElementById('scoreBreakdown');
    container.innerHTML = '';

    const scores = part1.category_scores;
    const order = ['topic_coverage', 'eeat', 'title_optimization', 'body_comprehensiveness', 'internal_links', 'cv_funnel', 'freshness'];

    for (const key of order) {
        const val = scores[key];
        const ratio = val.score / val.max;
        const isWeak = ratio < 0.6;
        const fillClass = ratio >= 0.7 ? 'good' : (ratio >= 0.4 ? 'mid' : 'weak');

        const item = document.createElement('div');
        item.className = 'score-bar-item';
        item.innerHTML = `
            <div class="score-bar-header">
                <span class="score-bar-label">${val.label}</span>
                <span class="score-bar-value ${isWeak ? 'weak' : ''}">${val.score}/${val.max}点</span>
            </div>
            <div class="score-bar-track">
                <div class="score-bar-fill ${fillClass}" style="width: ${ratio * 100}%"></div>
            </div>
            <div class="score-bar-detail">${val.details}</div>
        `;
        container.appendChild(item);
    }
}

/* ── 不足トピック TOP5 ───────────────────────── */
function displayMissingTopics(part1) {
    const container = document.getElementById('missingTopicsList');
    const topics = part1.missing_topics_top5 || [];

    if (topics.length === 0) {
        container.innerHTML = '<p style="color:var(--text-light);padding:12px;">不足トピックは検出されませんでした。網羅性は良好です。</p>';
        return;
    }

    container.innerHTML = '';
    topics.forEach((topic, i) => {
        const item = document.createElement('div');
        item.className = 'topic-item';
        item.innerHTML = `
            <div class="topic-rank">${i + 1}</div>
            <div class="topic-name">${topic.topic}</div>
            <div class="topic-coverage">
                <span class="coverage-num">${topic.competitor_coverage_count}</span>/${topic.competitor_coverage_count > 0 ? Math.ceil(topic.competitor_coverage_count / topic.competitor_coverage_ratio) : '?'}記事
                (${topic.competitor_coverage_ratio * 100 | 0}%)
            </div>
        `;
        container.appendChild(item);
    });
}

/* ── 鮮度問題 ────────────────────────────────── */
function displayFreshnessIssues(part1) {
    const container = document.getElementById('freshnessIssuesList');
    const issues = part1.freshness_issues || [];

    if (issues.length === 0) {
        container.innerHTML = '<p style="color:var(--text-light);padding:12px;">鮮度の問題は検出されませんでした。</p>';
        return;
    }

    container.innerHTML = '';
    issues.forEach(issue => {
        const item = document.createElement('div');
        item.className = 'issue-item freshness';
        const desc = issue.description || String(issue);
        item.innerHTML = `
            <span class="issue-icon">⏰</span>
            <span class="issue-text">${desc}</span>
        `;
        container.appendChild(item);
    });
}

/* ── 弱いE-E-A-T ─────────────────────────────── */
function displayWeakEeat(part1) {
    const container = document.getElementById('weakEeatList');
    const items = part1.weak_eeat || [];

    if (items.length === 0) {
        container.innerHTML = '<p style="color:var(--success);padding:12px;">✓ E-E-A-T要素は全て検出されました。良好な状態です。</p>';
        return;
    }

    container.innerHTML = '';
    items.forEach(item => {
        const el = document.createElement('div');
        el.className = 'issue-item';
        el.innerHTML = `
            <span class="issue-icon">⚠️</span>
            <span class="issue-text">
                <strong>${item.item}</strong> [${item.status}]<br>
                → ${item.recommendation}
            </span>
        `;
        container.appendChild(el);
    });
}

/* ── PAAカバー率 ─────────────────────────────── */
function displayPaaCoverage(part1) {
    const section = document.getElementById('paaSection');
    const container = document.getElementById('paaCoverageDisplay');
    const paa = part1.paa_coverage;

    if (!paa || paa.total === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    const ratio = Math.round(paa.coverage_ratio * 100);
    container.innerHTML = `
        <div class="paa-bar">
            <span class="paa-ratio">${ratio}%</span>
            <span>PAA ${paa.total}件中 ${paa.covered}件カバー / 未カバー ${paa.uncovered.length}件</span>
        </div>
        ${paa.uncovered.length > 0 ? '<div class="paa-uncovered"><strong>未カバーの質問:</strong>' + paa.uncovered.map(q => `<div class="paa-question">❓ ${q}</div>`).join('') + '</div>' : ''}
    `;
}

/* ── 競合サマリ ──────────────────────────────── */
function displayCompetitorSummary(part1) {
    const container = document.getElementById('competitorSummary');
    const comp = part1.competitor_summary;
    const urls = comp.urls || [];

    container.innerHTML = `
        <div class="competitor-info">
            <div class="competitor-stat">
                <div class="competitor-stat-num">${comp.count}</div>
                <div class="competitor-stat-label">競合記事数</div>
            </div>
            <div class="competitor-stat">
                <div class="competitor-stat-num">${comp.avg_word_count.toLocaleString()}</div>
                <div class="competitor-stat-label">競合平均文字数</div>
            </div>
        </div>
        <div class="competitor-urls">
            <strong>競合URL:</strong><br>
            ${urls.map(u => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`).join('<br>')}
        </div>
    `;
}

/* ── リライト指示書 ──────────────────────────── */
function displayInstructions(text) {
    document.getElementById('instructionText').textContent = text;
}

/* ── コピー機能 ──────────────────────────────── */
function copyInstructions() {
    const text = document.getElementById('instructionText').textContent;
    navigator.clipboard.writeText(text).then(() => {
        showToast('リライト指示書をコピーしました');
    }).catch(() => {
        showToast('コピーに失敗しました');
    });
}

function copyAllReport() {
    if (!currentReport) return;
    const text = formatFullReportText(currentReport);
    navigator.clipboard.writeText(text).then(() => {
        showToast('全レポートをコピーしました');
    }).catch(() => {
        showToast('コピーに失敗しました');
    });
}

/* ── ダウンロード機能 ────────────────────────── */
function downloadInstructions() {
    const text = document.getElementById('instructionText').textContent;
    downloadText(text, 'rewrite_instructions.txt');
}

function downloadFullReport() {
    if (!currentReport) return;
    const text = formatFullReportText(currentReport);
    downloadText(text, 'diagnosis_report.txt');
}

function downloadText(text, filename) {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
}

/* ── 全レポート整形（テキスト形式） ────────────── */
function formatFullReportText(report) {
    const p1 = report.part1_report;
    const lines = [];

    lines.push('═══════════════════════════════════════════════');
    lines.push('  ファクタリング記事リライト診断レポート');
    lines.push(`  診断日: ${report.diagnosis_date}`);
    lines.push('═══════════════════════════════════════════════');
    lines.push('');
    lines.push(`URL: ${report.input.url}`);
    lines.push(`タイトル: ${report.input.title}`);
    lines.push(`メインキーワード: ${report.input.keyword}`);
    lines.push(`記事の役割: ${report.input.role}`);
    lines.push('');
    lines.push('─── 第1部：診断レポート ───');
    lines.push('');
    lines.push(`総合スコア: ${p1.total_score}/100 (${p1.grade})`);
    lines.push('');

    const order = ['topic_coverage', 'eeat', 'title_optimization', 'body_comprehensiveness', 'internal_links', 'cv_funnel', 'freshness'];
    for (const key of order) {
        const val = p1.category_scores[key];
        lines.push(`  ${val.label}: ${val.score}/${val.max}点`);
        lines.push(`    → ${val.details}`);
    }
    lines.push('');

    // 不足トピック
    lines.push('■ 不足トピック TOP5');
    (p1.missing_topics_top5 || []).forEach((t, i) => {
        lines.push(`  ${i + 1}. ${t.topic} (${t.competitor_coverage_count}記事/${(t.competitor_coverage_ratio * 100 | 0)}%)`);
    });
    lines.push('');

    // 鮮度問題
    lines.push('■ 鮮度が怪しい数値・記述');
    (p1.freshness_issues || []).forEach(issue => {
        lines.push(`  □ ${issue.description || issue}`);
    });
    lines.push('');

    // E-E-A-T
    lines.push('■ 弱いE-E-A-T項目');
    (p1.weak_eeat || []).forEach(item => {
        lines.push(`  □ ${item.item} [${item.status}]`);
        lines.push(`    → ${item.recommendation}`);
    });
    lines.push('');
    lines.push('─── 第2部：リライト指示書 ───');
    lines.push('');
    lines.push(report.part2_instructions);

    return lines.join('\n');
}

/* ── トースト通知 ────────────────────────────── */
function showToast(message) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.style.cssText = `
            position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
            background: #1e293b; color: white; padding: 12px 28px;
            border-radius: 8px; font-size: 14px; z-index: 9999;
            opacity: 0; transition: opacity 0.3s; pointer-events: none;
        `;
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.style.opacity = '1';
    setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}

/* ── エラー表示 ──────────────────────────────── */
function showError(message) {
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'block';
    document.getElementById('errorMessage').textContent = message;
}

/* ── リセット ────────────────────────────────── */
function resetForm() {
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('inputSection').style.display = 'block';
    document.getElementById('comparisonBar').style.display = 'none';
    currentReport = null;
    window.scrollTo(0, 0);
}

/* ── Enter キーで診断開始 ────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('urlInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') startDiagnosis();
    });
    document.getElementById('keywordInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') startDiagnosis();
    });

    // LLM状態を取得して表示
    fetch('/api/status')
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const badge = document.getElementById('llmStatusBadge');
                if (data.llm_available) {
                    badge.innerHTML = `🤖 LLM連携あり: ${data.llm_provider} (${data.llm_model})`;
                    badge.className = 'llm-status-badge available';
                    const hint = document.getElementById('llmHint');
                    if (hint) hint.textContent = '✓ LLM APIキーが設定されています。LLM診断が可能です。';
                } else {
                    badge.innerHTML = '⚙️ ルールベースモード（LLM APIキー未設定）';
                    badge.className = 'llm-status-badge unavailable';
                }
                badge.style.display = 'inline-block';
            }
        })
        .catch(() => {});
});
