'use strict';

let lastContentSignature = '';
let previousModalFocus = null;

const emptyState = (message) => `
    <div class="empty-state">
        <svg class="empty-icon" aria-hidden="true"><use href="#icon-inbox"></use></svg>
        <p>${escapeHtml(message)}</p>
    </div>
`;

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    })[character]);
}

function fileNameFromPath(filePath) {
    return String(filePath || '').replaceAll('\\', '/').split('/').pop() || '未知文件';
}

async function apiFetch(url, options = {}) {
    return fetch(url, options);
}

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('subtranslatorTheme', theme);
    const toggle = document.getElementById('theme-toggle');
    const nextThemeName = theme === 'dark' ? '浅色' : '深色';
    toggle.setAttribute('aria-label', `切换${nextThemeName}主题`);
    toggle.title = `切换${nextThemeName}主题`;
}

function toggleTheme() {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

function openConfigModal() {
    const modal = document.getElementById('config-modal');
    previousModalFocus = document.activeElement;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => document.getElementById('api-key').focus());
}

function closeConfigModal() {
    const modal = document.getElementById('config-modal');
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (previousModalFocus) previousModalFocus.focus();
}

function keepFocusInModal(event) {
    if (event.key !== 'Tab') return;
    const modal = document.getElementById('config-modal');
    const focusable = [...modal.querySelectorAll('button, input, select, [tabindex]:not([tabindex="-1"])')]
        .filter(element => !element.disabled);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

function formatUptime(startTimeString) {
    if (!startTimeString) return '0h 0m';
    const difference = Math.max(0, Math.floor((Date.now() - new Date(startTimeString)) / 1000));
    const days = Math.floor(difference / 86400);
    const hours = Math.floor((difference % 86400) / 3600);
    const minutes = Math.floor((difference % 3600) / 60);
    return days ? `${days}d ${hours}h` : `${hours}h ${minutes}m`;
}

function getTimeDiff(timestamp) {
    const time = new Date(timestamp);
    if (Number.isNaN(time.getTime())) return '时间未知';
    const difference = Math.max(0, Math.floor((Date.now() - time.getTime()) / 1000));
    if (difference < 60) return `${difference} 秒前`;
    if (difference < 3600) return `${Math.floor(difference / 60)} 分钟前`;
    if (difference < 86400) return `${Math.floor(difference / 3600)} 小时前`;
    return time.toLocaleString('zh-CN');
}

async function updateConnectionStatus() {
    const state = document.getElementById('connection-state');
    const label = document.getElementById('connection-label');
    try {
        const response = await fetch('/health', {cache: 'no-store'});
        if (!response.ok) throw new Error('unhealthy');
        state.dataset.state = 'connected';
        label.textContent = '服务正常';
    } catch {
        state.dataset.state = 'disconnected';
        label.textContent = '服务异常';
    }
}

async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        document.getElementById('stat-success').textContent = data.total_translated || 0;
        document.getElementById('stat-failed').textContent = data.total_failed || 0;
        document.getElementById('stat-progress').textContent = data.in_progress || 0;
        document.getElementById('stat-uptime').textContent = formatUptime(data.start_time);
    } catch (error) {
        console.error('更新统计失败:', error);
    }
}

async function updateTranslationProgress() {
    try {
        const data = await (await apiFetch('/api/translation-logs')).json();
        const container = document.getElementById('translation-progress-list');
        if (!data.length) {
            container.innerHTML = emptyState('暂无翻译任务');
            return;
        }

        container.innerHTML = data.map(log => {
            const statusClass = {
                success: 'success',
                failed: 'error',
                skipped: 'error'
            }[log.status] || 'progress';
            const progress = Math.min(100, Math.max(0, Number(log.progress) || 0));
            return `
                <article class="translation-log-item">
                    <div class="translation-file-row">
                        <span class="task-status-dot status-${statusClass}" aria-hidden="true"></span>
                        <div class="translation-file-name" title="${escapeHtml(fileNameFromPath(log.file_path))}">${escapeHtml(fileNameFromPath(log.file_path))}</div>
                    </div>
                    <div class="translation-status-row">
                        <span class="status-badge status-${statusClass}">${escapeHtml(log.status)}</span>
                        <div class="translation-progress-bar" role="progressbar" aria-label="${escapeHtml(fileNameFromPath(log.file_path))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}">
                            <div class="translation-progress-fill ${statusClass}" style="width: ${progress}%"></div>
                        </div>
                        <span class="translation-percent">${progress}%</span>
                    </div>
                    <div class="translation-message">${escapeHtml(log.message)}</div>
                    <div class="translation-time">${getTimeDiff(log.updated_at)}</div>
                </article>
            `;
        }).join('');
    } catch (error) {
        console.error('更新翻译进度失败:', error);
    }
}

async function updateTranslationContent() {
    try {
        const data = await (await apiFetch('/api/translation-content-logs')).json();
        const container = document.getElementById('translation-content-list');
        if (!data.length) {
            lastContentSignature = '0';
            container.innerHTML = emptyState('暂无翻译内容');
            return;
        }

        const signature = `${data.length}:${data[0]?.timestamp || ''}:${data[0]?.translated || ''}`;
        if (signature === lastContentSignature) return;
        lastContentSignature = signature;
        const wasAtTop = container.scrollTop <= 50;

        container.innerHTML = data.map(log => `
            <article class="content-log-item">
                <div class="content-log-header">
                    <div class="content-log-file" title="${escapeHtml(fileNameFromPath(log.file_path))}">${escapeHtml(fileNameFromPath(log.file_path))}</div>
                    <time class="content-log-time">${getTimeDiff(log.timestamp)}</time>
                </div>
                <div class="content-log-text">
                    <div class="content-log-label">原文</div>
                    <div class="content-log-content content-log-original">${escapeHtml(log.original)}</div>
                </div>
                <div class="content-log-text">
                    <div class="content-log-label">译文</div>
                    <div class="content-log-content content-log-translated">${escapeHtml(log.translated)}</div>
                </div>
            </article>
        `).join('');

        if (wasAtTop) container.scrollTop = 0;
    } catch (error) {
        console.error('更新翻译内容失败:', error);
    }
}

async function updateLogs() {
    try {
        const data = await (await apiFetch('/api/logs?limit=200')).json();
        const container = document.getElementById('log-list');
        if (!data.length) {
            container.innerHTML = emptyState('暂无系统日志');
            return;
        }

        const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
        container.innerHTML = data.map(log => {
            const levelClass = ['DEBUG', 'INFO', 'WARNING', 'ERROR'].includes(log.level) ? log.level : 'INFO';
            const timestamp = new Date(log.timestamp);
            const displayTime = Number.isNaN(timestamp.getTime()) ? '时间未知' : timestamp.toLocaleString('zh-CN');
            return `
                <div class="log-item">
                    <span class="log-level ${levelClass}">${escapeHtml(log.level)}</span>
                    <time class="log-time">${displayTime}</time>
                    <span class="log-message">${escapeHtml(log.message)}</span>
                </div>
            `;
        }).join('');
        if (wasAtBottom) container.scrollTop = container.scrollHeight;
    } catch (error) {
        console.error('更新系统日志失败:', error);
    }
}

async function loadConfig() {
    try {
        const data = await (await apiFetch('/api/config')).json();
        Object.entries(data).forEach(([key, value]) => {
            const input = document.getElementById(key.toLowerCase().replaceAll('_', '-'));
            if (input) input.value = value || '';
        });
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

function showConfigAlert(type, message) {
    const alert = document.getElementById('config-alert');
    alert.className = `alert ${type}`;
    alert.textContent = message;
    alert.style.display = 'block';
    window.setTimeout(() => {
        alert.style.display = 'none';
    }, 5000);
}

async function saveConfig(event) {
    event.preventDefault();
    const config = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
        const data = await (await apiFetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        })).json();
        showConfigAlert(data.success ? 'success' : 'error', data.message || data.error || '请求失败');
    } catch (error) {
        showConfigAlert('error', `保存失败: ${error.message}`);
    }
}

function bindEvents() {
    const modal = document.getElementById('config-modal');
    document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
    document.getElementById('config-button').addEventListener('click', openConfigModal);
    document.getElementById('close-config-button').addEventListener('click', closeConfigModal);
    document.getElementById('cancel-config-button').addEventListener('click', closeConfigModal);
    document.getElementById('config-form').addEventListener('submit', saveConfig);
    modal.addEventListener('click', event => {
        if (event.target === modal) closeConfigModal();
    });
    modal.addEventListener('keydown', keepFocusInModal);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && modal.classList.contains('active')) closeConfigModal();
    });
}

function initialize() {
    bindEvents();
    setTheme(document.documentElement.dataset.theme || 'light');
    updateConnectionStatus();
    updateStats();
    updateTranslationProgress();
    updateTranslationContent();
    updateLogs();
    loadConfig();
    window.setTimeout(() => {
        const logs = document.getElementById('log-list');
        logs.scrollTop = logs.scrollHeight;
    }, 500);
    window.setInterval(updateStats, 2000);
    window.setInterval(updateTranslationProgress, 2500);
    window.setInterval(updateTranslationContent, 2000);
    window.setInterval(updateLogs, 3000);
    window.setInterval(updateConnectionStatus, 10000);
}

initialize();
