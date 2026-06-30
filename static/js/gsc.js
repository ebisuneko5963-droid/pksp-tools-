/* ════════════════════════════════════════════════
   GSC 定期分析テンプレート — フロントエンド
   ════════════════════════════════════════════════ */

let currentReport = null;
let currentReportId = null;
let currentMarkdown = "";

function updateFileList(input, listId) {
    const list = document.getElementById(listId);
    list.innerHTML = '';
    for (const file of input.files) {
        const chip = document.createElement('span');
        chip.className = 'file-chip';
        chip.textContent = file.name;
        list.appendChild(chip);
    }
}

function startAnalysis() {
    const f7 = document.getElementById('period_7d_files').files;
    const f28 = document.getElementById('period_28d_files').files;
    const f3m = document.getElementById('period_3m_files').files;

    if (f7.length === 0 && f28.length === 0 && f3m.length === 0) {
        alert('少なくとも1つの期間のCSVをアップロードしてください。');
        return;
    }

    const formData = new FormData();
    for (const f of f7) formData.append('period_7d_files', f);
    for (const f of f28) formData.append('period_28d_files', f);
    for (const f of f3m) formData.append('period_3m_files', f);

    document.getElementById('inputSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('loadingSection').style.display = 'block';

    animateSteps();

    fetch('/api/gsc/analyze', {
        method: 'POST',
        body: formData,
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
        } else if (data.success) {
            currentReport = data.report;
            currentReportId = data.report_id;
            currentMarkdown = data.markdown;
            displayResults(data.report, data.markdown);
        }
    })
    .catch(err => {
        showError('通信エラー: ' + err.message);
    });
}

function animateSteps() {
    const steps = document.querySelectorAll('.step');
    steps.forEach(s => s.classList.remove('active', 'done'));
    let i = 0;
    const iv = setInterval(() => {
        if (i > 0) steps[i - 1].classList.add('done');
        if (i < steps.length) { steps[i].classList.add('active'); i++; }
        else clearInterval(iv);
    }, 800);
}

function displayResults(report, markdown) {
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('resultSection').style.display = 'block';

    displaySummary(report.summary);
    displayGoodChanges(report.good_changes);
    displayBadChanges(report.bad_changes);
    displayHypotheses(report.hypotheses);
    displayRecommendations(report.recommendations);
    document.getElementById('markdownPreview').textContent = markdown;
}

function displaySummary(summary) {
    const c = document.getElementById('summaryTable');
    const p7 = summary.p7 || {};
    const p28 = summary.p28 || {};
    const p3m = summary.p3m || {};
    const d = summary.diff_7d_vs_28d || {};

    let diffHTML = '';
    if (d.clicks_ratio !== null && d.clicks_ratio !== undefined) {
        const ratio = d.clicks_ratio;
        const cls = ratio >= 100 ? 'diff-up' : 'diff-down';
        diffHTML += `<div style="margin-top:14px;font-size:14px;">
            <strong>7日 vs 28日（日次平均）:</strong>
            クリック <span class="${cls}">${ratio.toFixed(0)}%</span>,
            表示 <span class="${d.imp_ratio >= 100 ? 'diff-up' : 'diff-down'}">${(d.imp_ratio || 0).toFixed(0)}%</span>,
            順位 <span class="${d.position_diff <= 0 ? 'diff-up' : 'diff-down'}">${d.position_diff > 0 ? '+' : ''}${d.position_diff}位</span>,
            CTR <span class="${d.ctr_diff >= 0 ? 'diff-up' : 'diff-down'}">${d.ctr_diff > 0 ? '+' : ''}${d.ctr_diff}pt</span>
        </div>`;
    }

    c.innerHTML = `
        <table class="summary-table">
            <thead>
                <tr><th>指標</th><th>直近7日</th><th>直近28日</th><th>直近3か月</th></tr>
            </thead>
            <tbody>
                <tr><td>総クリック数</td><td>${p7.total_clicks || 0}</td><td>${p28.total_clicks || 0}</td><td>${p3m.total_clicks || 0}</td></tr>
                <tr><td>総表示回数</td><td>${(p7.total_impressions || 0).toLocaleString()}</td><td>${(p28.total_impressions || 0).toLocaleString()}</td><td>${(p3m.total_impressions || 0).toLocaleString()}</td></tr>
                <tr><td>平均CTR</td><td>${p7.avg_ctr || 0}%</td><td>${p28.avg_ctr || 0}%</td><td>${p3m.avg_ctr || 0}%</td></tr>
                <tr><td>平均掲載順位</td><td>${p7.avg_position || 0}位</td><td>${p28.avg_position || 0}位</td><td>${p3m.avg_position || 0}位</td></tr>
                <tr><td>日次平均クリック</td><td>${p7.daily_avg_clicks || 0}</td><td>${p28.daily_avg_clicks || 0}</td><td>${p3m.daily_avg_clicks || 0}</td></tr>
                <tr><td>日次平均表示</td><td>${(p7.daily_avg_impressions || 0).toFixed(0)}</td><td>${(p28.daily_avg_impressions || 0).toFixed(0)}</td><td>${(p3m.daily_avg_impressions || 0).toFixed(0)}</td></tr>
            </tbody>
        </table>
        ${diffHTML}
    `;
}

function displayGoodChanges(changes) {
    const c = document.getElementById('goodChangesList');
    if (!changes || changes.length === 0) {
        c.innerHTML = '<p style="color:var(--text-light);padding:10px;">目立った良い変化なし</p>';
        return;
    }
    c.innerHTML = changes.map(g => `
        <div class="change-item good">
            <div class="change-title">
                <span class="change-category">${g.category}</span>
                ${g.title}
            </div>
            ${g.detail ? `<div class="change-detail">${g.detail}</div>` : ''}
        </div>
    `).join('');
}

function displayBadChanges(changes) {
    const c = document.getElementById('badChangesList');
    if (!changes || changes.length === 0) {
        c.innerHTML = '<p style="color:var(--good);padding:10px;">✓ 目立った悪い変化なし</p>';
        return;
    }
    c.innerHTML = changes.map(b => {
        const sev = b.severity || 'mid';
        const icon = {high: '🔴', mid: '🟡', low: '🟢'}[sev];
        return `
        <div class="change-item bad-${sev}">
            <div class="change-title">
                <span class="change-category">${b.category}</span>
                ${icon} ${b.title}
            </div>
            ${b.detail ? `<div class="change-detail">${b.detail}</div>` : ''}
        </div>`;
    }).join('');
}

function displayHypotheses(hypos) {
    const c = document.getElementById('hypothesesList');
    if (!hypos || hypos.length === 0) {
        c.innerHTML = '<p style="color:var(--text-light);padding:10px;">仮説生成対象なし</p>';
        return;
    }
    c.innerHTML = hypos.map((h, i) => `
        <div class="hypothesis-item">
            <div class="hypothesis-title">仮説${i + 1}: ${h.hypothesis}</div>
            <div class="hypothesis-badges">
                <span class="badge badge-conf-${h.confidence}">確度: ${h.confidence}</span>
                <span class="badge badge-sev-${h.severity || 'mid'}">重要度: ${h.severity || 'mid'}</span>
            </div>
            <div class="hypothesis-section">
                <strong>根拠:</strong>
                <ul class="hypothesis-evidence">
                    ${(h.evidence || []).map(e => `<li>${e}</li>`).join('')}
                </ul>
            </div>
            <div class="hypothesis-action">
                <strong>👉 次のアクション:</strong> ${h.suggested_action || ''}
            </div>
        </div>
    `).join('');
}

function displayRecommendations(recs) {
    const c = document.getElementById('recommendationsList');
    if (!recs || recs.length === 0) {
        c.innerHTML = '<p style="color:var(--text-light);padding:10px;">リライト推奨記事なし</p>';
        return;
    }
    c.innerHTML = recs.map(r => {
        const cs = r.current_state;
        const impact = r.estimated_impact;
        const queriesHTML = (r.related_queries && r.related_queries.length > 0)
            ? `<div class="rec-section">
                  <strong>主要流入クエリ（推定）:</strong>
                  <ul>${r.related_queries.map(q => `<li>${q.query} <span style="color:var(--text-light);">(表示${q.impressions} / 順位${q.position})</span></li>`).join('')}</ul>
               </div>`
            : '';

        return `
        <div class="rec-item">
            <div class="rec-header">
                <div class="rec-rank">${r.rank}</div>
                <div style="flex:1;">
                    <div class="rec-url"><a href="${r.url}" target="_blank">${r.url}</a></div>
                    <div class="rec-category">${r.category}</div>
                </div>
            </div>
            <div class="rec-stats">
                <div class="rec-stat"><span class="stat-label">表示数</span><span class="stat-value">${cs.impressions.toLocaleString()}</span></div>
                <div class="rec-stat"><span class="stat-label">クリック</span><span class="stat-value">${cs.clicks}</span></div>
                <div class="rec-stat"><span class="stat-label">CTR</span><span class="stat-value">${cs.ctr}%</span></div>
                <div class="rec-stat"><span class="stat-label">順位</span><span class="stat-value">${cs.position}</span></div>
                <div class="rec-stat"><span class="stat-label">機会損失</span><span class="stat-value">約${(r.missed_clicks || 0).toFixed(1)}クリック</span></div>
            </div>
            <div class="rec-section"><strong>推奨理由:</strong> ${r.reason}</div>
            ${queriesHTML}
            <div class="rec-section">
                <strong>リライトの焦点:</strong>
                <ul>${(r.rewrite_focus || []).map(f => `<li>${f}</li>`).join('')}</ul>
            </div>
            <div class="rec-section">
                <strong>pksp.jp 独自の打ち手（八木氏視点）:</strong>
                <ul>${(r.pksp_unique_angle || []).map(a => `<li>${a}</li>`).join('')}</ul>
            </div>
            <div class="rec-impact">
                <strong>推定インパクト:</strong> ${impact.scenario}<br>
                現在 ${impact.current_clicks}クリック → 改善後 ${impact.potential_clicks_per_period}クリック (+${impact.uplift})
            </div>
            <div class="rec-next">
                👉 ${r.next_step}
            </div>
        </div>`;
    }).join('');
}

function toggleMarkdown() {
    const el = document.getElementById('markdownPreview');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function copyMarkdown() {
    navigator.clipboard.writeText(currentMarkdown).then(() => {
        showToast('Markdownレポートをコピーしました');
    });
}

function downloadReport(fmt) {
    if (!currentReportId) return;
    window.location.href = `/api/report/${currentReportId}/download/${fmt}`;
}

function showToast(message) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.style.cssText = 'position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#1e293b;color:white;padding:12px 28px;border-radius:8px;font-size:14px;z-index:9999;opacity:0;transition:opacity 0.3s;';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.style.opacity = '1';
    setTimeout(() => toast.style.opacity = '0', 2500);
}

function showError(msg) {
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'block';
    document.getElementById('errorMessage').textContent = msg;
}

function resetForm() {
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    document.getElementById('inputSection').style.display = 'block';
    window.scrollTo(0, 0);
}
