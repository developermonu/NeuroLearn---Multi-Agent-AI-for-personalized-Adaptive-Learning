/* ===================================================================
   study.js — Sequential topic unlock study flow with rich reading,
   quiz progress, and revision support.
   Topics unlock one-by-one:  Generate → Read → Quiz → Next
   =================================================================== */

/** Sanitize HTML to prevent XSS from LLM-generated content */
function sanitizeText(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

let currentEnrollment = null;
let currentPath = null;
let topicsData = [];

document.addEventListener('DOMContentLoaded', async () => {
    if (!checkAuth()) return;
    const params = new URLSearchParams(window.location.search);
    currentEnrollment = params.get('enrollment') || localStorage.getItem('current_enrollment');
    
    if (!currentEnrollment || currentEnrollment === 'null') {
        try {
            const enrollments = await api.getMyEnrollments();
            const active = enrollments.find(e => e.status === 'active');
            if (active) {
                currentEnrollment = active.id;
                localStorage.setItem('current_enrollment', currentEnrollment);
                // Update URL without refreshing to keep it clean
                const newUrl = new URL(window.location);
                newUrl.searchParams.set('enrollment', currentEnrollment);
                window.history.replaceState({}, '', newUrl);
            } else {
                window.location.href = '/dashboard.html';
                return;
            }
        } catch (e) {
            window.location.href = '/dashboard.html';
            return;
        }
    }
    
    localStorage.setItem('current_enrollment', currentEnrollment);
    await loadStudyDashboard();
});

// ───────────────────────── Main loader ─────────────────────────
async function loadStudyDashboard() {
    try {
        showLoading('Loading study plan…');
        const progress = await api.getProgressSummary(currentEnrollment).catch(() => null);
        if (progress) renderProgressStats(progress);

        const path = await api.getPath(currentEnrollment).catch(() => null);
        if (path) { currentPath = path; renderPathInfo(path); }

        const todayTasks = await api.getTodayTasks(currentEnrollment).catch(() => []);
        renderTodayTasks(todayTasks);

        topicsData = await api.getTopicsStatus(currentEnrollment).catch(() => []);
        renderTopicsList(topicsData);

        hideLoading();
    } catch (error) {
        hideLoading();
        showToast(`Error: ${error.message}`, 'error');
    }
}

// ───────────────────────── Progress stats ─────────────────────────
function renderProgressStats(p) {
    const c = document.getElementById('progress-stats');
    if (!c) return;

    // Calculate reading progress from topics data
    const readCount = topicsData.filter(t => t.content_read).length;
    const genCount = topicsData.filter(t => t.content_generated).length;
    const totalT = topicsData.length || p.total_topics || 1;
    const readPct = Math.round((readCount / totalT) * 100);

    c.innerHTML = `
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-icon primary">&#128202;</div><div><div class="stat-value">${Math.round(p.overall_mastery)}%</div><div class="stat-label">Overall Mastery</div></div></div>
        <div class="stat-card"><div class="stat-icon success">&#9989;</div><div><div class="stat-value">${p.mastered_topics}/${p.total_topics}</div><div class="stat-label">Topics Mastered</div></div></div>
        <div class="stat-card"><div class="stat-icon warning">&#128336;</div><div><div class="stat-value">${p.days_remaining ?? '--'}</div><div class="stat-label">Days Remaining</div></div></div>
        <div class="stat-card"><div class="stat-icon info">&#128293;</div><div><div class="stat-value">${p.study_streak}</div><div class="stat-label">Day Streak</div></div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-top:var(--space-4);">
        <div style="padding:var(--space-4);background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-lg);display:flex;align-items:center;gap:var(--space-4);">
            <div style="position:relative;width:56px;height:56px;">
                <svg viewBox="0 0 36 36" style="transform:rotate(-90deg);width:56px;height:56px;">
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--bg-input)" stroke-width="3"/>
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--accent-primary)" stroke-width="3" stroke-dasharray="${readPct}, 100" stroke-linecap="round"/>
                </svg>
                <span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;">${readPct}%</span>
            </div>
            <div>
                <div style="font-weight:700;font-size:var(--text-lg);">${readCount}/${totalT}</div>
                <div style="font-size:var(--text-xs);color:var(--text-tertiary);">Chapters Read</div>
            </div>
        </div>
        <div style="padding:var(--space-4);background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-lg);display:flex;align-items:center;gap:var(--space-4);">
            <div style="position:relative;width:56px;height:56px;">
                <svg viewBox="0 0 36 36" style="transform:rotate(-90deg);width:56px;height:56px;">
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--bg-input)" stroke-width="3"/>
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--success)" stroke-width="3" stroke-dasharray="${Math.round((genCount/totalT)*100)}, 100" stroke-linecap="round"/>
                </svg>
                <span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;">${Math.round((genCount/totalT)*100)}%</span>
            </div>
            <div>
                <div style="font-weight:700;font-size:var(--text-lg);">${genCount}/${totalT}</div>
                <div style="font-size:var(--text-xs);color:var(--text-tertiary);">Content Generated</div>
            </div>
        </div>
    </div>`;
}

// ───────────────────────── Path info ─────────────────────────
function renderPathInfo(path) {
    const c = document.getElementById('path-info');
    if (!c) return;
    c.classList.remove('hidden');
    c.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-3);">
        <div>
            <div class="text-sm text-muted">Study Days: ${path.study_days} | Buffer: ${path.buffer_days}</div>
            <div class="text-sm text-muted">Daily: ${path.daily_load_minutes} min</div>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="viewSchedule()">View Schedule</button>
    </div>
    <div class="progress-bar" style="height:10px;"><div class="progress-fill" style="width:${Math.min(100,path.velocity_score)}%"></div></div>
    <div class="text-sm text-muted" style="margin-top:6px;">Velocity: ${path.velocity_score}%</div>`;
}

// ───────────────────────── Today's tasks ─────────────────────────
function renderTodayTasks(tasks) {
    const c = document.getElementById('today-tasks');
    if (!c) return;
    if (!tasks.length) { c.innerHTML = '<div class="text-center text-muted" style="padding:var(--space-6);">No tasks for today. Build your learning path to start!</div>'; return; }
    const icons = { study:'&#128214;', quiz:'&#10067;', review:'&#128260;', mock:'&#128221;', remedial:'&#127891;', spaced_rep:'&#128257;' };
    c.innerHTML = tasks.map(t => {
        const done = t.status==='completed';
        return `<div class="task-item ${done?'completed':''}" style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--bg-card);border-radius:var(--radius-md);margin-bottom:8px;">
            <span style="font-size:1.3rem;">${icons[t.item_type]||'&#128196;'}</span>
            <div style="flex:1;">
                <div style="font-weight:600;${done?'text-decoration:line-through;opacity:.5':''}">${t.title}</div>
                <div class="text-sm text-muted">${t.estimated_minutes} min${t.topic_name?' · '+t.topic_name:''}</div>
            </div>
            ${done ? '<span class="badge badge-success">Done</span>' :
              (t.item_type==='quiz'||t.item_type==='mock')
                ? `<button class="btn btn-primary btn-sm" onclick="startTaskQuiz('${t.id}','${t.topic_name||''}','${t.topic_id||''}')">Start</button>`
                : `<button class="btn btn-secondary btn-sm" onclick="completeTask('${t.id}')">Done</button>`}
        </div>`;
    }).join('');
}

// ═══════════════════════════════════════════════════════════════
//  TOPIC LIST WITH SEQUENTIAL LOCKS + RE-READ SUPPORT
// ═══════════════════════════════════════════════════════════════
function renderTopicsList(topics) {
    const c = document.getElementById('topics-list');
    if (!c) return;
    if (!topics.length) { c.innerHTML = '<div class="text-muted text-center" style="padding:var(--space-8);">Enroll and build your learning path first.</div>'; return; }

    c.innerHTML = topics.map((t, i) => {
        const locked = !t.topic_unlocked;
        const hasContent = t.content_generated;
        const isRead = t.content_read;
        const quizOpen = t.quiz_unlocked;
        const quizDone = t.quiz_passed;

        // ── Status badge ──
        let badge = '';
        if (locked && !hasContent) badge = mkBadge('🔒 Locked', 'var(--bg-input)', 'var(--text-tertiary)');
        else if (locked && hasContent) badge = mkBadge('🔒 Locked', 'var(--bg-input)', 'var(--text-tertiary)');
        else if (quizDone) badge = mkBadge('✅ Complete', null, null, 'badge-success');
        else if (quizOpen) badge = mkBadge('📝 Quiz Ready', null, null, 'badge-warning');
        else if (isRead) badge = mkBadge('✅ Read', null, null, 'badge-info');
        else if (hasContent) badge = mkBadge('📖 Ready to Read', 'rgba(99,102,241,.15)', '#818cf8');
        else badge = mkBadge('⚡ Generate', 'rgba(168,85,247,.15)', '#c084fc');

        // ── Action buttons ──
        let actions = '';
        if (locked) {
            // Even locked topics can have a "Read" button if content exists (revision)
            if (hasContent && isRead) {
                actions = `<button class="btn btn-ghost btn-sm" onclick="readTopic('${t.topic_id}','${esc(t.topic_name)}',true)">📖 Revise</button>
                           <span class="text-sm text-muted" style="white-space:nowrap;">🔒 Quiz locked</span>`;
            } else {
                actions = '<span class="text-sm text-muted">Complete previous topic first</span>';
            }
        } else if (!hasContent) {
            actions = `<button class="btn btn-primary btn-sm" id="gen-btn-${t.topic_id}" onclick="generateSingleTopic('${t.topic_id}','${esc(t.topic_name)}')">⚡ Generate</button>`;
        } else if (!isRead) {
            actions = `<button class="btn btn-secondary btn-sm" onclick="readTopic('${t.topic_id}','${esc(t.topic_name)}',false)">📖 Read</button>`;
        } else if (!quizDone) {
            // BOTH read again AND take quiz available
            actions = `<button class="btn btn-ghost btn-sm" onclick="readTopic('${t.topic_id}','${esc(t.topic_name)}',true)">📖 Revise</button>
                       <button class="btn btn-primary btn-sm" ${quizOpen?'':'disabled title="Read the chapter first"'} onclick="startTopicQuiz('${t.topic_id}','${esc(t.topic_name)}')">📝 Quiz</button>`;
        } else {
            // Complete: read again & retake quiz
            actions = `<button class="btn btn-ghost btn-sm" onclick="readTopic('${t.topic_id}','${esc(t.topic_name)}',true)">📖 Revise</button>
                       <button class="btn btn-ghost btn-sm" onclick="startTopicQuiz('${t.topic_id}','${esc(t.topic_name)}')">📝 Retake</button>`;
        }

        // ── Weight badge ──
        const wc = t.weight==='high'?'danger':t.weight==='medium'?'warning':'info';

        // ── Mastery bar ──
        const mastery = Math.round(t.mastery_level);
        const mc = mastery >= 80 ? 'var(--success)' : mastery >= 40 ? 'var(--warning)' : 'var(--danger)';

        // ── Left border color ──
        const borderColor = quizDone ? 'var(--success)' : hasContent ? 'var(--accent-primary)' : 'var(--border-color)';

        // ── Subtopics ──
        let subtopicsHtml = '';
        if (hasContent && t.subtopics && t.subtopics.length > 0) {
            subtopicsHtml = `<div style="margin-top:8px;padding-left:12px;border-left:2px solid var(--border-color);display:flex;flex-direction:column;gap:4px;">
                ${t.subtopics.map(st => `<div style="font-size:var(--text-xs);color:var(--text-tertiary);display:flex;align-items:center;gap:4px;"><span style="color:var(--accent-primary);font-size:8px;">▶</span> ${st}</div>`).join('')}
            </div>`;
        }

        return `
        <div class="topic-row" style="display:flex;align-items:flex-start;gap:12px;padding:14px 18px;background:${locked?'var(--bg-input)':'var(--bg-card)'};border-radius:var(--radius-lg);margin-bottom:8px;opacity:${locked && !hasContent?'0.45':'1'};border-left:3px solid ${borderColor};transition:all .2s ease;">
            <div style="min-width:32px;text-align:center;font-weight:700;font-size:var(--text-sm);color:var(--text-tertiary);margin-top:2px;">${i+1}</div>
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;margin-bottom:2px;">${t.topic_name}</div>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                    <span class="text-sm text-muted">${t.section_name}</span>
                    <span class="badge badge-${wc}" style="font-size:10px;">${t.weight}</span>
                    ${badge}
                </div>
                ${subtopicsHtml}
                ${mastery > 0 ? `<div style="display:flex;align-items:center;gap:6px;margin-top:8px;">
                    <div style="width:80px;height:4px;background:var(--bg-input);border-radius:99px;overflow:hidden;">
                        <div style="height:100%;width:${mastery}%;background:${mc};border-radius:99px;"></div>
                    </div>
                    <span class="text-sm" style="color:${mc};">${mastery}%</span>
                </div>` : ''}
            </div>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;">${actions}</div>
        </div>`;
    }).join('');
}

function mkBadge(text, bg, fg, cls) {
    if (cls) return `<span class="badge ${cls}">${text}</span>`;
    return `<span class="badge" style="background:${bg};color:${fg};">${text}</span>`;
}
function esc(s) { return (s||'').replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

// ═══════════════════════════════════════════════════════════════
//  GENERATE SINGLE TOPIC
// ═══════════════════════════════════════════════════════════════
async function generateSingleTopic(topicId, topicName) {
    const btn = document.getElementById(`gen-btn-${topicId}`);
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:12px;height:12px;border-width:2px;"></span> Generating…'; }
    try {
        const result = await api.generateTopicContent(currentEnrollment, topicId);
        showToast(`Generated: ${result.title}`, 'success');
        await loadStudyDashboard();
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '⚡ Generate'; }
    }
}

// ═══════════════════════════════════════════════════════════════
//  READ / REVISE TOPIC — RICH FORMATTED READER
// ═══════════════════════════════════════════════════════════════
async function readTopic(topicId, topicName, isRevision) {
    try {
        const contentArr = await api.getTopicContent(currentEnrollment, topicId);
        if (!contentArr.length) { showToast('No content found. Generate it first.', 'error'); return; }

        const content = contentArr[0];
        const alreadyRead = topicsData.find(t => t.topic_id === topicId)?.content_read;

        // Footer buttons: show "Mark Read" only if not yet marked
        let footerBtns = '';
        if (!alreadyRead && !isRevision) {
            footerBtns = `<button class="btn btn-primary" id="mark-read-btn" onclick="markAsRead('${topicId}')">
                ✅ Mark as Read &amp; Unlock Quiz
            </button>`;
        } else {
            footerBtns = `<span class="badge badge-success" style="padding:8px 16px;">Already read ✅</span>`;
        }

        // Build overlay
        const overlay = document.createElement('div');
        overlay.id = 'read-overlay';
        overlay.innerHTML = `
        <div class="reader-backdrop" onclick="if(event.target===this) document.getElementById('read-overlay').remove();">
            <div class="reader-container">
                <div class="reader-header">
                    <div>
                        <h2 class="reader-title">${sanitizeText(content.title)}</h2>
                        <div class="reader-meta">
                            <span class="reader-tag">${sanitizeText(content.difficulty)}</span>
                            <span class="reader-tag">${sanitizeText(content.learning_style)} learner</span>
                            <span class="reader-tag">${estimateReadTime(content.content)} min read</span>
                        </div>
                    </div>
                    <button class="reader-close" onclick="document.getElementById('read-overlay').remove()">&times;</button>
                </div>
                <div class="reader-body">${formatContent(content.content)}</div>
                <div class="reader-footer">
                    ${footerBtns}
                    <button class="btn btn-ghost" onclick="document.getElementById('read-overlay').remove()">Close</button>
                </div>
            </div>
        </div>`;

        // Inject reader styles if not already present
        if (!document.getElementById('reader-styles')) injectReaderStyles();

        document.body.appendChild(overlay);
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

function estimateReadTime(text) {
    if (!text) return 1;
    return Math.max(1, Math.ceil((text.split(/\s+/).length) / 200));
}

// ── Pre-process raw LLM content ──
function cleanRawContent(text) {
    if (!text) return '';
    let cleaned = text.trim();

    // Strip ```json ... ``` wrappers (greedy)
    cleaned = cleaned.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?```\s*$/i, '');
    cleaned = cleaned.trim();

    // Strategy 1: Try full JSON parse
    try {
        const parsed = JSON.parse(cleaned);
        if (parsed && typeof parsed === 'object' && parsed.content) {
            let parts = [];
            parts.push(parsed.content);
            if (parsed.key_points && Array.isArray(parsed.key_points) && parsed.key_points.length) {
                parts.push('\n\n## Key Points\n' + parsed.key_points.map(p => `- ${p}`).join('\n'));
            }
            if (parsed.examples && Array.isArray(parsed.examples) && parsed.examples.length) {
                parts.push('\n\n## Examples\n' + parsed.examples.map(e => `- ${e}`).join('\n'));
            }
            if (parsed.summary) parts.push('\n\n## Summary\n' + parsed.summary);
            return parts.join('').replace(/\\n/g, '\n').trim();
        }
    } catch (e) { /* not valid JSON */ }

    // Strategy 2: Regex-extract "content" field from partial/broken JSON
    const contentMatch = cleaned.match(/"content"\s*:\s*"([\s\S]*?)(?:"\s*[,}]|"$)/);
    if (contentMatch) {
        let extracted = contentMatch[1];
        // Also try to extract key_points
        const kpMatch = cleaned.match(/"key_points"\s*:\s*\[([\s\S]*?)\]/);
        if (kpMatch) {
            try {
                const kps = JSON.parse('[' + kpMatch[1] + ']');
                extracted += '\n\n## Key Points\n' + kps.map(k => `- ${k}`).join('\n');
            } catch(e) {}
        }
        const sumMatch = cleaned.match(/"summary"\s*:\s*"([\s\S]*?)(?:"\s*[,}]|"$)/);
        if (sumMatch) extracted += '\n\n## Summary\n' + sumMatch[1];

        cleaned = extracted;
    }

    // Strategy 3: Strip any leading JSON artifact { "title": "...", "content": "
    cleaned = cleaned.replace(/^\s*\{\s*"title"\s*:\s*"[^"]*"\s*,\s*"content"\s*:\s*"/i, '');

    // Convert literal \n to real newlines
    cleaned = cleaned.replace(/\\n/g, '\n');
    // Clean up trailing JSON artifacts
    cleaned = cleaned.replace(/"\s*,\s*"key_points"\s*:.*$/s, '');
    cleaned = cleaned.replace(/"\s*\}\s*$/, '');

    return cleaned.trim();
}

// ── Rich content formatter ──
function formatContent(text) {
    let raw = cleanRawContent(text);
    if (!raw) return '<p style="color:var(--text-tertiary);text-align:center;">No content available.</p>';

    let html = raw;

    // Escape HTML entities
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Code blocks ```...```
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
        return `<div class="rc-code"><div class="rc-code-header">${lang || 'code'}</div><pre><code>${code.trim()}</code></pre></div>`;
    });

    // Inline code `...`
    html = html.replace(/`([^`]+)`/g, '<code class="rc-inline-code">$1</code>');

    // Headers (### before ## before #)
    html = html.replace(/^### (.+)$/gm, '<h4 class="rc-h4">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 class="rc-h3">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 class="rc-h2">$1</h2>');

    // Bold + italic combos
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="rc-bold">$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em class="rc-italic">$1</em>');

    // Numbered lists
    html = html.replace(/^(\d+)\.\s+(.+)$/gm, '<div class="rc-ol-item"><span class="rc-ol-num">$1</span><span>$2</span></div>');

    // Bullet lists
    html = html.replace(/^- (.+)$/gm, '<div class="rc-li">$1</div>');

    // Horizontal rules
    html = html.replace(/^---$/gm, '<hr class="rc-hr">');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p class="rc-p">');
    html = html.replace(/\n/g, '<br>');

    // Wrap in paragraph
    html = '<p class="rc-p">' + html + '</p>';

    // Clean up empty/broken paragraphs
    html = html.replace(/<p class="rc-p"><\/p>/g, '');
    html = html.replace(/<p class="rc-p">(<h[2-4])/g, '$1');
    html = html.replace(/(<\/h[2-4]>)<\/p>/g, '$1');
    html = html.replace(/<p class="rc-p">(<div class="rc-)/g, '$1');
    html = html.replace(/(<\/div>)<\/p>/g, '$1');
    html = html.replace(/<p class="rc-p">(<hr)/g, '$1');

    return html;
}

// ── Inject premium reader CSS ──
function injectReaderStyles() {
    const style = document.createElement('style');
    style.id = 'reader-styles';
    style.textContent = `
    .reader-backdrop {
        position:fixed; inset:0; background:rgba(8,10,16,.92); z-index:200;
        overflow-y:auto; padding:32px 16px; backdrop-filter:blur(8px);
        animation: fadeInReader .25s ease;
    }
    @keyframes fadeInReader { from { opacity:0; } to { opacity:1; } }

    .reader-container {
        max-width:820px; margin:0 auto;
        background: linear-gradient(145deg, rgba(30,33,48,1), rgba(22,24,36,1));
        border:1px solid rgba(99,102,241,.2);
        border-radius:20px; overflow:hidden;
        box-shadow: 0 25px 80px rgba(0,0,0,.5), 0 0 40px rgba(99,102,241,.06);
        animation: slideUpReader .3s ease;
    }
    @keyframes slideUpReader { from { transform:translateY(32px);opacity:.6; } to { transform:translateY(0);opacity:1; } }

    .reader-header {
        display:flex; justify-content:space-between; align-items:flex-start;
        padding:32px 36px 20px; border-bottom:1px solid rgba(255,255,255,.06);
        background:linear-gradient(180deg, rgba(99,102,241,.08) 0%, transparent 100%);
    }
    .reader-title { font-size:1.5rem; font-weight:700; color:var(--text-primary); margin:0 0 8px; line-height:1.3; }
    .reader-meta { display:flex; gap:8px; flex-wrap:wrap; }
    .reader-tag {
        padding:3px 10px; border-radius:99px; font-size:11px; font-weight:600; letter-spacing:.3px;
        background:rgba(99,102,241,.12); color:#a5b4fc; text-transform:uppercase;
    }
    .reader-close {
        background:none; border:none; color:var(--text-tertiary); font-size:1.8rem;
        cursor:pointer; padding:4px 8px; border-radius:8px; line-height:1;
        transition:all .15s;
    }
    .reader-close:hover { background:rgba(255,255,255,.08); color:var(--text-primary); }

    .reader-body {
        padding:28px 36px 36px; line-height:1.85; color:rgba(209,213,225,.9);
        font-size:15.5px; font-family:'Inter',sans-serif;
    }

    .reader-footer {
        display:flex; justify-content:center; gap:12px; padding:20px 36px 28px;
        border-top:1px solid rgba(255,255,255,.06);
        background:rgba(15,17,25,.5);
    }

    /* ── Typography ── */
    .rc-h2 { font-size:1.45rem; font-weight:700; color:#f1f5f9; margin:32px 0 14px; padding-bottom:8px; border-bottom:2px solid rgba(99,102,241,.25); }
    .rc-h3 { font-size:1.15rem; font-weight:700; color:#a5b4fc; margin:28px 0 10px; padding-left:12px; border-left:3px solid #6366f1; }
    .rc-h4 { font-size:1rem; font-weight:600; color:#c4b5fd; margin:20px 0 8px; }
    .rc-p { margin:0 0 12px; }
    .rc-bold { color:#e2e8f0; }
    .rc-italic { color:#cbd5e1; font-style:italic; }

    .rc-li {
        padding:6px 0 6px 24px; position:relative; margin:2px 0;
    }
    .rc-li::before {
        content:''; position:absolute; left:8px; top:14px;
        width:6px; height:6px; border-radius:50%; background:#6366f1;
    }
    .rc-ol-item {
        display:flex; gap:10px; padding:6px 0; align-items:flex-start;
    }
    .rc-ol-num {
        min-width:24px; height:24px; display:flex; align-items:center; justify-content:center;
        background:rgba(99,102,241,.15); color:#818cf8; border-radius:50%;
        font-size:12px; font-weight:700; flex-shrink:0;
    }

    .rc-hr { border:none; height:1px; background:linear-gradient(90deg,transparent,rgba(99,102,241,.3),transparent); margin:24px 0; }

    .rc-code {
        margin:16px 0; border-radius:12px; overflow:hidden;
        border:1px solid rgba(99,102,241,.15);
        background:rgba(15,17,25,.7);
    }
    .rc-code-header {
        padding:6px 14px; font-size:11px; font-weight:600; color:#818cf8;
        background:rgba(99,102,241,.08); text-transform:uppercase; letter-spacing:.5px;
    }
    .rc-code pre { margin:0; padding:14px 16px; overflow-x:auto; }
    .rc-code code { font-family:'JetBrains Mono','Fira Code',monospace; font-size:13px; color:#d1d5db; }

    .rc-inline-code {
        background:rgba(99,102,241,.12); color:#c4b5fd; padding:2px 6px;
        border-radius:4px; font-family:'JetBrains Mono',monospace; font-size:13px;
    }

    /* ── Quiz prep overlay ── */
    .quiz-prep-backdrop {
        position:fixed; inset:0; background:rgba(8,10,16,.88); z-index:250;
        display:flex; align-items:center; justify-content:center;
        backdrop-filter:blur(6px); animation:fadeInReader .2s ease;
    }
    .quiz-prep-card {
        background:linear-gradient(145deg,rgba(30,33,48,1),rgba(22,24,36,1));
        border:1px solid rgba(99,102,241,.2); border-radius:20px;
        padding:40px 48px; text-align:center; max-width:420px; width:90%;
        box-shadow:0 20px 60px rgba(0,0,0,.5);
        animation:slideUpReader .3s ease;
    }
    .quiz-prep-icon { font-size:3rem; margin-bottom:16px; }
    .quiz-prep-title { font-size:1.2rem; font-weight:700; margin-bottom:8px; }
    .quiz-prep-steps { text-align:left; margin:20px 0; }
    .quiz-prep-step {
        display:flex; align-items:center; gap:12px; padding:10px 0;
        border-bottom:1px solid rgba(255,255,255,.04);
        color:var(--text-tertiary); transition:all .3s;
    }
    .quiz-prep-step.active { color:var(--text-primary); }
    .quiz-prep-step.done { color:var(--success); }
    .quiz-prep-step-icon { font-size:1.2rem; min-width:28px; text-align:center; }
    .quiz-prep-bar {
        height:8px; background:var(--bg-input); border-radius:99px;
        overflow:hidden; margin-top:20px;
    }
    .quiz-prep-bar-fill {
        height:100%; width:0%; border-radius:99px;
        background:linear-gradient(90deg,#6366f1,#a78bfa);
        transition:width .5s ease;
    }
    `;
    document.head.appendChild(style);
}

async function markAsRead(topicId) {
    const btn = document.getElementById('mark-read-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Marking…'; }
    try {
        await api.markTopicRead(currentEnrollment, topicId);
        document.getElementById('read-overlay')?.remove();
        showToast('Topic marked as read — quiz unlocked!', 'success');
        await loadStudyDashboard();
    } catch (e) {
        showToast(e.message, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '✅ Mark as Read &amp; Unlock Quiz'; }
    }
}

// ═══════════════════════════════════════════════════════════════
//  QUIZ — WITH PREPARATION PROGRESS OVERLAY
// ═══════════════════════════════════════════════════════════════
async function startTopicQuiz(topicId, topicName) {
    if (!document.getElementById('reader-styles')) injectReaderStyles();

    // Show quiz preparation overlay
    const overlay = document.createElement('div');
    overlay.id = 'quiz-prep-overlay';
    overlay.innerHTML = `
    <div class="quiz-prep-backdrop">
        <div class="quiz-prep-card">
            <div class="quiz-prep-icon">📝</div>
            <div class="quiz-prep-title">Preparing Your Quiz</div>
            <p class="text-sm text-muted" id="qp-topic-name" style="margin-bottom:4px;">${topicName || 'Topic Quiz'}</p>

            <div class="quiz-prep-steps">
                <div class="quiz-prep-step active" id="qp-step-1">
                    <span class="quiz-prep-step-icon"><span class="spinner" style="width:16px;height:16px;border-width:2px;"></span></span>
                    <span id="qp-text-1">Initializing generator…</span>
                </div>
                <div class="quiz-prep-step" id="qp-step-2">
                    <span class="quiz-prep-step-icon">⏳</span>
                    <span id="qp-text-2">Generating batches (5 per call)…</span>
                </div>
                <div class="quiz-prep-step" id="qp-step-3">
                    <span class="quiz-prep-step-icon">⏳</span>
                    <span id="qp-text-3">Finalizing session…</span>
                </div>
            </div>

            <div class="quiz-prep-bar"><div class="quiz-prep-bar-fill" id="qp-bar"></div></div>
            <div class="text-sm text-muted" style="margin-top:10px;" id="qp-pct">0%</div>
        </div>
    </div>`;
    document.body.appendChild(overlay);

    api.generateQuizSSE(currentEnrollment, topicId, 10, {
        onStart(data) {
            updateQuizBar(10);
            setStepDone('qp-step-1');
            setStepActive('qp-step-2');
            document.getElementById('qp-text-1').textContent = 'Content analysis complete ✅';
            if (data.topic_name) document.getElementById('qp-topic-name').textContent = data.topic_name;
        },
        onProgress(data) {
            document.getElementById('qp-text-2').textContent = data.message;
            const pct = 10 + Math.round((data.current / 10) * 80);
            updateQuizBar(pct);
        },
        async onDone(data) {
            setStepDone('qp-step-2');
            setStepActive('qp-step-3');
            document.getElementById('qp-text-3').textContent = 'Session created! Redirecting…';
            updateQuizBar(100);
            
            await sleep(500);
            document.getElementById('quiz-prep-overlay')?.remove();
            window.location.href = `/quiz.html?enrollment=${currentEnrollment}&sessionId=${data.session_id}`;
        },
        onError(data) {
            document.getElementById('quiz-prep-overlay')?.remove();
            showToast(data.error || 'Generation failed', 'error');
        }
    });
}

function setStepDone(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('active');
    el.classList.add('done');
    el.querySelector('.quiz-prep-step-icon').innerHTML = '✅';
}
function setStepActive(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('active');
    el.querySelector('.quiz-prep-step-icon').innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px;"></span>';
}
function updateQuizBar(pct) {
    const bar = document.getElementById('qp-bar');
    const pctEl = document.getElementById('qp-pct');
    if (bar) bar.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
}
async function animateQuizPrep(targetPct, stepId, label) {
    const duration = 600 + Math.random() * 800;
    const steps = 10;
    const startPct = parseInt(document.getElementById('qp-bar')?.style?.width || '0');
    for (let i = 1; i <= steps; i++) {
        await sleep(duration / steps);
        const p = Math.round(startPct + ((targetPct - startPct) * (i / steps)));
        updateQuizBar(p);
    }
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function startTaskQuiz(taskId, topicName, topicId) {
    if (topicId) {
        startTopicQuiz(topicId, topicName);
    } else {
        window.location.href = `/quiz.html?enrollment=${currentEnrollment}&type=topic`;
    }
}

// ───────────────────────── Complete task ─────────────────────────
async function completeTask(itemId) {
    try {
        await api.completeItem(currentEnrollment, itemId);
        showToast('Task completed!', 'success');
        await loadStudyDashboard();
    } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
//  BUILD LEARNING PATH (SSE)
// ═══════════════════════════════════════════════════════════════
async function buildLearningPath() {
    if (!document.getElementById('reader-styles')) injectReaderStyles();
    const btn = document.querySelector('[onclick="buildLearningPath()"]');
    if (btn) { btn.disabled = true; btn.textContent = 'Building…'; }

    const overlay = document.createElement('div');
    overlay.id = 'gen-overlay';
    overlay.innerHTML = `
    <div class="quiz-prep-backdrop">
        <div class="quiz-prep-card">
            <div class="quiz-prep-icon">🧠</div>
            <div class="quiz-prep-title">Building Learning Path</div>
            <p id="path-msg" class="text-sm text-muted">Starting from today…</p>
            <div class="quiz-prep-bar"><div class="quiz-prep-bar-fill" id="path-bar" style="width:0%"></div></div>
            <div class="text-sm text-muted" style="margin-top:10px;" id="path-pct">0%</div>
        </div>
    </div>`;
    document.body.appendChild(overlay);

    api.buildPathSSE(currentEnrollment, {
        onProgress(d) {
            const msg = document.getElementById('path-msg');
            const bar = document.getElementById('path-bar');
            const pct = document.getElementById('path-pct');
            if (msg) msg.textContent = d.message;
            if (bar) bar.style.width = d.pct + '%';
            if (pct) pct.textContent = d.pct + '%';
        },
        async onDone(d) {
            overlay.remove();
            if (btn) { btn.disabled = false; btn.textContent = '🧠 Build Learning Path'; }
            showToast(`Learning path ready! Starts today, ${d.schedule_items_count} items.`, 'success');
            await loadStudyDashboard();
        },
        onError(d) {
            overlay.remove();
            if (btn) { btn.disabled = false; btn.textContent = '🧠 Build Learning Path'; }
            showToast(`Error: ${d.error || d.message}`, 'error');
        },
    });
}

// ═══════════════════════════════════════════════════════════════
//  GENERATE ALL CONTENT (SSE, RESUMABLE)
// ═══════════════════════════════════════════════════════════════
async function generateAllContent() {
    const btn = document.querySelector('[onclick="generateAllContent()"]');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Generating…'; }

    const container = document.getElementById('gen-progress');
    if (!container) return;
    container.classList.remove('hidden');
    container.innerHTML = `
    <div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-xl);padding:var(--space-6);margin-bottom:var(--space-6);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-4);">
            <h3 style="display:flex;align-items:center;gap:8px;">⚡ Generating Study Content</h3>
            <span id="gen-counter" style="font-family:var(--font-mono);color:var(--text-tertiary);">0 / ?</span>
        </div>
        <div style="background:var(--bg-input);border-radius:99px;height:10px;overflow:hidden;margin-bottom:var(--space-4);">
            <div id="gen-bar" style="height:100%;width:0%;background:linear-gradient(90deg,var(--accent-primary),var(--accent-secondary));border-radius:99px;transition:width .4s ease;"></div>
        </div>
        <div id="gen-current" style="color:var(--text-secondary);font-size:var(--text-sm);margin-bottom:var(--space-4);">Checking existing content…</div>
        <div id="gen-chapters" style="display:flex;flex-direction:column;gap:6px;max-height:400px;overflow-y:auto;"></div>
    </div>`;

    api.generateContentSSE(currentEnrollment, {
        onStart(d) { document.getElementById('gen-counter').textContent = `0 / ${d.total_chapters}`; },
        onProgress(d) {
            document.getElementById('gen-current').textContent = `⏳ Generating: ${d.topic_name}…`;
            document.getElementById('gen-bar').style.width = d.pct + '%';
        },
        onChapter(d) {
            document.getElementById('gen-counter').textContent = `${d.chapter} / ${d.total}`;
            document.getElementById('gen-bar').style.width = d.pct + '%';
            const cached = d.cached ? ' <span style="color:var(--accent-secondary);font-size:10px;">(CACHED)</span>' : '';
            document.getElementById('gen-current').textContent = `✅ ${d.topic_name}`;
            const el = document.getElementById('gen-chapters');
            el.innerHTML += `
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg-card);border-radius:var(--radius-md);border-left:3px solid ${d.cached?'var(--accent-secondary)':'var(--success)'};">
                <span style="color:${d.cached?'var(--accent-secondary)':'var(--success)'};font-weight:700;min-width:36px;">Ch ${d.chapter}</span>
                <div style="flex:1;"><div style="font-weight:600;font-size:var(--text-sm);">${d.title||d.topic_name}${cached}</div></div>
            </div>`;
            el.scrollTop = el.scrollHeight;
        },
        onAgentStep(d) {
            const current = document.getElementById('gen-current');
            if (!current) return;
            const icons = { model_a: '🤖', model_b: '🤖', critic_evaluating: '🧑‍⚖️', critic_done: '✅' };
            const icon = icons[d.step] || '⚙️';
            const colors = { model_a: 'var(--accent-primary)', model_b: 'var(--accent-secondary)', critic_evaluating: 'var(--warning)', critic_done: 'var(--success)' };
            const color = colors[d.step] || 'var(--text-secondary)';
            
            current.innerHTML = `<span style="display:flex;align-items:center;gap:6px;">${icon} <span>${sanitizeText(d.message)}</span></span>`;
            
            // Populate Popup
            const popup = document.getElementById('critic-popup');
            const feed = document.getElementById('critic-feed');
            if (popup && feed) {
                popup.classList.remove('hidden');
                // Force reflow
                void popup.offsetWidth;
                popup.style.opacity = '1';
                popup.style.transform = 'translateY(0)';
                
                const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
                feed.innerHTML += `<div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:${color};">
                    <span style="opacity:0.5;font-size:10px;min-width:60px;">${time}</span>
                    <span>${icon} ${sanitizeText(d.message)}</span>
                </div>`;
                feed.scrollTop = feed.scrollHeight;
            }
        },
        onError(d) {
            const el = document.getElementById('gen-chapters');
            if (el) el.innerHTML += `
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg-card);border-radius:var(--radius-md);border-left:3px solid var(--danger);">
                <span style="color:var(--danger);font-weight:700;min-width:36px;">Ch ${d.chapter}</span>
                <div style="flex:1;"><div style="font-weight:600;font-size:var(--text-sm);color:var(--danger);">${d.topic_name}: ${d.error}</div></div>
            </div>`;
        },
        async onDone(d) {
            document.getElementById('gen-current').innerHTML = `<span style="color:var(--success);font-weight:600;">🎉 ${d.message}</span>`;
            document.getElementById('gen-bar').style.width = '100%';
            if (btn) { btn.disabled = false; btn.innerHTML = '📚 Generate All Content'; }
            showToast(d.message, 'success');
            await loadStudyDashboard();
        },
    });
}

// ───────────────────────── Schedule view ─────────────────────────
async function viewSchedule() {
    try {
        const items = await api.getSchedule(currentEnrollment);
        const container = document.getElementById('schedule-view');
        if (!container) return;
        container.classList.remove('hidden');
        let html = '<h3 style="margin-bottom:var(--space-4)">Full Schedule</h3>';
        let currentDay = -1;
        for (const item of items) {
            if (item.day_number !== currentDay) {
                currentDay = item.day_number;
                html += `<div style="margin-top:var(--space-4);font-weight:600;color:var(--accent-primary);">Day ${currentDay} — ${item.scheduled_date||''}</div>`;
            }
            const icon = item.status === 'completed' ? '&#9989;' : '&#9744;';
            html += `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;"><span>${icon}</span><div style="flex:1;"><span style="font-weight:500;">${item.title}</span><span class="text-sm text-muted" style="margin-left:8px;">${item.estimated_minutes}min</span></div></div>`;
        }
        container.innerHTML = html;
    } catch (e) { showToast(e.message, 'error'); }
}
