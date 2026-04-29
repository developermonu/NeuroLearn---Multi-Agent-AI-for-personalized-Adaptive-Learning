let qaState = {
    enrollmentId: null,
    conversationId: null,
    topicId: null,
};

document.addEventListener('DOMContentLoaded', async () => {
    if (!checkAuth()) return;

    const params = new URLSearchParams(window.location.search);
    qaState.enrollmentId = params.get('enrollment') || localStorage.getItem('current_enrollment');
    qaState.topicId = params.get('topic');

    await loadConversations();
    initChatInput();
});

async function loadConversations() {
    const sidebar = document.getElementById('conversations-list');
    if (!sidebar) return;

    try {
        const conversations = await api.getConversations();

        if (conversations.length === 0) {
            sidebar.innerHTML = '<div class="text-muted text-sm" style="padding: var(--space-4)">No conversations yet. Ask a question to start!</div>';
            return;
        }

        let html = '';
        for (const conv of conversations) {
            html += `
                <div class="nav-item ${qaState.conversationId === conv.id ? 'active' : ''}"
                     onclick="loadConversation('${conv.id}')">
                    <span class="nav-icon">&#128488;</span>
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${conv.title}</span>
                </div>`;
        }
        sidebar.innerHTML = html;
    } catch {}
}

async function loadConversation(conversationId) {
    qaState.conversationId = conversationId;

    try {
        const data = await api.getConversation(conversationId);
        const messagesContainer = document.getElementById('chat-messages');
        if (!messagesContainer) return;

        let html = '';
        if (data.messages && data.messages.length > 0) {
            for (const msg of data.messages) {
                html += renderMessage(msg);
            }
        } else {
            html = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#129302;</div>
                    <div class="empty-state-title">AI Tutor</div>
                    <div class="empty-state-text">Ask me anything about your course material. I'll route your question to the best AI model based on complexity.</div>
                </div>`;
        }
        messagesContainer.innerHTML = html;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        await loadConversations();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function renderMessage(msg) {
    const isUser = msg.role === 'user';
    let meta = '';
    if (!isUser && msg.model_tier) {
        meta = `<div class="chat-message-meta">
            <span class="badge badge-${msg.model_tier === 'high' ? 'danger' : msg.model_tier === 'medium' ? 'warning' : 'success'}">${msg.model_tier}</span>
            ${msg.complexity_score !== null && msg.complexity_score !== undefined ? `<span>Complexity: ${msg.complexity_score}/100</span>` : ''}
        </div>`;
    }

    return `
        <div class="chat-message ${msg.role}">
            <div>${msg.content}</div>
            ${meta}
        </div>`;
}

function initChatInput() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');

    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    if (sendBtn) {
        sendBtn.addEventListener('click', sendMessage);
    }
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const question = input.value.trim();
    if (!question) return;

    input.value = '';

    // Add user message to UI
    const messagesContainer = document.getElementById('chat-messages');
    if (messagesContainer) {
        // Clear empty state if present
        const emptyState = messagesContainer.querySelector('.empty-state');
        if (emptyState) {
            messagesContainer.innerHTML = '';
        }
        
        messagesContainer.innerHTML += renderMessage({ role: 'user', content: question });

        // Add loading indicator
        messagesContainer.innerHTML += '<div class="chat-message assistant" id="typing-indicator"><div class="spinner spinner-sm"></div> Thinking...</div>';
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    try {
        const result = await api.askQuestion({
            question,
            enrollment_id: qaState.enrollmentId,
            topic_id: qaState.topicId,
            conversation_id: qaState.conversationId,
        });

        qaState.conversationId = result.conversation_id;

        // Remove typing indicator
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();

        // Add AI response
        messagesContainer.innerHTML += renderMessage({
            role: 'assistant',
            content: result.answer,
            model_tier: result.model_tier,
            complexity_score: result.complexity_score,
        });
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        await loadConversations();
    } catch (error) {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
        showToast(error.message, 'error');
    }
}

function newConversation() {
    qaState.conversationId = null;
    const messagesContainer = document.getElementById('chat-messages');
    if (messagesContainer) {
        messagesContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#129302;</div>
                <div class="empty-state-title">AI Tutor</div>
                <div class="empty-state-text">Ask me anything about your course material. I'll route your question to the best AI model based on complexity.</div>
            </div>`;
    }
}
