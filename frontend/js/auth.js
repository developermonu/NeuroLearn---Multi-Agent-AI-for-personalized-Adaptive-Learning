function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === 'success' ? '&#10003;' : type === 'error' ? '&#10007;' : '&#9432;'}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function showLoading(message = 'Loading...') {
    let overlay = document.getElementById('loading-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `<div class="spinner"></div><div style="color: var(--text-secondary)">${message}</div>`;
        document.body.appendChild(overlay);
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.remove();
}

function checkAuth() {
    if (!api.isAuthenticated()) {
        window.location.href = '/';
        return false;
    }
    return true;
}

function logout() {
    api.clearTokens();
    window.location.href = '/';
}

function initAuthModal() {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const switchToRegister = document.getElementById('switch-to-register');
    const switchToLogin = document.getElementById('switch-to-login');
    const loginView = document.getElementById('login-view');
    const registerView = document.getElementById('register-view');

    if (switchToRegister) {
        switchToRegister.addEventListener('click', (e) => {
            e.preventDefault();
            loginView.classList.add('hidden');
            registerView.classList.remove('hidden');
        });
    }

    if (switchToLogin) {
        switchToLogin.addEventListener('click', (e) => {
            e.preventDefault();
            registerView.classList.add('hidden');
            loginView.classList.remove('hidden');
        });
    }

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;

            try {
                showLoading('Signing in...');
                await api.login(email, password);
                hideLoading();
                showToast('Welcome back!', 'success');
                window.location.href = '/dashboard.html';
            } catch (error) {
                hideLoading();
                showToast(error.message, 'error');
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                email: document.getElementById('reg-email').value,
                full_name: document.getElementById('reg-name').value,
                password: document.getElementById('reg-password').value,
                learning_style: document.getElementById('reg-style').value,
                daily_study_minutes: parseInt(document.getElementById('reg-minutes').value) || 60,
            };

            try {
                showLoading('Creating account...');
                await api.register(data);
                hideLoading();
                showToast('Account created successfully!', 'success');
                window.location.href = '/dashboard.html';
            } catch (error) {
                hideLoading();
                showToast(error.message, 'error');
            }
        });
    }
}

// Auto-redirect if already logged in
if (window.location.pathname === '/' || window.location.pathname === '/index.html') {
    if (api.isAuthenticated()) {
        window.location.href = '/dashboard.html';
    }
}
