document.addEventListener('DOMContentLoaded', async () => {
    if (!checkAuth()) return;

    const user = api.getUser();
    if (user) {
        const welcomeName = document.getElementById('welcome-name');
        if (welcomeName) welcomeName.textContent = user.full_name;

        const userNameEl = document.getElementById('user-name');
        if (userNameEl) userNameEl.textContent = user.full_name;
    }

    try {
        await loadEnrollments();
    } catch (error) {
        console.error('Failed to load enrollments:', error);
    }

    try {
        await loadNotifications();
    } catch (error) {
        console.error('Failed to load notifications:', error);
    }
});

async function loadEnrollments() {
    const container = document.getElementById('enrollments-container');
    if (!container) return;

    try {
        const enrollments = await Promise.race([
            api.getEnrollments(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timeout')), 5000)
            )
        ]);

        if (enrollments.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128218;</div>
                    <div class="empty-state-title">No Enrollments Yet</div>
                    <div class="empty-state-text">Browse available exams and enroll to start your learning journey.</div>
                    <button class="btn btn-primary" onclick="showExamCatalog()">Browse Exams</button>
                </div>`;
            return;
        }

        let html = '<div class="card-grid">';
        for (const enrollment of enrollments) {
            const examName = enrollment.exam ? enrollment.exam.name : 'Unknown Exam';
            const statusBadge = enrollment.status === 'active'
                ? '<span class="badge badge-success">Active</span>'
                : `<span class="badge badge-info">${enrollment.status}</span>`;

            let mastery = 0, scheduleCompletion = 0;
            try {
                const progress = await Promise.race([
                    api.getProgressSummary(enrollment.id),
                    new Promise((_, reject) =>
                        setTimeout(() => reject(new Error('Progress timeout')), 3000)
                    )
                ]);
                mastery = progress.overall_mastery || 0;
                scheduleCompletion = progress.schedule_completion_pct || 0;
            } catch (err) {
                console.warn('Could not load progress for enrollment:', err);
            }

            html += `
                <div class="card enrollment-card" onclick="openEnrollment('${enrollment.id}')">
                    <div class="card-header">
                        <div class="card-title">${examName}</div>
                        <div class="enrollment-status">${statusBadge}</div>
                    </div>
                    <div style="margin-top: var(--space-4)">
                        <div class="flex justify-between mb-4">
                            <span class="text-sm text-muted">Mastery</span>
                            <span class="text-sm font-bold">${Math.round(mastery)}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${mastery}%"></div>
                        </div>
                    </div>
                    <div class="enrollment-meta">
                        <div class="enrollment-meta-item">
                            <span class="enrollment-meta-label">Progress</span>
                            <span class="enrollment-meta-value">${Math.round(scheduleCompletion)}%</span>
                        </div>
                        <div class="enrollment-meta-item">
                            <span class="enrollment-meta-label">Target</span>
                            <span class="enrollment-meta-value">${enrollment.target_score || 70}%</span>
                        </div>
                        <div class="enrollment-meta-item">
                            <span class="enrollment-meta-label">Enrolled</span>
                            <span class="enrollment-meta-value">${new Date(enrollment.enrolled_at).toLocaleDateString()}</span>
                        </div>
                    </div>
                </div>`;
        }
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading enrollments:', error);
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-title">No Enrollments</div>
                <div class="empty-state-text">Start by browsing available exams.</div>
                <button class="btn btn-primary" onclick="showExamCatalog()">Browse Exams</button>
            </div>`;
    }
}

async function loadNotifications() {
    try {
        const notifications = await api.getNotifications();
        const badge = document.getElementById('notification-count');
        if (badge) {
            if (notifications.length > 0) {
                badge.textContent = notifications.length;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
    } catch {}
}

async function showExamCatalog() {
    const modal = document.getElementById('exam-modal');
    const examList = document.getElementById('exam-list');

    if (!modal || !examList) return;

    try {
        showLoading('Loading exams...');
        const exams = await Promise.race([
            api.listExams(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timeout')), 5000)
            )
        ]);
        hideLoading();

        let html = '';
        for (const exam of exams) {
            html += `
                <div class="card" style="margin-bottom: var(--space-4); cursor: pointer;" onclick="enrollInExam('${exam.id}')">
                    <div class="card-title">${exam.name}</div>
                    <div class="card-subtitle">${exam.description || exam.category || ''}</div>
                    ${exam.exam_date ? `<div class="mt-2 text-sm text-muted">Exam Date: ${new Date(exam.exam_date).toLocaleDateString()}</div>` : ''}
                </div>`;
        }
        examList.innerHTML = html || '<div class="text-muted text-center">No exams available</div>';
        modal.classList.add('active');
    } catch (error) {
        hideLoading();
        console.error('Error loading exams:', error);
        examList.innerHTML = '<div class="text-muted text-center">Failed to load exams. Please try again.</div>';
        modal.classList.add('active');
    }
}

async function enrollInExam(examId) {
    try {
        showLoading('Enrolling and loading syllabus...');
        const enrollment = await api.enroll(examId);
        hideLoading();
        showToast('Enrolled successfully! Starting diagnostic...', 'success');

        const modal = document.getElementById('exam-modal');
        if (modal) modal.classList.remove('active');

        // Redirect to diagnostic
        setTimeout(() => {
            window.location.href = `/quiz.html?enrollment=${enrollment.id}&type=diagnostic`;
        }, 1000);
    } catch (error) {
        hideLoading();
        showToast(error.message, 'error');
    }
}

function openEnrollment(enrollmentId) {
    localStorage.setItem('current_enrollment', enrollmentId);
    window.location.href = `/study.html?enrollment=${enrollmentId}`;
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
}
