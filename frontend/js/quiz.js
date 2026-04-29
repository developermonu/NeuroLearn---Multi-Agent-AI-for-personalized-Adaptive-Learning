let quizState = {
    sessionId: null,
    enrollmentId: null,
    type: null,
    currentQuestion: null,
    totalQuestions: 0,
    answeredCount: 0,
    correctCount: 0,
    selectedAnswer: null,
    answered: false,
};

/** Sanitize HTML to prevent XSS from LLM-generated content */
function sanitizeText(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', async () => {
    if (!checkAuth()) return;

    const params = new URLSearchParams(window.location.search);
    quizState.enrollmentId = params.get('enrollment');
    quizState.type = params.get('type') || 'topic';
    const topicId = params.get('topic');
    const sessionId = params.get('sessionId');

    if (!quizState.enrollmentId) {
        document.querySelector('.quiz-header').classList.add('hidden');
        document.getElementById('quiz-content').innerHTML = `
            <div class="card" style="padding:var(--space-8);text-align:center;">
                <h2 style="font-size:var(--text-2xl);margin-bottom:var(--space-2);">Quiz Hub</h2>
                <p class="text-muted" style="margin-bottom:var(--space-8);">Select a course below to take your diagnostic assessment or chapter quizzes.</p>
                <div id="quiz-hub-list" style="max-width:600px;margin:0 auto;text-align:left;display:flex;flex-direction:column;gap:var(--space-4);">
                    <div class="spinner" style="margin:0 auto;"></div>
                </div>
            </div>
        `;
        await loadQuizHub();
        return;
    }

    try {
        if (sessionId) {
            // Already generated (from study.js)
            quizState.sessionId = sessionId;
            showLoading('Loading questions...');
            // Need total questions - get from session if possible or just load first question
            // For now we'll load first question which updates total
            await loadQuestion();
            hideLoading();
            return;
        }

        if (quizState.type === 'diagnostic') {
            // SSE-based diagnostic with per-question progress
            const quizContent = document.getElementById('quiz-content');
            if (quizContent) {
                quizContent.innerHTML = `
                <div class="quiz-prep-card" style="text-align:center;padding:var(--space-8);">
                    <div class="quiz-prep-icon" style="font-size:48px;">🧠</div>
                    <div class="quiz-prep-title" style="font-size:var(--text-xl);font-weight:700;margin:var(--space-4) 0;">Generating Diagnostic Quiz</div>
                    <p id="diag-msg" class="text-sm text-muted">Connecting to AI question generator...</p>
                    <div class="quiz-prep-bar" style="margin:var(--space-4) auto;max-width:400px;"><div class="quiz-prep-bar-fill" id="diag-bar" style="width:0%"></div></div>
                    <div class="text-sm text-muted" id="diag-pct" style="margin-top:var(--space-2);">0%</div>
                    <div id="diag-questions" style="margin-top:var(--space-4);display:flex;flex-wrap:wrap;gap:6px;justify-content:center;"></div>
                </div>`;
            }

            api.startDiagnosticSSE(quizState.enrollmentId, {
                onStart: (data) => {
                    const msg = document.getElementById('diag-msg');
                    if (msg) msg.textContent = `Generating ${data.total_questions} questions across ${data.total_topics} topics...`;
                    quizState.totalQuestions = data.total_questions;
                },
                onProgress: (data) => {
                    const msg = document.getElementById('diag-msg');
                    const bar = document.getElementById('diag-bar');
                    const pct = document.getElementById('diag-pct');
                    if (msg) msg.textContent = data.message;
                    if (bar) bar.style.width = data.pct + '%';
                    if (pct) pct.textContent = data.pct + '%';
                },
                onQuestionReady: (data) => {
                    const el = document.getElementById('diag-questions');
                    if (el) {
                        el.innerHTML += `<span style="width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;background:var(--success);color:white;">${data.current}</span>`;
                    }
                },
                onDone: async (data) => {
                    quizState.sessionId = data.session_id;
                    quizState.totalQuestions = data.total_questions;
                    hideLoading();
                    await loadQuestion();
                },
                onError: (data) => {
                    hideLoading();
                    showToast(data.error || 'Diagnostic generation failed', 'error');
                }
            });
            return;
        } else {
            // Topic quiz with SSE progress
            if (!topicId) {
                showToast('No topic specified', 'error');
                return;
            }

            showLoading('Connecting to quiz generator...');
            
            api.generateQuizSSE(quizState.enrollmentId, topicId, 10, {
                onStart: (data) => {
                    showLoading(`Starting generation for ${data.topic_name}...`);
                    quizState.totalQuestions = data.total;
                },
                onProgress: (data) => {
                    showLoading(data.message);
                },
                onDone: async (data) => {
                    quizState.sessionId = data.session_id;
                    hideLoading();
                    await loadQuestion();
                },
                onError: (data) => {
                    hideLoading();
                    showToast(data.error || 'Generation failed', 'error');
                }
            });
        }
    } catch (error) {
        hideLoading();
        showToast(error.message, 'error');
    }
});

async function loadQuestion() {
    const container = document.getElementById('quiz-content');
    if (!container) return;

    try {
        let question;
        if (quizState.type === 'diagnostic') {
            question = await api.getQuestion(quizState.enrollmentId, quizState.sessionId);
        } else {
            question = await api.getQuizQuestion(quizState.sessionId);
        }

        quizState.currentQuestion = question;
        quizState.selectedAnswer = null;
        quizState.answered = false;

        updateProgressBar(question.question_number, question.total_questions);
        renderQuestion(question);
    } catch (error) {
        if (error.message.includes('All questions answered') || error.message.includes('completed')) {
            await finishQuiz();
        } else {
            showToast(error.message, 'error');
        }
    }
}

function updateProgressBar(current, total) {
    const progressText = document.getElementById('quiz-progress-text');
    const progressFill = document.getElementById('quiz-progress-fill');

    if (progressText) progressText.textContent = `Question ${current} of ${total}`;
    if (progressFill) progressFill.style.width = `${(current / total) * 100}%`;
}

function renderQuestion(question) {
    const container = document.getElementById('quiz-content');

    const options = question.options || [];
    const letters = ['A', 'B', 'C', 'D'];

    let optionsHtml = '';
    options.forEach((opt, i) => {
        const letter = letters[i] || String.fromCharCode(65 + i);
        const optText = sanitizeText(opt.replace(/^[A-D]\)\s*/, ''));
        optionsHtml += `
            <div class="option-item" data-answer="${letter}" onclick="selectOption(this, '${letter}')">
                <div class="option-letter">${letter}</div>
                <div class="option-text">${optText}</div>
            </div>`;
    });

    container.innerHTML = `
        <div class="question-card">
            <div class="question-meta">
                <span class="badge badge-${question.difficulty === 'easy' ? 'success' : question.difficulty === 'hard' ? 'danger' : 'warning'}">${sanitizeText(question.difficulty)}</span>
                <span class="badge badge-info">${sanitizeText(question.bloom_level)}</span>
            </div>
            <div class="question-text">${sanitizeText(question.question_text)}</div>
            <div class="options-list" id="options-list">${optionsHtml}</div>
            <div id="explanation-container"></div>
        </div>
        <div class="quiz-actions">
            <div class="text-sm text-muted">Question ${question.question_number} of ${question.total_questions}</div>
            <div class="flex gap-3">
                <button class="btn btn-primary" id="submit-btn" onclick="submitAnswer()" disabled>Submit Answer</button>
                <button class="btn btn-secondary hidden" id="next-btn" onclick="nextQuestion()">Next &rarr;</button>
            </div>
        </div>`;
}

function selectOption(el, answer) {
    if (quizState.answered) return;

    document.querySelectorAll('.option-item').forEach(o => o.classList.remove('selected'));
    el.classList.add('selected');
    quizState.selectedAnswer = answer;

    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) submitBtn.disabled = false;
}

async function submitAnswer() {
    if (!quizState.selectedAnswer || quizState.answered) return;

    try {
        let result;
        if (quizState.type === 'diagnostic') {
            result = await api.submitAnswer(quizState.enrollmentId, quizState.sessionId, quizState.selectedAnswer);
        } else {
            result = await api.submitQuizAnswer(quizState.sessionId, quizState.selectedAnswer);
        }

        quizState.answered = true;
        quizState.answeredCount++;
        if (result.is_correct) quizState.correctCount++;

        // Highlight correct/incorrect
        document.querySelectorAll('.option-item').forEach(opt => {
            const letter = opt.dataset.answer;
            if (letter === result.correct_answer) opt.classList.add('correct');
            else if (letter === quizState.selectedAnswer && !result.is_correct) opt.classList.add('incorrect');
        });

        // Show explanation
        const explanationContainer = document.getElementById('explanation-container');
        if (explanationContainer && result.explanation) {
            explanationContainer.innerHTML = `
                <div class="explanation-box ${result.is_correct ? 'correct' : 'incorrect'}">
                    <div class="explanation-title">${result.is_correct ? '&#9989; Correct!' : '&#10060; Incorrect'}</div>
                    <div>${sanitizeText(result.explanation)}</div>
                </div>`;
        }

        const submitBtn = document.getElementById('submit-btn');
        const nextBtn = document.getElementById('next-btn');
        if (submitBtn) submitBtn.classList.add('hidden');
        if (nextBtn) nextBtn.classList.remove('hidden');

        if (result.next_question === null || result.next_question === undefined) {
            if (nextBtn) nextBtn.textContent = 'View Results';
        }
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function nextQuestion() {
    const nextBtn = document.getElementById('next-btn');
    if (nextBtn && nextBtn.textContent === 'View Results') {
        await finishQuiz();
        return;
    }
    await loadQuestion();
}

async function finishQuiz() {
    try {
        showLoading('Calculating results...');
        let result;
        if (quizState.type === 'diagnostic') {
            result = await api.completeDiagnostic(quizState.enrollmentId, quizState.sessionId);
        } else {
            result = await api.completeQuiz(quizState.sessionId);
        }
        hideLoading();
        renderResults(result);
    } catch (error) {
        hideLoading();
        showToast(error.message, 'error');
        renderResults({ score_pct: (quizState.correctCount / Math.max(quizState.answeredCount, 1)) * 100, correct: quizState.correctCount, total: quizState.answeredCount });
    }
}

function renderResults(result) {
    const container = document.getElementById('quiz-content');
    const score = result.score_pct || 0;
    const passed = score >= 60;

    // Strengths / Weaknesses cards (from diagnostic)
    let strengthWeakness = '';
    if (quizState.type === 'diagnostic' && result.learning_profile) {
        const strengths = result.learning_profile.strong_areas || [];
        const weaknesses = result.learning_profile.gap_areas || [];

        strengthWeakness = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-top:var(--space-6);">
            <div style="padding:var(--space-4);background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);border-radius:var(--radius-lg);">
                <div style="font-weight:700;color:var(--success);margin-bottom:var(--space-2);display:flex;align-items:center;gap:6px;">💪 Strengths</div>
                ${strengths.length > 0 ? strengths.map(s => `<div style="padding:6px 10px;background:rgba(16,185,129,0.1);border-radius:var(--radius-md);margin-bottom:4px;font-size:var(--text-sm);">${sanitizeText(s)}</div>`).join('') : '<div class="text-sm text-muted">Not enough data</div>'}
            </div>
            <div style="padding:var(--space-4);background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:var(--radius-lg);">
                <div style="font-weight:700;color:var(--danger);margin-bottom:var(--space-2);display:flex;align-items:center;gap:6px;">📉 Needs Improvement</div>
                ${weaknesses.length > 0 ? weaknesses.map(w => `<div style="padding:6px 10px;background:rgba(239,68,68,0.1);border-radius:var(--radius-md);margin-bottom:4px;font-size:var(--text-sm);">${sanitizeText(w)}</div>`).join('') : '<div class="text-sm text-muted">Good across all topics!</div>'}
            </div>
        </div>`;
    }

    // Bloom's taxonomy breakdown
    let bloomChart = '';
    if (quizState.type === 'diagnostic' && result.bloom_scores) {
        const levels = ['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'];
        const colors = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899'];
        bloomChart = `
        <div style="margin-top:var(--space-6);padding:var(--space-4);background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-lg);">
            <div style="font-weight:700;margin-bottom:var(--space-3);display:flex;align-items:center;gap:6px;">🎯 Bloom's Taxonomy Breakdown</div>
            ${levels.map((lvl, i) => {
                const val = result.bloom_scores[lvl] || 0;
                return `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                    <span style="width:80px;font-size:var(--text-xs);text-transform:capitalize;color:var(--text-secondary);">${lvl}</span>
                    <div style="flex:1;height:10px;background:var(--bg-input);border-radius:99px;overflow:hidden;">
                        <div style="height:100%;width:${val}%;background:${colors[i]};border-radius:99px;transition:width .5s ease;"></div>
                    </div>
                    <span style="width:40px;text-align:right;font-size:var(--text-xs);font-weight:600;">${val.toFixed(0)}%</span>
                </div>`;
            }).join('')}
        </div>`;
    }

    // Cognitive gap analysis (LLM-generated)
    let cognitiveAnalysis = '';
    if (quizState.type === 'diagnostic' && result.cognitive_gap_analysis && result.cognitive_gap_analysis.length > 20) {
        cognitiveAnalysis = `
        <div style="margin-top:var(--space-4);padding:var(--space-4);background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-lg);">
            <div style="font-weight:700;margin-bottom:var(--space-2);display:flex;align-items:center;gap:6px;">🔬 AI Cognitive Analysis</div>
            <div style="font-size:var(--text-sm);color:var(--text-secondary);line-height:1.6;white-space:pre-wrap;">${sanitizeText(result.cognitive_gap_analysis)}</div>
        </div>`;
    }

    let extraInfo = '';
    if (quizState.type === 'diagnostic' && result.ability_level) {
        extraInfo = `
            <div class="stats-grid mt-6">
                <div class="stat-card"><div class="stat-icon info">&#920;</div><div><div class="stat-value">${result.irt_theta?.toFixed(2) || '0'}</div><div class="stat-label">IRT Ability (theta)</div></div></div>
                <div class="stat-card"><div class="stat-icon primary">&#127891;</div><div><div class="stat-value">${result.ability_level}</div><div class="stat-label">Ability Level</div></div></div>
                <div class="stat-card"><div class="stat-icon success">&#128154;</div><div><div class="stat-value">${result.easy_pct?.toFixed(0) || 0}%</div><div class="stat-label">Easy Score</div></div></div>
                <div class="stat-card"><div class="stat-icon danger">&#128308;</div><div><div class="stat-value">${result.hard_pct?.toFixed(0) || 0}%</div><div class="stat-label">Hard Score</div></div></div>
            </div>
            ${strengthWeakness}
            ${bloomChart}
            ${cognitiveAnalysis}
            ${result.conceptual_plateau ? '<div class="mt-4" style="padding: var(--space-4); background: var(--warning-light); border-radius: var(--radius-md); color: var(--warning);"><strong>Conceptual Plateau Detected:</strong> High recall but low application scores. Focus on practice problems.</div>' : ''}
        `;
    }

    container.innerHTML = `
        <div class="score-card card">
            <div class="score-circle ${passed ? 'passed' : 'failed'}">
                <div class="score-value">${Math.round(score)}%</div>
                <div class="score-label">${passed ? 'Passed' : 'Needs Work'}</div>
            </div>
            <h2>${quizState.type === 'diagnostic' ? 'Diagnostic Complete!' : passed ? 'Great Job!' : 'Keep Practicing!'}</h2>
            <p class="text-muted mt-2">You got ${result.correct || quizState.correctCount} out of ${result.total || quizState.answeredCount} questions correct</p>
            ${extraInfo}
            <div class="flex justify-center gap-4 mt-6">
                ${quizState.type === 'diagnostic'
                    ? `<button class="btn btn-primary btn-lg" onclick="buildPath()">🧠 Build Learning Path</button>`
                    : `<button class="btn btn-secondary" onclick="window.location.href='/study.html?enrollment=${quizState.enrollmentId}'">Back to Study</button>`
                }
                <button class="btn btn-ghost" onclick="window.location.href='/dashboard.html'">Dashboard</button>
            </div>
        </div>`;

    // hide progress bar
    const progressBar = document.querySelector('.quiz-header');
    if (progressBar) progressBar.classList.add('hidden');
}

async function buildPath() {
    try {
        showLoading('Building your personalized learning path...');
        await api.buildPath(quizState.enrollmentId);
        hideLoading();
        showToast('Learning path created!', 'success');
        window.location.href = `/study.html?enrollment=${quizState.enrollmentId}`;
    } catch (error) {
        hideLoading();
        showToast(error.message, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
//  QUIZ HUB 
// ═══════════════════════════════════════════════════════════════
async function loadQuizHub() {
    try {
        const enrollments = await api.getMyEnrollments();
        const hubList = document.getElementById('quiz-hub-list');
        
        if (!enrollments || enrollments.length === 0) {
            hubList.innerHTML = `<div class="text-center text-muted">You are not enrolled in any courses. <br><a href="/dashboard.html" style="color:var(--accent-primary);">Browse Courses</a></div>`;
            return;
        }

        let html = '';
        for (const enr of enrollments) {
            const courseName = enr.exam ? enr.exam.title : 'Course';
            html += `
            <div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-lg);padding:var(--space-4);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-4);">
                    <h3 style="font-size:var(--text-lg);">${courseName}</h3>
                    <button class="btn btn-primary btn-sm" onclick="window.location.href='/quiz.html?enrollment=${enr.id}&type=diagnostic'">🧠 Diagnostic Quiz</button>
                </div>
                <div id="hub-topics-${enr.id}" style="display:flex;flex-direction:column;gap:8px;">
                    <div class="text-sm text-muted">Loading chapter quizzes...</div>
                </div>
            </div>`;
        }
        hubList.innerHTML = html;

        // Fetch topics for each enrollment
        for (const enr of enrollments) {
            const topicsData = await api.getTopicsStatus(enr.id);
            const topicsContainer = document.getElementById(`hub-topics-${enr.id}`);
            if (topicsData && topicsData.length > 0) {
                const availableQuizzes = topicsData.filter(t => t.content_generated && t.topic_unlocked);
                if (availableQuizzes.length > 0) {
                    topicsContainer.innerHTML = availableQuizzes.map(t => `
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-md);">
                            <div>
                                <div style="font-weight:600;font-size:var(--text-sm);">${t.topic_name}</div>
                                <div style="font-size:var(--text-xs);color:var(--text-tertiary);">Chapter ${t.index + 1}</div>
                            </div>
                            <button class="btn btn-secondary btn-sm" onclick="window.location.href='/quiz.html?enrollment=${enr.id}&type=topic&topic=${t.topic_id}'">Take Quiz</button>
                        </div>
                    `).join('');
                } else {
                    topicsContainer.innerHTML = `<div class="text-sm text-muted">No chapter quizzes unlocked yet. Generate content in the Study section first.</div>`;
                }
            } else {
                topicsContainer.innerHTML = `<div class="text-sm text-muted">No topics found.</div>`;
            }
        }

    } catch (e) {
        console.error(e);
        document.getElementById('quiz-hub-list').innerHTML = `<div class="text-center text-danger">Failed to load quizzes.</div>`;
    }
}
