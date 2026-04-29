const API_BASE = '/api/v1';

class APIClient {
    constructor() {
        this.accessToken = localStorage.getItem('access_token');
        this.refreshToken = localStorage.getItem('refresh_token');
    }

    setTokens(access, refresh) {
        this.accessToken = access;
        this.refreshToken = refresh;
        localStorage.setItem('access_token', access);
        localStorage.setItem('refresh_token', refresh);
    }

    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    }

    isAuthenticated() {
        return !!this.accessToken;
    }

    getUser() {
        try {
            return JSON.parse(localStorage.getItem('user'));
        } catch {
            return null;
        }
    }

    setUser(user) {
        localStorage.setItem('user', JSON.stringify(user));
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (response.status === 401 && this.refreshToken) {
                const refreshed = await this.tryRefresh();
                if (refreshed) {
                    headers['Authorization'] = `Bearer ${this.accessToken}`;
                    const retryResponse = await fetch(url, { ...options, headers });
                    return this.handleResponse(retryResponse);
                } else {
                    this.clearTokens();
                    window.location.href = '/';
                    throw new Error('Session expired');
                }
            }

            return this.handleResponse(response);
        } catch (error) {
            if (error.message === 'Session expired') throw error;
            throw new Error(`Network error: ${error.message}`);
        }
    }

    async handleResponse(response) {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return data;
    }

    async tryRefresh() {
        try {
            const response = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this.refreshToken }),
            });
            if (response.ok) {
                const data = await response.json();
                this.accessToken = data.access_token;
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
            return false;
        } catch {
            return false;
        }
    }

    // Auth
    async register(data) {
        const result = await this.request('/auth/register', { method: 'POST', body: JSON.stringify(data) });
        this.setTokens(result.access_token, result.refresh_token);
        this.setUser(result.user);
        return result;
    }

    async login(email, password) {
        const result = await this.request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
        this.setTokens(result.access_token, result.refresh_token);
        this.setUser(result.user);
        return result;
    }

    async getMe() { return this.request('/auth/me'); }

    // Courses
    async listExams() { return this.request('/courses'); }
    async getExam(id) { return this.request(`/courses/${id}`); }
    async getSyllabus(examId) { return this.request(`/courses/${examId}/syllabus`); }
    async getTopics(examId) { return this.request(`/courses/${examId}/topics`); }
    async enroll(examId, targetScore = 70) { return this.request('/courses/enroll', { method: 'POST', body: JSON.stringify({ exam_id: examId, target_score: targetScore }) }); }
    async getEnrollments() { return this.request('/courses/enrollments/my'); }
    async getMyEnrollments() { return this.getEnrollments(); }

    // Diagnostic
    async startDiagnostic(enrollmentId) { return this.request(`/diagnostic/${enrollmentId}/start`, { method: 'POST' }); }
    async getQuestion(enrollmentId, sessionId) { return this.request(`/diagnostic/${enrollmentId}/question/${sessionId}`); }
    async submitAnswer(enrollmentId, sessionId, answer) { return this.request(`/diagnostic/${enrollmentId}/answer/${sessionId}`, { method: 'POST', body: JSON.stringify({ answer }) }); }
    async completeDiagnostic(enrollmentId, sessionId) { return this.request(`/diagnostic/${enrollmentId}/complete/${sessionId}`, { method: 'POST' }); }

    // Diagnostic SSE — streams per-question generation progress
    startDiagnosticSSE(enrollmentId, handlers) {
        const url = `${API_BASE}/diagnostic/${enrollmentId}/start-stream`;
        this._fetchSSE(url, handlers);
    }

    // Learning Path
    async buildPath(enrollmentId) { return this.request(`/learning-path/${enrollmentId}/build`, { method: 'POST' }); }
    async getPath(enrollmentId) { return this.request(`/learning-path/${enrollmentId}`); }
    async getTodayTasks(enrollmentId) { return this.request(`/learning-path/${enrollmentId}/today`); }
    async getSchedule(enrollmentId) { return this.request(`/learning-path/${enrollmentId}/schedule`); }
    async completeItem(enrollmentId, itemId) { return this.request(`/learning-path/${enrollmentId}/complete-item/${itemId}`, { method: 'POST' }); }
    async reschedule(enrollmentId, strategy) { return this.request(`/learning-path/${enrollmentId}/reschedule`, { method: 'POST', body: JSON.stringify({ strategy }) }); }

    // Quiz
    async createQuiz(data) { return this.request('/quiz/create', { method: 'POST', body: JSON.stringify(data) }); }
    async getQuizQuestion(sessionId) { return this.request(`/quiz/${sessionId}/question`); }
    async submitQuizAnswer(sessionId, answer) { return this.request(`/quiz/${sessionId}/answer`, { method: 'POST', body: JSON.stringify({ answer }) }); }
    async completeQuiz(sessionId) { return this.request(`/quiz/${sessionId}/complete`, { method: 'POST' }); }

    // Q&A
    async askQuestion(data) { return this.request('/qa/ask', { method: 'POST', body: JSON.stringify(data) }); }
    async getConversations() { return this.request('/qa/conversations'); }
    async getConversation(id) { return this.request(`/qa/conversations/${id}`); }

    // Progress
    async getProgressSummary(enrollmentId) { return this.request(`/progress/enrollments/${enrollmentId}/summary`); }
    async getTopicMastery(enrollmentId) { return this.request(`/progress/topics/${enrollmentId}/mastery`); }
    async getNotifications() { return this.request('/progress/notifications'); }
    async markNotificationRead(id) { return this.request(`/progress/notifications/${id}/read`, { method: 'POST' }); }

    // Certificates
    async generateCertificate(enrollmentId) { return this.request(`/certificates/generate/${enrollmentId}`, { method: 'POST' }); }
    async getMyCertificates() { return this.request('/certificates/my'); }

    // Content Generation & Topic Progress
    async getTopicsStatus(enrollmentId) { return this.request(`/generate/${enrollmentId}/topics-status`); }
    async getTopicContent(enrollmentId, topicId) { return this.request(`/generate/${enrollmentId}/content/${topicId}`); }
    async generateTopicContent(enrollmentId, topicId) { return this.request(`/generate/${enrollmentId}/generate-topic/${topicId}`, { method: 'POST' }); }
    async markTopicRead(enrollmentId, topicId) { return this.request(`/generate/${enrollmentId}/mark-read/${topicId}`, { method: 'POST' }); }
    async markQuizPassed(enrollmentId, topicId) { return this.request(`/generate/${enrollmentId}/quiz-passed/${topicId}`, { method: 'POST' }); }

    /**
     * Stream chapter-by-chapter content generation via SSE.
     * @param {string} enrollmentId
     * @param {function} onProgress  - (data) called when a chapter starts
     * @param {function} onChapter   - (data) called when a chapter completes
     * @param {function} onDone      - (data) called when all chapters are done
     * @param {function} onError     - (data) called on error
     */
    generateContentSSE(enrollmentId, { onStart, onProgress, onChapter, onError, onDone }) {
        const url = `${API_BASE}/generate/${enrollmentId}/generate-all`;
        const es = new EventSource(url);
        // NOTE: EventSource doesn't send custom headers. Auth is handled
        // via cookie or we rely on the endpoint being accessible.
        // For now the endpoint uses Depends(get_current_user) which reads
        // the Authorization header — we override w/ a fetch-based SSE below.
        es.close(); // close the native one

        // Fetch-based SSE for auth support
        this._fetchSSE(url, { onStart, onProgress, onChapter, onError, onDone });
    }

    buildPathSSE(enrollmentId, { onProgress, onDone, onError }) {
        const url = `${API_BASE}/generate/${enrollmentId}/build-path-stream`;
        this._fetchSSE(url, { onProgress, onDone, onError });
    }

    generateQuizSSE(enrollmentId, topicId, numQuestions, { onStart, onProgress, onDone, onError }) {
        const url = `${API_BASE}/quiz/generate-stream/${enrollmentId}/${topicId}?num_questions=${numQuestions}`;
        this._fetchSSE(url, { onStart, onProgress, onDone, onError });
    }

    async _fetchSSE(url, handlers) {
        try {
            const headers = {};
            if (this.accessToken) {
                headers['Authorization'] = `Bearer ${this.accessToken}`;
            }
            const response = await fetch(url, { headers });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                if (handlers.onError) handlers.onError({ error: err.detail || 'Request failed' });
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line

                let eventType = null;
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ') && eventType) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            const handler = handlers['on' + eventType.charAt(0).toUpperCase() + eventType.slice(1)];
                            if (handler) handler(data);
                            else if (eventType === 'chapter' && handlers.onChapter) handlers.onChapter(data);
                            else if (eventType === 'agent_step' && handlers.onAgentStep) handlers.onAgentStep(data);
                            else if (eventType === 'question_ready' && handlers.onQuestionReady) handlers.onQuestionReady(data);
                        } catch (e) { /* skip bad JSON */ }
                        eventType = null;
                    }
                }
            }
        } catch (e) {
            if (handlers.onError) handlers.onError({ error: e.message });
        }
    }
}

const api = new APIClient();
