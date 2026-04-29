document.addEventListener('DOMContentLoaded', async () => {
    if (!checkAuth()) return;

    const params = new URLSearchParams(window.location.search);
    const enrollmentId = params.get('enrollment') || localStorage.getItem('current_enrollment');

    if (!enrollmentId) {
        window.location.href = '/dashboard.html';
        return;
    }

    await loadProgressData(enrollmentId);
});

async function loadProgressData(enrollmentId) {
    try {
        showLoading('Loading analytics...');

        const [summary, mastery] = await Promise.all([
            api.getProgressSummary(enrollmentId).catch(() => null),
            api.getTopicMastery(enrollmentId).catch(() => []),
        ]);

        hideLoading();

        if (summary) renderSummary(summary);
        renderMasteryChart(mastery);
        renderMasteryTable(mastery);
    } catch (error) {
        hideLoading();
        showToast(error.message, 'error');
    }
}

function renderSummary(s) {
    const container = document.getElementById('summary-stats');
    if (!container) return;

    container.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-icon primary">&#128200;</div><div><div class="stat-value">${Math.round(s.overall_mastery)}%</div><div class="stat-label">Overall Mastery</div></div></div>
            <div class="stat-card"><div class="stat-icon success">&#9989;</div><div><div class="stat-value">${s.mastered_topics}</div><div class="stat-label">Mastered</div></div></div>
            <div class="stat-card"><div class="stat-icon warning">&#9203;</div><div><div class="stat-value">${s.days_remaining !== null ? s.days_remaining : '--'}</div><div class="stat-label">Days Left</div></div></div>
            <div class="stat-card"><div class="stat-icon info">&#128640;</div><div><div class="stat-value">${Math.round(s.velocity_score)}</div><div class="stat-label">Velocity</div></div></div>
            <div class="stat-card"><div class="stat-icon danger">&#128293;</div><div><div class="stat-value">${s.study_streak}</div><div class="stat-label">Streak</div></div></div>
            <div class="stat-card"><div class="stat-icon primary">&#128203;</div><div><div class="stat-value">${Math.round(s.schedule_completion_pct)}%</div><div class="stat-label">Schedule Done</div></div></div>
        </div>`;
}

function renderMasteryChart(topics) {
    const container = document.getElementById('mastery-chart');
    if (!container || !topics.length) return;

    let html = '<div style="display: flex; flex-direction: column; gap: var(--space-3);">';
    for (const t of topics) {
        const pct = Math.round(t.mastery_level);
        const color = pct >= 80 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)';
        html += `
            <div>
                <div class="flex justify-between text-sm mb-4">
                    <span>${t.topic_name}</span>
                    <span style="color: ${color}; font-weight: 600;">${pct}%</span>
                </div>
                <div class="progress-bar" style="height: 10px;">
                    <div style="height: 100%; width: ${pct}%; background: ${color}; border-radius: var(--radius-full); transition: width 0.5s;"></div>
                </div>
            </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
}

function renderMasteryTable(topics) {
    const container = document.getElementById('mastery-details');
    if (!container) return;

    let html = '<div class="table-container"><table><thead><tr><th>Topic</th><th>Weight</th><th>Mastery</th><th>Attempts</th><th>Last Score</th><th>Next Review</th></tr></thead><tbody>';
    for (const t of topics) {
        html += `<tr>
            <td>${t.topic_name}</td>
            <td><span class="badge badge-${t.weight === 'high' ? 'danger' : t.weight === 'medium' ? 'warning' : 'info'}">${t.weight}</span></td>
            <td>${Math.round(t.mastery_level)}%</td>
            <td>${t.attempts}</td>
            <td>${t.last_score !== null ? Math.round(t.last_score) + '%' : '-'}</td>
            <td>${t.next_review || '-'}</td>
        </tr>`;
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}
