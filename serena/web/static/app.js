/* ────────────────────────────────────────────────────────────
   SERENA web — frontend
   ──────────────────────────────────────────────────────────── */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const ACTION_LABELS_BY_LANG = {
    en: { NORMAL: 'Normal', ALERT: 'Alert', BLOCK: 'Restricted', EMERGENCY: 'Emergency' },
    fr: { NORMAL: 'Normal', ALERT: 'Vigilance', BLOCK: 'Restreint', EMERGENCY: 'Urgence' },
};
const ACTION_LABELS = new Proxy({}, {
    get: (_t, k) => (ACTION_LABELS_BY_LANG[state?.lang || 'en'] || ACTION_LABELS_BY_LANG.en)[k],
});
const ACTION_BADGE = {
    NORMAL: 'badge-normal',
    ALERT: 'badge-alert',
    BLOCK: 'badge-block',
    EMERGENCY: 'badge-emergency',
};

const LANG = {
    en: {
        placeholder: "Send a message...",
        compare: "Compare",
        with_serena: "WITH SERENA",
        without_serena: "WITHOUT SERENA",
        analyzing: "SERENA is analyzing...",
        analyzing_short: "Working...",
        crisis: "Crisis detected. Please call",
        score: "Score",
        signals_one: "signal",
        signals_many: "signals",
        welcome_title: "Talk to AI. Safely.",
        welcome_sub: "A conversational AI with real-time psychiatric safety.",
        hint: "SERENA can make mistakes. Verify important information.",
        sug_advice: "I need advice",
        sug_idea: "I have a project idea",
        sug_write: "Help me write",
        sug_chat: "Let's chat",
        no_signals: "None",
        no_signals_detected: "No signal detected.",
        tagline: "Safe AI for mental health",
        new_chat: "New chat",
        conversations: "Conversations",
        dashboard: "SERENA Dashboard",
        switch_mode: "Switch mode",
        profile: "User profile",
        reset_profile: "Reset profile",
        export: "Export session",
        theme: "Theme (Dark / Light)",
        about: "About",
        language: "Language",
        user_view: "User view",
        user_desc: "Protected conversation",
        admin_desc: "Dashboard + Comparison",
        admin_code: "Admin code",
        enter: "Enter",
        invalid_code: "Invalid code",
        rename_prompt: "New title:",
        reset_title: "Reset profile and all detection state?",
        reset_body: "Profile, learned signals, and all conversation detection memory will be cleared. Message history is kept.",
        reset_done: "Profile and memory cleared.",
        blocked_one: "validation blocked",
        blocked_many: "validations blocked",
        risky_one: "risky term",
        risky_many: "risky terms",
        streaming_now: "— in progress —",
        turn: "Turn",
        raw_gemma: "Raw Gemma",
        path_validations: "pathological validations detected",
        preparing: "Preparing response...",
        stopped: "stopped",
    },
    fr: {
        placeholder: "Envoyer un message...",
        compare: "Comparer",
        with_serena: "AVEC SERENA",
        without_serena: "SANS SERENA",
        analyzing: "SERENA analyse...",
        analyzing_short: "En cours...",
        crisis: "Crise détectée. Appelez le",
        score: "Score",
        signals_one: "signal",
        signals_many: "signaux",
        welcome_title: "Parlez à l'IA. En sécurité.",
        welcome_sub: "Une IA conversationnelle avec classification psychiatrique en temps réel.",
        hint: "SERENA peut faire des erreurs. Vérifiez les informations importantes.",
        sug_advice: "J'ai besoin de conseils",
        sug_idea: "J'ai une idée de projet",
        sug_write: "Aide-moi à rédiger",
        sug_chat: "Discutons librement",
        no_signals: "Aucun",
        no_signals_detected: "Aucun signal détecté.",
        tagline: "L'IA sécurisée pour la santé mentale",
        new_chat: "Nouvelle conversation",
        conversations: "Conversations",
        dashboard: "Tableau de bord SERENA",
        switch_mode: "Changer de mode",
        profile: "Profil utilisateur",
        reset_profile: "Réinitialiser le profil",
        export: "Exporter la session",
        theme: "Thème (Sombre / Clair)",
        about: "À propos",
        language: "Langue",
        user_view: "Vue utilisateur",
        user_desc: "Conversation protégée",
        admin_desc: "Tableau de bord + Comparaison",
        admin_code: "Code admin",
        enter: "Entrer",
        invalid_code: "Code invalide",
        rename_prompt: "Nouveau titre :",
        reset_title: "Réinitialiser le profil et l'état de détection ?",
        reset_body: "Le profil, les signaux appris et la mémoire de détection de toutes les conversations seront effacés. L'historique des messages est conservé.",
        reset_done: "Profil et mémoire effacés.",
        blocked_one: "validation bloquée",
        blocked_many: "validations bloquées",
        risky_one: "terme risqué",
        risky_many: "termes risqués",
        streaming_now: "— en cours —",
        turn: "Tour",
        raw_gemma: "Gemma brut",
        path_validations: "validations pathologiques détectées",
        preparing: "Préparation de la réponse...",
        stopped: "interrompu",
    },
};

const LS_KEYS = {
    MODE: 'serena.mode',          // 'user' | 'admin'
    ADMIN_OK: 'serena.adminOk',   // 'true' if admin code passed
    THEME: 'serena.theme',        // 'dark' | 'light'
    LANG: 'serena.lang',          // 'en' | 'fr'
};

function t(key) {
    return (LANG[state.lang] || LANG.en)[key] || key;
}

const LEGACY_UNTITLED = new Set([
    "", "Nouvelle conversation", "New chat", "Sans titre", "Untitled",
]);
function displayTitle(raw) {
    if (!raw || LEGACY_UNTITLED.has(raw.trim())) return t('new_chat');
    return raw;
}

const state = {
    mode: 'user',                 // 'user' | 'admin'
    lang: 'en',                   // 'en' | 'fr'
    compareMode: false,
    activeId: null,
    activeMode: null,             // mode of the loaded conversation
    conversations: [],
    messages: [],
    sending: false,
    cancelled: false,
    ws: null,
    wsRetry: 0,
    sidebarOpen: false,
    sidebarCollapsed: false,
    barCollapsed: false,
    autoScroll: true,
    lastSnapshot: null,
    lastDebug: null,
    emergencyDismissed: false,
};

// Server-mirrored danger terms — used for client-side fallback highlight
const DANGER_TERMS = [
    "incredible energy", "i believe in you", "you're right", "great idea",
    "sounds exciting", "trust your instincts", "here's a plan", "here's your",
    "step 1", "step 2", "step 3", "unique experience", "gift", "profound",
    "destiny", "spiritual", "vision", "build an empire", "amazing idea",
    "fantastic", "go for it", "you can do it",
    "énergie incroyable", "je crois en", "bonne idée", "vous avez raison",
    "tu as raison", "foncez", "bravo", "génial", "fantastique", "extraordinaire",
    "votre vision", "ta vision", "lance-toi", "lancez-vous", "n'hésitez pas",
    "vous êtes capable", "tu es capable",
];

// ────── Mode / theme persistence ──────
function applyMode(mode) {
    state.mode = mode;
    document.body.dataset.mode = mode;
}
function applyTheme(theme) {
    document.body.classList.toggle('light-theme', theme === 'light');
}

function applyLang(lang) {
    if (!LANG[lang]) lang = 'en';
    state.lang = lang;
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        const val = t(key);
        // crisis_full contains HTML — re-render preserving nested elements
        if (key === 'crisis_full') return;
        el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    // Refresh dynamic bits from last snapshot + conv list (untitled rename)
    if (state.lastSnapshot) updateSerenaUI(state.lastSnapshot, false);
    if (state.conversations.length) renderConversations();
    const sel = document.getElementById('langSelect');
    if (sel && sel.value !== lang) sel.value = lang;
}

function getInitialMode() {
    const saved = localStorage.getItem(LS_KEYS.MODE);
    if (saved === 'admin' && localStorage.getItem(LS_KEYS.ADMIN_OK) === 'true') return 'admin';
    if (saved === 'user') return 'user';
    return null; // unset → show selection
}

// ────── WebSocket ──────
function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws`;
    const ws = new WebSocket(url);

    ws.addEventListener('open', () => {
        state.wsRetry = 0;
        $('#reconnectBanner').hidden = true;
    });
    ws.addEventListener('close', () => {
        state.ws = null;
        $('#reconnectBanner').hidden = false;
        const delay = Math.min(8000, 800 * Math.pow(2, state.wsRetry++));
        setTimeout(connectWS, delay);
    });
    ws.addEventListener('error', () => ws.close());
    ws.addEventListener('message', (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        handleWsMessage(msg);
    });

    state.ws = ws;
}

function handleWsMessage(msg) {
    // After user cancel, discard mid-flight stream events. Allow only
    // conversation_created (cid bookkeeping) and error (so user sees issues).
    if (state.cancelled) {
        const passthrough = new Set(['conversation_created', 'error']);
        const streamy = new Set([
            'thinking', 'typing',
            'stream_start', 'stream_token', 'stream_end',
            'comparison_stream_start', 'comparison_stream_token', 'comparison_stream_end',
            'response', 'comparison_response',
        ]);
        if (streamy.has(msg.type)) return;
        if (!passthrough.has(msg.type)) return;
    }
    switch (msg.type) {
        case 'thinking':
            showTyping(t('analyzing'));
            break;
        case 'typing':
            if (msg.status === 'analyzing') showTyping(t('analyzing'));
            else if (msg.status === 'preparing') showTyping(t('preparing'));
            break;
        case 'stream_start':
            removeTyping();
            startStreamingBubble(msg);
            break;
        case 'stream_token':
            appendStreamToken(msg.token);
            break;
        case 'stream_end':
            finishStreamingBubble(msg);
            break;
        case 'comparison_stream_start':
            removeCompTyping();
            startComparisonStream(msg);
            break;
        case 'comparison_stream_token':
            appendComparisonToken(msg.source, msg.token);
            break;
        case 'comparison_stream_end':
            finishComparisonStream(msg);
            break;
        case 'response':
            // Legacy non-streaming path (kept for safety)
            removeTyping();
            handleResponse(msg);
            break;
        case 'comparison_response':
            removeCompTyping();
            handleComparisonResponse(msg);
            break;
        case 'conversation_created':
            state.activeId = msg.conversation_id;
            break;
        case 'error':
            removeTyping();
            removeCompTyping();
            cancelStream();
            appendErrorBubble(msg.message);
            state.sending = false;
            updateSendBtn();
            break;
    }
}

function sendMessage(content) {
    content = (content || '').trim();
    if (!content || state.sending) return;
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        appendErrorBubble('Connexion perdue.');
        return;
    }
    state.sending = true;
    state.cancelled = false;
    updateSendBtn();

    if (state.compareMode) {
        appendCompUserBubble(content);
        showCompTyping();
        state.ws.send(JSON.stringify({
            type: 'comparison_message',
            content,
            conversation_id: state.activeId,
        }));
    } else {
        appendUserBubble(content);
        state.messages.push({ role: 'user', content });
        hideWelcome();
        state.ws.send(JSON.stringify({
            type: 'message',
            content,
            conversation_id: state.activeId,
            mode: state.mode,
        }));
    }
}

// ────── API ──────
async function api(path, opts = {}) {
    const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `${res.status}`);
    }
    return res.json();
}

async function loadConversations() {
    state.conversations = await api('/api/conversations');
    renderConversations();
}

async function createConversation(forceMode) {
    const mode = forceMode || (state.compareMode ? 'comparison' : state.mode);
    const conv = await api('/api/conversations/new', {
        method: 'POST',
        body: JSON.stringify({ mode }),
    });
    state.activeId = conv.id;
    state.activeMode = mode;
    state.messages = [];
    state.lastSnapshot = null;
    state.lastDebug = null;
    state.emergencyDismissed = false;
    await loadConversations();
    if (state.compareMode) {
        clearComparison();
    } else {
        renderMessages();
        showWelcome();
    }
    resetSerenaUI();
    hideEmergencyBanner();
}

async function loadConversation(id) {
    const conv = await api(`/api/conversations/${id}`);
    state.activeId = conv.id;
    state.activeMode = conv.mode || 'user';
    state.messages = conv.messages || [];
    state.lastSnapshot = null;
    state.lastDebug = null;
    state.emergencyDismissed = false;

    // Comparison-saved conversation → enter comparison mode (admin only & desktop)
    if (state.activeMode === 'comparison') {
        if (state.mode !== 'admin' || window.innerWidth <= 1024) {
            // gracefully fall back: render as normal
            setCompareMode(false);
            renderMessages();
        } else {
            setCompareMode(true);
            renderComparisonHistory();
        }
    } else {
        if (state.compareMode) setCompareMode(false);
        renderMessages();
    }

    if (state.messages.length === 0) {
        showWelcome();
        resetSerenaUI();
    } else {
        hideWelcome();
        const lastAssistant = [...state.messages].reverse().find(m => m.role === 'assistant');
        if (lastAssistant) {
            updateSerenaUI({
                score: lastAssistant.score ?? conv.final_score ?? 0,
                action: lastAssistant.action ?? conv.final_action ?? 'NORMAL',
                signals: lastAssistant.signals ?? {},
                score_history: state.messages.filter(m => m.role === 'assistant').map(m => m.score ?? 0),
                probable_condition: '',
                confidence: 0,
            }, false);
            maybeShowEmergencyBanner(lastAssistant.action);
        }
    }
    closeSidebarMobile();
    renderConversations();
}

async function deleteConversation(id) {
    await api(`/api/conversations/${id}`, { method: 'DELETE' });
    state.conversations = state.conversations.filter(c => c.id !== id);
    if (state.activeId === id) {
        const next = state.conversations[0];
        if (next) await loadConversation(next.id);
        else await createConversation();
    }
    renderConversations();
}

async function renameConversation(id, title) {
    const conv = await api(`/api/conversations/${id}/rename`, {
        method: 'POST',
        body: JSON.stringify({ title }),
    });
    const i = state.conversations.findIndex(c => c.id === id);
    if (i >= 0) state.conversations[i].title = conv.title;
    renderConversations();
}

// ────── Render conversations list ──────
function renderConversations() {
    const root = $('#conversationsList');
    root.innerHTML = '';
    for (const c of state.conversations) {
        const el = document.createElement('div');
        el.className = 'conv-item' + (c.id === state.activeId ? ' active' : '');
        el.dataset.id = c.id;
        const modeTag = c.mode === 'comparison'
            ? '<span class="conv-mode compare">CMP</span>'
            : (c.mode === 'admin' && state.mode === 'admin'
                ? '<span class="conv-mode">ADM</span>' : '');
        el.innerHTML = `
            <span class="conv-title">${modeTag}<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(displayTitle(c.title))}</span></span>
            <span class="conv-date">${formatDate(c.updated_at)}</span>
            <div class="conv-actions">
                <button class="conv-action" data-act="rename" aria-label="Renommer" title="Renommer">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 20h9"/>
                        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/>
                    </svg>
                </button>
                <button class="conv-action danger" data-act="delete" aria-label="Supprimer" title="Supprimer">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        <path d="M10 11v6M14 11v6"/>
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                    </svg>
                </button>
            </div>
        `;
        el.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('.conv-action');
            if (actionBtn) {
                e.stopPropagation();
                handleConvAction(actionBtn.dataset.act, c, el);
                return;
            }
            loadConversation(c.id);
        });
        root.appendChild(el);
    }
}

function handleConvAction(act, conv, itemEl) {
    if (act === 'rename') {
        const newTitle = prompt(t('rename_prompt'), displayTitle(conv.title));
        if (newTitle && newTitle.trim()) renameConversation(conv.id, newTitle.trim());
    } else if (act === 'delete') {
        confirmDialog(
            'Supprimer cette conversation ?',
            'Cette action est irréversible.',
            () => {
                itemEl.classList.add('conv-leaving');
                setTimeout(() => deleteConversation(conv.id), 280);
            }
        );
    }
}

// ────── Render messages (single-pane) ──────
function renderMessages() {
    const root = $('#messages');
    root.innerHTML = '';
    if (state.messages.length === 0) {
        root.appendChild(welcomeNode());
        return;
    }
    for (const m of state.messages) {
        if (m.role === 'user') {
            root.appendChild(userNode(m.content));
        } else if (m.role === 'assistant') {
            root.appendChild(assistantNode(m.content));
            if (state.mode === 'admin' && typeof m.score === 'number') {
                root.appendChild(scoreInlineNode(m.score, m.action));
            }
        }
    }
    scrollToBottom(true);
}

function welcomeNode() {
    const tpl = `
        <div class="welcome" id="welcome">
            <img src="/static/assets/serena-logo.svg" width="64" height="64" alt="">
            <h1 data-i18n="welcome_title">${t('welcome_title')}</h1>
            <div data-i18n="welcome_sub" class="welcome-sub">${t('welcome_sub')}</div>
            <div class="suggestions">
                <button class="suggestion" data-prompt-en="I need advice on a personal project" data-prompt-fr="J'ai besoin de conseils sur un projet personnel"><span class="emoji">💡</span><span data-i18n="sug_advice">${t('sug_advice')}</span></button>
                <button class="suggestion" data-prompt-en="I have a project idea, can you help me develop it?" data-prompt-fr="J'ai une idée de projet, peux-tu m'aider à la développer ?"><span class="emoji">🧠</span><span data-i18n="sug_idea">${t('sug_idea')}</span></button>
                <button class="suggestion" data-prompt-en="Help me write a clear, structured text" data-prompt-fr="Aide-moi à rédiger un texte clair et structuré"><span class="emoji">📝</span><span data-i18n="sug_write">${t('sug_write')}</span></button>
                <button class="suggestion" data-prompt-en="I just want to chat" data-prompt-fr="Je veux juste discuter"><span class="emoji">💬</span><span data-i18n="sug_chat">${t('sug_chat')}</span></button>
            </div>
        </div>`;
    const wrap = document.createElement('div');
    wrap.innerHTML = tpl;
    const node = wrap.firstElementChild;
    node.querySelectorAll('.suggestion').forEach(b => {
        b.addEventListener('click', () => {
            const prompt = b.dataset[`prompt${state.lang.charAt(0).toUpperCase() + state.lang.slice(1)}`] || b.dataset.prompt;
            $('#input').value = prompt;
            sendMessage(prompt);
        });
    });
    return node;
}

function userNode(content) {
    const el = document.createElement('div');
    el.className = 'message user';
    el.innerHTML = `<div class="bubble">${escapeHtml(content)}</div>`;
    return el;
}

function assistantNode(content, opts = {}) {
    const el = document.createElement('div');
    el.className = 'message assistant';
    const html = opts.highlightDanger
        ? renderMarkdownWithDanger(content)
        : renderMarkdown(content);
    el.innerHTML = `
        <img class="avatar" src="/static/assets/serena-logo.svg" alt="">
        <div class="bubble">${html}</div>
    `;
    return el;
}

function scoreInlineNode(score, action) {
    const cls = (action || 'NORMAL').toLowerCase();
    const el = document.createElement('div');
    el.className = `score-inline ${cls}`;
    el.innerHTML = `
        <div class="score-inline-line"></div>
        <span class="dot"></span>
        <span>Score ${(+score).toFixed(2)} · ${ACTION_LABELS[action] || action}</span>
        <div class="score-inline-line"></div>
    `;
    return el;
}

function blockedNoteNode(count) {
    const el = document.createElement('div');
    el.className = 'blocked-note';
    el.textContent = `🛡️ ${count} ${count > 1 ? t('blocked_many') : t('blocked_one')}`;
    return el;
}

function appendUserBubble(content) {
    hideWelcome();
    $('#messages').appendChild(userNode(content));
    scrollToBottom();
}

function appendAssistantBubble(content) {
    $('#messages').appendChild(assistantNode(content));
    scrollToBottom();
}

function appendScoreInline(score, action) {
    $('#messages').appendChild(scoreInlineNode(score, action));
    scrollToBottom();
}

function appendErrorBubble(text) {
    const el = document.createElement('div');
    el.className = 'message assistant';
    el.innerHTML = `
        <img class="avatar" src="/static/assets/serena-logo.svg" alt="">
        <div class="bubble" style="color:var(--status-block);">⚠ ${escapeHtml(text)}</div>
    `;
    $('#messages').appendChild(el);
    scrollToBottom();
}

function showTyping(label) {
    let typingEl = $('#typing');
    const text = label || (state.mode === 'admin' ? t('analyzing') : t('analyzing_short'));
    if (typingEl) {
        const lab = typingEl.querySelector('.typing-label');
        if (lab) lab.textContent = text;
        return;
    }
    const el = document.createElement('div');
    el.className = 'typing';
    el.id = 'typing';
    el.innerHTML = `
        <div class="typing-dots"><span></span><span></span><span></span></div>
        <span class="typing-label">${text}</span>
    `;
    $('#messages').appendChild(el);
    scrollToBottom();
}
function removeTyping() {
    const el = $('#typing');
    if (el) el.remove();
}

function handleResponse(msg) {
    appendAssistantBubble(msg.content);
    if (state.mode === 'admin') {
        appendScoreInline(msg.score, msg.action);
    }

    state.messages.push({
        role: 'assistant',
        content: msg.content,
        score: msg.score,
        action: msg.action,
        signals: msg.signals,
    });

    updateSerenaUI(msg, true);
    updateDebugPane(msg);
    maybeShowEmergencyBanner(msg.action);

    const i = state.conversations.findIndex(c => c.id === state.activeId);
    if (i >= 0) {
        state.conversations[i].title = msg.title || state.conversations[i].title;
        state.conversations[i].final_score = msg.score;
        state.conversations[i].final_action = msg.action;
        state.conversations[i].updated_at = new Date().toISOString();
        const [item] = state.conversations.splice(i, 1);
        state.conversations.unshift(item);
        renderConversations();
    } else {
        loadConversations();
    }

    state.sending = false;
    updateSendBtn();
}

// ────── Comparison view ──────
function clearComparison() {
    $('#compSerenaStream').innerHTML = '';
    $('#compRawStream').innerHTML = '';
    $('#compSerenaMeta').textContent = '';
    $('#compRawMeta').textContent = '';
    $('#compSummary').hidden = true;
    $('#compSummary').textContent = '';
}

function renderComparisonHistory() {
    clearComparison();
    let turn = 0;
    for (const m of state.messages) {
        if (m.role === 'user') {
            turn++;
            appendCompUserBubble(m.content, /*skipScroll=*/true);
        } else if (m.role === 'assistant') {
            const serenaPane = $('#compSerenaStream');
            serenaPane.appendChild(assistantNode(m.content));
            if (typeof m.score === 'number') {
                serenaPane.appendChild(scoreInlineNode(m.score, m.action));
            }
            if (m.blocked_count) {
                serenaPane.appendChild(blockedNoteNode(m.blocked_count));
            }
            const rawPane = $('#compRawStream');
            const rawNode = assistantNode(m.raw_content || '', { highlightDanger: true });
            rawPane.appendChild(rawNode);
        }
    }
    requestAnimationFrame(() => {
        $('#compSerenaStream').scrollTop = $('#compSerenaStream').scrollHeight;
        $('#compRawStream').scrollTop = $('#compRawStream').scrollHeight;
    });
}

function appendCompUserBubble(content, skipScroll = false) {
    hideWelcome();
    $('#compSerenaStream').appendChild(userNode(content));
    $('#compRawStream').appendChild(userNode(content));
    if (!skipScroll) {
        $('#compSerenaStream').scrollTop = $('#compSerenaStream').scrollHeight;
        $('#compRawStream').scrollTop = $('#compRawStream').scrollHeight;
    }
}

function showCompTyping() {
    for (const id of ['compSerenaStream', 'compRawStream']) {
        const root = document.getElementById(id);
        if (root.querySelector('.typing.comp')) continue;
        const el = document.createElement('div');
        el.className = 'typing comp';
        el.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div><span class="typing-label">Génération…</span>`;
        root.appendChild(el);
        root.scrollTop = root.scrollHeight;
    }
}
function removeCompTyping() {
    document.querySelectorAll('.typing.comp').forEach(n => n.remove());
}

// ─── Streaming bubbles (single-pane) ───
const stream = {
    active: false,
    text: '',
    bubbleEl: null,
    bubbleInner: null,   // .bubble inside bubbleEl
    startMeta: null,
};

function startStreamingBubble(msg) {
    stream.active = true;
    stream.text = '';
    stream.startMeta = msg;

    const node = document.createElement('div');
    node.className = 'message assistant streaming';
    node.innerHTML = `
        <img class="avatar" src="/static/assets/serena-logo.svg" alt="">
        <div class="bubble"><span class="streaming-cursor">▊</span></div>
    `;
    $('#messages').appendChild(node);
    stream.bubbleEl = node;
    stream.bubbleInner = node.querySelector('.bubble');

    // Update gauge early (admin)
    if (state.mode === 'admin') {
        updateSerenaUI({
            score: msg.score ?? 0,
            action: msg.action || 'NORMAL',
            signals: msg.signals || {},
            score_history: state.lastSnapshot?.score_history ?? [],
            probable_condition: '',
            confidence: 0,
        }, true);
    }
    maybeShowEmergencyBanner(msg.action);
    scrollToBottom();
}

function appendStreamToken(token) {
    if (!stream.active || !stream.bubbleInner) return;
    stream.text += token;
    stream.bubbleInner.innerHTML =
        renderMarkdown(stream.text) + '<span class="streaming-cursor">▊</span>';
    if (state.autoScroll) scrollToBottom();
}

function finishStreamingBubble(msg) {
    if (!stream.active || !stream.bubbleInner) return;
    const finalText = msg.full_response || stream.text;
    stream.bubbleInner.innerHTML = renderMarkdown(finalText);
    stream.bubbleEl.classList.remove('streaming');

    // Append inline score (admin)
    if (state.mode === 'admin' && typeof msg.score === 'number') {
        const inline = scoreInlineNode(msg.score, msg.action);
        $('#messages').appendChild(inline);
    }

    // Persist into state.messages
    state.messages.push({
        role: 'assistant',
        content: finalText,
        score: msg.score,
        action: msg.action,
        signals: msg.signals,
    });

    // Final UI update
    updateSerenaUI(msg, true);
    updateDebugPane(msg);
    maybeShowEmergencyBanner(msg.action);

    // Sidebar
    const i = state.conversations.findIndex(c => c.id === state.activeId);
    if (i >= 0) {
        state.conversations[i].title = msg.title || state.conversations[i].title;
        state.conversations[i].final_score = msg.score;
        state.conversations[i].final_action = msg.action;
        state.conversations[i].updated_at = new Date().toISOString();
        const [item] = state.conversations.splice(i, 1);
        state.conversations.unshift(item);
        renderConversations();
    } else {
        loadConversations();
    }

    cancelStream();
    state.sending = false;
    updateSendBtn();
}

function cancelStream() {
    if (stream.bubbleEl) {
        stream.bubbleEl.classList.remove('streaming');
        const c = stream.bubbleInner?.querySelector('.streaming-cursor');
        if (c) c.remove();
    }
    stream.active = false;
    stream.text = '';
    stream.bubbleEl = null;
    stream.bubbleInner = null;
    stream.startMeta = null;
}

// ─── Streaming bubbles (comparison) ───
const compStream = {
    active: false,
    serenaText: '', rawText: '',
    serenaInner: null, rawInner: null,
    serenaEl: null, rawEl: null,
    startMeta: null,
};

function startComparisonStream(msg) {
    compStream.active = true;
    compStream.serenaText = '';
    compStream.rawText = '';
    compStream.startMeta = msg;

    const buildSide = () => {
        const wrap = document.createElement('div');
        wrap.className = 'message assistant streaming';
        wrap.innerHTML = `<div class="bubble"><span class="streaming-cursor">▊</span></div>`;
        return wrap;
    };
    const sNode = buildSide();
    const rNode = buildSide();
    $('#compSerenaStream').appendChild(sNode);
    $('#compRawStream').appendChild(rNode);

    compStream.serenaEl = sNode;
    compStream.rawEl = rNode;
    compStream.serenaInner = sNode.querySelector('.bubble');
    compStream.rawInner = rNode.querySelector('.bubble');

    // Headers preview
    $('#compSerenaMeta').textContent = `Score ${(+(msg.score ?? 0)).toFixed(2)} · ${ACTION_LABELS[msg.action] || msg.action}`;
    $('#compRawMeta').textContent = t('streaming_now');

    if (state.mode === 'admin') {
        updateSerenaUI({
            score: msg.score ?? 0,
            action: msg.action || 'NORMAL',
            signals: msg.signals || {},
            score_history: state.lastSnapshot?.score_history ?? [],
            probable_condition: '',
            confidence: 0,
        }, true);
    }

    [$('#compSerenaStream'), $('#compRawStream')].forEach(p => { p.scrollTop = p.scrollHeight; });
}

function appendComparisonToken(source, token) {
    if (!compStream.active) return;
    if (source === 'serena' && compStream.serenaInner) {
        compStream.serenaText += token;
        compStream.serenaInner.innerHTML =
            renderMarkdown(compStream.serenaText) + '<span class="streaming-cursor">▊</span>';
        $('#compSerenaStream').scrollTop = $('#compSerenaStream').scrollHeight;
    } else if (source === 'raw' && compStream.rawInner) {
        compStream.rawText += token;
        // Live highlight as we go
        compStream.rawInner.innerHTML =
            renderMarkdownWithDanger(compStream.rawText) + '<span class="streaming-cursor">▊</span>';
        $('#compRawStream').scrollTop = $('#compRawStream').scrollHeight;
    }
}

function finishComparisonStream(msg) {
    if (!compStream.active) return;

    const sFinal = msg.serena?.content || compStream.serenaText;
    const rFinal = msg.raw?.content || compStream.rawText;
    const danger = msg.raw?.danger_terms_found || [];

    if (compStream.serenaInner) compStream.serenaInner.innerHTML = renderMarkdown(sFinal);
    if (compStream.rawInner) compStream.rawInner.innerHTML = renderMarkdownWithDanger(rFinal);
    compStream.serenaEl?.classList.remove('streaming');
    compStream.rawEl?.classList.remove('streaming');

    // Append score inline + blocked note under SERENA bubble
    const sPane = $('#compSerenaStream');
    if (typeof msg.serena?.score === 'number') {
        sPane.appendChild(scoreInlineNode(msg.serena.score, msg.serena.action));
    }
    if (msg.serena?.blocked_count) {
        sPane.appendChild(blockedNoteNode(msg.serena.blocked_count));
    }
    sPane.scrollTop = sPane.scrollHeight;
    $('#compRawStream').scrollTop = $('#compRawStream').scrollHeight;

    // Headers + summary
    const turn = state.messages.filter(m => m.role === 'user').length + 1;
    $('#compSerenaMeta').textContent = `Score ${(+msg.serena.score).toFixed(2)} · ${ACTION_LABELS[msg.serena.action] || msg.serena.action}`;
    $('#compRawMeta').textContent = `${danger.length} ${danger.length > 1 ? t('risky_many') : t('risky_one')}`;
    const sum = $('#compSummary');
    sum.hidden = false;
    sum.innerHTML = `
        📊 ${t('turn')} ${turn} ·
        <b>SERENA</b> Score ${(+msg.serena.score).toFixed(2)} ${ACTION_LABELS[msg.serena.action] || msg.serena.action} ·
        <b>${t('raw_gemma')}</b> ${danger.length} ${t('path_validations')}
    `;

    // Persist
    state.messages.push({
        role: 'assistant',
        content: sFinal,
        raw_content: rFinal,
        score: msg.serena.score,
        action: msg.serena.action,
        signals: msg.serena.signals,
        danger_terms_in_raw: danger,
        blocked_count: msg.serena.blocked_count,
    });

    updateSerenaUI(msg.serena, true);
    updateDebugPane(msg.serena);
    maybeShowEmergencyBanner(msg.serena.action);

    const i = state.conversations.findIndex(c => c.id === state.activeId);
    if (i >= 0) {
        state.conversations[i].title = msg.title || state.conversations[i].title;
        state.conversations[i].final_score = msg.serena.score;
        state.conversations[i].final_action = msg.serena.action;
        state.conversations[i].updated_at = new Date().toISOString();
        state.conversations[i].mode = 'comparison';
        const [item] = state.conversations.splice(i, 1);
        state.conversations.unshift(item);
        renderConversations();
    } else {
        loadConversations();
    }

    compStream.active = false;
    compStream.serenaInner = null;
    compStream.rawInner = null;
    compStream.serenaEl = null;
    compStream.rawEl = null;
    state.sending = false;
    updateSendBtn();
}

function handleComparisonResponse(msg) {
    state.messages.push({
        role: 'assistant',
        content: msg.serena.content,
        raw_content: msg.raw.content,
        score: msg.serena.score,
        action: msg.serena.action,
        signals: msg.serena.signals,
        danger_terms_in_raw: msg.raw.danger_terms_found,
        blocked_count: msg.serena.blocked_count,
    });

    const sPane = $('#compSerenaStream');
    sPane.appendChild(assistantNode(msg.serena.content));
    sPane.appendChild(scoreInlineNode(msg.serena.score, msg.serena.action));
    if (msg.serena.blocked_count) {
        sPane.appendChild(blockedNoteNode(msg.serena.blocked_count));
    }

    const rPane = $('#compRawStream');
    rPane.appendChild(assistantNode(msg.raw.content, { highlightDanger: true }));

    sPane.scrollTop = sPane.scrollHeight;
    rPane.scrollTop = rPane.scrollHeight;

    // Headers + summary
    const turn = state.messages.filter(m => m.role === 'user').length;
    $('#compSerenaMeta').textContent = `Score ${(+msg.serena.score).toFixed(2)} · ${ACTION_LABELS[msg.serena.action] || msg.serena.action}`;
    const dangerCount = (msg.raw.danger_terms_found || []).length;
    $('#compRawMeta').textContent = `${dangerCount} ${dangerCount > 1 ? t('risky_many') : t('risky_one')}`;
    const sum = $('#compSummary');
    sum.hidden = false;
    sum.innerHTML = `
        📊 ${t('turn')} ${turn} ·
        <b>SERENA</b> Score ${(+msg.serena.score).toFixed(2)} ${ACTION_LABELS[msg.serena.action] || msg.serena.action} ·
        <b>${t('raw_gemma')}</b> ${dangerCount} ${t('path_validations')}
    `;

    updateSerenaUI(msg.serena, true);
    updateDebugPane(msg.serena);
    maybeShowEmergencyBanner(msg.serena.action);

    // Sidebar bookkeeping
    const i = state.conversations.findIndex(c => c.id === state.activeId);
    if (i >= 0) {
        state.conversations[i].title = msg.title || state.conversations[i].title;
        state.conversations[i].final_score = msg.serena.score;
        state.conversations[i].final_action = msg.serena.action;
        state.conversations[i].updated_at = new Date().toISOString();
        state.conversations[i].mode = 'comparison';
        const [item] = state.conversations.splice(i, 1);
        state.conversations.unshift(item);
        renderConversations();
    } else {
        loadConversations();
    }

    state.sending = false;
    updateSendBtn();
}

// ────── SERENA UI ──────
function updateSerenaUI(snap, flash) {
    state.lastSnapshot = snap;
    const score = snap.score ?? 0;
    const action = snap.action || 'NORMAL';
    const signals = snap.signals || {};
    const signalCount = Object.keys(signals).length;

    $('#barFill').style.width = `${Math.min(100, score * 100)}%`;
    $('#barScore').textContent = (+score).toFixed(2);
    setBadge($('#barAction'), action, flash);
    $('#barSignals').textContent = `${signalCount} ${signalCount > 1 ? t('signals_many') : t('signals_one')}`;

    document.getElementById('serenaBar').classList.toggle('emergency', action === 'EMERGENCY');

    $('#dashScore').textContent = (+score).toFixed(2);
    $('#dashScoreFill').style.width = `${Math.min(100, score * 100)}%`;
    setBadge($('#dashAction'), action, flash);
    const turns = snap.score_history?.length ?? state.messages.filter(m => m.role === 'assistant').length;
    $('#dashTurns').textContent = turns;

    const sigList = $('#dashSignals');
    sigList.innerHTML = '';
    if (signalCount === 0) {
        sigList.innerHTML = `<span class="muted">${t('no_signals')}</span>`;
    } else {
        for (const [name, info] of Object.entries(signals)) {
            const chip = document.createElement('span');
            chip.className = 'signal-chip';
            chip.textContent = name;
            chip.title = `Tour ${info.first_seen ?? '?'} · ×${info.count ?? 1}`;
            sigList.appendChild(chip);
        }
    }

    if (snap.probable_condition) {
        $('#dashConditionWrap').hidden = false;
        $('#dashCondition').textContent = `${snap.probable_condition} (${Math.round((snap.confidence ?? 0) * 100)}%)`;
    } else {
        $('#dashConditionWrap').hidden = true;
    }

    drawScoreHistory(snap.score_history || []);
}

function drawScoreHistory(history) {
    const svg = $('#scoreHistory');
    if (!svg) return;
    svg.innerHTML = '';
    if (!history || history.length === 0) return;

    const W = 200, H = 50, P = 4;
    const n = history.length;
    const xStep = n > 1 ? (W - 2 * P) / (n - 1) : 0;

    let pts = history.map((y, i) => {
        const xv = P + i * xStep;
        const yv = H - P - (Math.max(0, Math.min(1, y))) * (H - 2 * P);
        return [xv, yv];
    });
    if (pts.length === 1) {
        pts = [[P, H - P], pts[0], [W - P, pts[0][1]]];
    }

    const lineD = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
    const areaD = `${lineD} L ${pts[pts.length - 1][0].toFixed(1)} ${H - P} L ${pts[0][0].toFixed(1)} ${H - P} Z`;

    const ns = 'http://www.w3.org/2000/svg';
    const area = document.createElementNS(ns, 'path');
    area.setAttribute('d', areaD);
    area.setAttribute('class', 'area');
    svg.appendChild(area);

    const line = document.createElementNS(ns, 'path');
    line.setAttribute('d', lineD);
    line.setAttribute('class', 'line');
    svg.appendChild(line);

    const last = pts[pts.length - 1];
    const dot = document.createElementNS(ns, 'circle');
    dot.setAttribute('cx', last[0]);
    dot.setAttribute('cy', last[1]);
    dot.setAttribute('r', '2.5');
    dot.setAttribute('class', 'dot-marker');
    svg.appendChild(dot);
}

function setBadge(el, action, flash) {
    const cls = ACTION_BADGE[action] || 'badge-normal';
    const prev = el.className;
    el.className = `badge ${cls}`;
    el.textContent = ACTION_LABELS[action] || action;
    if (flash && !prev.includes(cls)) {
        el.classList.add('badge-flash');
        setTimeout(() => el.classList.remove('badge-flash'), 600);
    }
}

function resetSerenaUI() {
    updateSerenaUI({
        score: 0,
        action: 'NORMAL',
        signals: {},
        score_history: [],
        probable_condition: '',
        confidence: 0,
    }, false);
    $('#debugPass1').textContent = '—';
    $('#debugAction').textContent = '—';
    $('#debugTiming').textContent = '—';
    $('#debugPane').hidden = true;
}

function updateDebugPane(snap) {
    if (state.mode !== 'admin') return;
    state.lastDebug = snap;
    $('#debugPane').hidden = false;
    $('#debugPass1').textContent = JSON.stringify(snap.pass1_raw || {}, null, 2);
    $('#debugAction').textContent = `action=${snap.action || '—'} score=${(snap.score ?? 0).toFixed(3)} blocked=${snap.blocked_count ?? 0}`;
    $('#debugTiming').textContent = (snap.elapsed_ms != null) ? `${snap.elapsed_ms} ms` : '—';
}

// ────── Emergency banner ──────
function maybeShowEmergencyBanner(action) {
    if (action === 'EMERGENCY' && !state.emergencyDismissed) {
        $('#emergencyBanner').hidden = false;
    } else if (action !== 'EMERGENCY') {
        // do not auto-hide; only dismiss-clear
    }
}
function hideEmergencyBanner() { $('#emergencyBanner').hidden = true; }

// ────── Helpers ──────
function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function renderMarkdown(text) {
    const escaped = escapeHtml(text);
    let html = escaped.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^\*])\*([^\*\n]+)\*/g, '$1<em>$2</em>');
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/(^|[\s>])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
    html = html.replace(/(^|\n)(\s*[-*]\s.+(?:\n\s*[-*]\s.+)*)/g, (_, pre, block) => {
        const items = block.trim().split(/\n/).map(line => `<li>${line.replace(/^\s*[-*]\s/, '')}</li>`).join('');
        return `${pre}<ul>${items}</ul>`;
    });
    html = html.replace(/(^|\n)(\s*\d+\.\s.+(?:\n\s*\d+\.\s.+)*)/g, (_, pre, block) => {
        const items = block.trim().split(/\n/).map(line => `<li>${line.replace(/^\s*\d+\.\s/, '')}</li>`).join('');
        return `${pre}<ol>${items}</ol>`;
    });
    const blocks = html.split(/\n{2,}/).map(b => {
        if (/^<(ul|ol|pre|blockquote)/.test(b.trim())) return b;
        return `<p>${b.replace(/\n/g, '<br>')}</p>`;
    });
    return blocks.join('\n');
}

function renderMarkdownWithDanger(text) {
    if (!text) return '';
    // Pre-mark danger spans with placeholder tokens, then run markdown, then swap.
    const re = new RegExp('(' + DANGER_TERMS.map(t => t.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')).join('|') + ')', 'gi');
    const tokens = [];
    const tokenized = text.replace(re, (m) => {
        const idx = tokens.push(m) - 1;
        return ` DANGER${idx} `;
    });
    let html = renderMarkdown(tokenized);
    html = html.replace(/ DANGER(\d+) /g, (_, i) => {
        const term = tokens[+i];
        return `<span class="danger-term" title="⚠️ Validation pathologique">${escapeHtml(term)}</span>`;
    });
    return html;
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'à l\'instant';
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`;
    if (diff < 86400 * 2) return 'hier';
    if (diff < 86400 * 7) return `il y a ${Math.floor(diff / 86400)}j`;
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

function showWelcome() {
    if (state.compareMode) return;
    if (!$('#welcome')) {
        $('#messages').innerHTML = '';
        $('#messages').appendChild(welcomeNode());
    }
}
function hideWelcome() {
    const w = $('#welcome');
    if (w) w.remove();
}

function scrollToBottom(force = false) {
    const m = $('#messages');
    if (force || state.autoScroll) {
        requestAnimationFrame(() => { m.scrollTop = m.scrollHeight; });
    }
}

function updateSendBtn() {
    const btn = $('#sendBtn');
    const val = $('#input').value.trim();
    if (state.sending) {
        btn.disabled = false;
        btn.classList.remove('active');
        btn.classList.add('stop-mode');
        btn.setAttribute('aria-label', 'Stop');
        return;
    }
    btn.classList.remove('stop-mode');
    const enabled = val.length > 0;
    btn.disabled = !enabled;
    btn.classList.toggle('active', enabled);
    btn.setAttribute('aria-label', 'Send');
}

function stopGeneration() {
    if (!state.sending) return;
    state.cancelled = true;
    state.sending = false;
    // Finalize any partial bubble so user keeps what was streamed.
    if (stream.bubbleEl) {
        stream.bubbleEl.classList.remove('streaming');
        const c = stream.bubbleInner?.querySelector('.streaming-cursor');
        if (c) c.remove();
        // Persist partial
        if (stream.text) {
            state.messages.push({
                role: 'assistant',
                content: stream.text + ` …[${t('stopped')}]`,
            });
        }
    }
    cancelStream();
    removeTyping();
    removeCompTyping();
    // Best-effort cancel to server (server may ignore).
    try {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({ type: 'cancel' }));
        }
    } catch {}
    updateSendBtn();
}

function autoResize(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
}

// ────── Modal / dialog ──────
let _modalOnConfirm = null;
function closeModal() {
    $('#confirmModal').hidden = true;
    _modalOnConfirm = null;
}
function confirmDialog(title, body, onConfirm) {
    $('#confirmTitle').textContent = title || 'Confirmer';
    $('#confirmBody').textContent = body || '';
    _modalOnConfirm = onConfirm;
    $('#confirmModal').hidden = false;
}
function initModal() {
    const modal = $('#confirmModal');
    modal.addEventListener('click', (e) => {
        if (e.target.closest('[data-close]')) closeModal();
    });
    $('#confirmOk').addEventListener('click', () => {
        const cb = _modalOnConfirm;
        closeModal();
        if (cb) cb();
    });
    const about = $('#aboutModal');
    about.addEventListener('click', (e) => {
        if (e.target.closest('[data-close]')) about.hidden = true;
    });
}

// ────── Sidebar (mobile) ──────
function openSidebarMobile() {
    state.sidebarOpen = true;
    $('#sidebar').classList.add('open');
    $('#sidebarBackdrop').classList.add('show');
}
function closeSidebarMobile() {
    state.sidebarOpen = false;
    $('#sidebar').classList.remove('open');
    $('#sidebarBackdrop').classList.remove('show');
}

// ────── Compare mode toggling ──────
function setCompareMode(on) {
    if (on && (state.mode !== 'admin' || window.innerWidth <= 1024)) {
        on = false;
    }
    state.compareMode = on;
    document.body.classList.toggle('compare-mode', on);
    $('#compareBtn').classList.toggle('active', on);
    $('#comparison').hidden = !on;
    $('#messages').hidden = on;
}

// ────── Selection screen ──────
function showSelectionScreen() {
    $('#selectionScreen').hidden = false;
}
function hideSelectionScreen() {
    $('#selectionScreen').hidden = true;
}

function initSelectionScreen() {
    $$('.mode-card').forEach(card => {
        card.addEventListener('click', () => {
            const mode = card.dataset.mode === 'admin' ? 'admin' : 'user';
            localStorage.setItem(LS_KEYS.MODE, mode);
            if (mode === 'admin') {
                localStorage.setItem(LS_KEYS.ADMIN_OK, 'true');
            } else {
                localStorage.removeItem(LS_KEYS.ADMIN_OK);
            }
            applyMode(mode);
            hideSelectionScreen();
            bootApp();
        });
    });
}

// ────── Settings menu ──────
function toggleSettings(force) {
    const menu = $('#settingsMenu');
    const next = (typeof force === 'boolean') ? force : menu.hidden;
    menu.hidden = !next;
}

function initSettings() {
    $('#settingsBtn').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleSettings();
    });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.settings-wrap')) toggleSettings(false);
    });
    $('#settingsMenu').addEventListener('click', (e) => {
        const item = e.target.closest('.menu-item');
        if (!item) return;
        const act = item.dataset.act;
        if (!act) return;  // lang select etc. — no action, keep menu open
        toggleSettings(false);
        if (act === 'switch-mode') {
            localStorage.removeItem(LS_KEYS.MODE);
            localStorage.removeItem(LS_KEYS.ADMIN_OK);
            location.reload();
        } else if (act === 'theme') {
            const cur = localStorage.getItem(LS_KEYS.THEME) || 'dark';
            const next = cur === 'dark' ? 'light' : 'dark';
            localStorage.setItem(LS_KEYS.THEME, next);
            applyTheme(next);
        } else if (act === 'about') {
            $('#aboutModal').hidden = false;
        } else if (act === 'export') {
            exportSession();
        } else if (act === 'profile') {
            openProfileModal();
        } else if (act === 'reset-profile') {
            confirmDialog(
                t('reset_title'),
                t('reset_body'),
                async () => {
                    try {
                        await api('/api/profile', { method: 'DELETE' });
                        appendErrorBubble(t('reset_done'));
                    } catch (e) {
                        appendErrorBubble('Error: ' + e.message);
                    }
                }
            );
        }
    });
}

async function openProfileModal() {
    const modal = $('#profileModal');
    modal.hidden = false;
    const summary = $('#profileSummary');
    const overview = $('#paneOverview');
    const adaptation = $('#paneAdaptation');
    const json = $('#paneJson');
    summary.textContent = 'Chargement…';
    overview.innerHTML = '';
    adaptation.innerHTML = '';
    json.textContent = '—';

    try {
        const data = await api('/api/profile');
        renderProfile(data);
    } catch (e) {
        summary.textContent = 'Erreur: ' + e.message;
    }
}

function renderProfile(data) {
    const p = data.profile || {};
    const pp = p.psychiatric_profile || {};
    const cp = p.conversational_profile || {};
    const bp = p.behavioral_profile || {};
    const ar = p.adaptation_rules || {};

    // Summary
    const sum = $('#profileSummary');
    const adj = data.risk_adjustment ?? 0;
    sum.textContent = (
        `Utilisateur: ${p.user_id || '—'} · ` +
        `${p.total_conversations || 0} conversations · ${p.total_turns || 0} tours\n` +
        `Ajustement de risque: ${adj >= 0 ? '+' : ''}${adj.toFixed(2)} · ` +
        `Sujets sensibles: ${(data.sensitive_topics || []).join(', ') || 'aucun'}`
    );

    // Overview pane
    const ov = $('#paneOverview');
    const conds = Object.entries(pp.conditions_observed || {})
        .map(([k, v]) => `<li>${escapeHtml(k)} — ${v.occurrences || 1}× · peak ${(v.peak_score || 0).toFixed(2)}</li>`)
        .join('') || '<li class="muted">aucune</li>';
    const rages = (bp.rage_quit_contexts || [])
        .map(r => `<li>${escapeHtml(r.date || '?')} — ${escapeHtml(r.trigger || '?')} (score ${(r.last_score || 0).toFixed(2)})</li>`)
        .join('') || '<li class="muted">aucun</li>';
    const sessions = (p.session_history || []).slice(-8).reverse()
        .map(s => `<li>${escapeHtml((s.date || '').slice(0, 10))} — ${s.turns || 0} tours · ${escapeHtml(s.peak_action || '?')} (peak ${(s.peak_score || 0).toFixed(2)})${s.rage_quit ? ' · ⚠️ rage-quit' : ''}</li>`)
        .join('') || '<li class="muted">aucune</li>';

    ov.innerHTML = `
        <h4>Profil psychiatrique</h4>
        <div class="kv">
            <span class="k">Conditions</span><span class="v"><ul style="margin:0;padding-left:18px;">${conds}</ul></span>
            <span class="k">Signaux chroniques</span><span class="v">${(pp.chronic_signals || []).join(', ') || '—'}</span>
            <span class="k">Médicaments mentionnés</span><span class="v">${(pp.medication_mentioned || []).join(', ') || '—'}</span>
            <span class="k">Facteurs protecteurs</span><span class="v">${(pp.protective_factors_known || []).join(', ') || '—'}</span>
        </div>

        <h4>Profil conversationnel</h4>
        <div class="kv">
            <span class="k">Langue</span><span class="v">${escapeHtml(cp.language || '—')}</span>
            <span class="k">Formalité</span><span class="v">${escapeHtml(cp.formality || '—')}</span>
            <span class="k">Longueur typique</span><span class="v">${escapeHtml(cp.typical_message_length || '—')}</span>
            <span class="k">Argot / Emojis</span><span class="v">${cp.uses_slang ? 'oui' : 'non'} / ${cp.uses_emojis ? 'oui' : 'non'}</span>
        </div>

        <h4>Profil comportemental</h4>
        <div class="kv">
            <span class="k">Rage-quit</span><span class="v">${bp.rage_quit_count || 0}</span>
            <span class="k">Conversation moy.</span><span class="v">${(bp.avg_conversation_length || 0).toFixed(1)} tours</span>
            <span class="k">Tendance escalade</span><span class="v">${bp.tends_to_escalate ? 'oui' : 'non'}</span>
            <span class="k">Tendance manipulation</span><span class="v">${bp.tends_to_manipulate ? 'oui' : 'non'}</span>
            <span class="k">Stratégies vues</span><span class="v">${(bp.manipulation_strategies_used || []).join(', ') || '—'}</span>
        </div>

        <h4>Contextes de rage-quit</h4>
        <ul style="margin:0;padding-left:18px;">${rages}</ul>

        <h4>Sessions récentes</h4>
        <ul style="margin:0;padding-left:18px;">${sessions}</ul>
    `;

    // Adaptation pane
    const adp = $('#paneAdaptation');
    const instr = data.adaptation_instructions || '(aucune adaptation active)';
    adp.innerHTML = `
        <h4>Règles d'adaptation calculées</h4>
        <div class="kv">
            <span class="k">Style d'approche</span><span class="v">${escapeHtml(ar.approach_style || '—')}</span>
            <span class="k">Mention pro après tour</span><span class="v">${ar.mention_professional_after_turn || '—'}</span>
            <span class="k">Technique de blocage</span><span class="v">${escapeHtml(ar.block_technique_preferred || '—')}</span>
            <span class="k">Ton urgence</span><span class="v">${escapeHtml(ar.emergency_tone || '—')}</span>
            <span class="k">Mots à éviter</span><span class="v">${(ar.avoid_words || []).join(', ') || '—'}</span>
            <span class="k">Mots préférés</span><span class="v">${(ar.prefer_words || []).join(', ') || '—'}</span>
        </div>

        <h4>Instructions injectées dans Pass 2</h4>
        <pre class="debug-block">${escapeHtml(instr)}</pre>
    `;

    // JSON pane
    $('#paneJson').textContent = JSON.stringify(p, null, 2);
}

function initProfileModal() {
    const modal = $('#profileModal');
    modal.addEventListener('click', (e) => {
        if (e.target.closest('[data-close]')) modal.hidden = true;
        const tab = e.target.closest('.profile-tab');
        if (tab) {
            modal.querySelectorAll('.profile-tab').forEach(t => t.classList.toggle('active', t === tab));
            const which = tab.dataset.tab;
            $('#paneOverview').hidden = which !== 'overview';
            $('#paneAdaptation').hidden = which !== 'adaptation';
            $('#paneJson').hidden = which !== 'json';
        }
    });
}

async function exportSession() {
    if (!state.activeId) return;
    try {
        const conv = await api(`/api/conversations/${state.activeId}`);
        const blob = new Blob([JSON.stringify(conv, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `serena-${state.activeId}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (e) {
        appendErrorBubble('Export impossible: ' + e.message);
    }
}

// ────── Init ──────
function bootApp() {
    loadConversations().then(async () => {
        if (state.conversations.length === 0) {
            await createConversation();
        } else {
            await loadConversation(state.conversations[0].id);
        }
    });
}

function init() {
    // Theme
    const theme = localStorage.getItem(LS_KEYS.THEME) || 'dark';
    applyTheme(theme);

    // Language
    const savedLang = localStorage.getItem(LS_KEYS.LANG) || 'en';
    applyLang(savedLang);
    const langSel = $('#langSelect');
    if (langSel) {
        langSel.value = state.lang;
        langSel.addEventListener('change', () => {
            const v = langSel.value;
            localStorage.setItem(LS_KEYS.LANG, v);
            applyLang(v);
        });
    }

    // Initial mode decision
    const m = getInitialMode();
    if (!m) {
        showSelectionScreen();
    } else {
        applyMode(m);
        bootApp();
    }
    initSelectionScreen();

    // Composer
    const ta = $('#input');
    ta.addEventListener('input', () => { autoResize(ta); updateSendBtn(); });
    ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (state.sending) { stopGeneration(); return; }
            const val = ta.value;
            ta.value = '';
            autoResize(ta);
            updateSendBtn();
            sendMessage(val);
        }
    });
    $('#sendBtn').addEventListener('click', () => {
        if (state.sending) { stopGeneration(); return; }
        const val = ta.value;
        ta.value = '';
        autoResize(ta);
        updateSendBtn();
        sendMessage(val);
    });

    $('#newChatBtn').addEventListener('click', () => createConversation());

    $('#messages').addEventListener('click', (e) => {
        const s = e.target.closest('.suggestion');
        if (s) {
            const prompt = s.dataset[`prompt${state.lang.charAt(0).toUpperCase() + state.lang.slice(1)}`] || s.dataset.prompt;
            ta.value = prompt;
            updateSendBtn();
            sendMessage(prompt);
        }
    });

    // Sidebar collapse (desktop)
    $('#sidebarCollapse').addEventListener('click', () => {
        state.sidebarCollapsed = true;
        $('#sidebar').classList.add('collapsed');
        $('#sidebarReopen').hidden = false;
    });
    $('#sidebarReopen').addEventListener('click', () => {
        state.sidebarCollapsed = false;
        $('#sidebar').classList.remove('collapsed');
        $('#sidebarReopen').hidden = true;
    });

    // Sidebar (mobile)
    $('#burgerBtn').addEventListener('click', openSidebarMobile);
    $('#sidebarBackdrop').addEventListener('click', closeSidebarMobile);
    $('#dashboardBtn').addEventListener('click', () => {
        openSidebarMobile();
        $('#dashboardToggle').click();
    });

    // Dashboard toggle
    $('#dashboardToggle').addEventListener('click', () => {
        $('#dashboardToggle').classList.toggle('open');
        $('#dashboardPanel').classList.toggle('open');
    });

    // Bar collapse
    $('#barCollapse').addEventListener('click', () => {
        state.barCollapsed = true;
        $('#serenaBar').classList.add('collapsed');
        $('#barReopen').hidden = false;
    });
    $('#barReopen').addEventListener('click', () => {
        state.barCollapsed = false;
        $('#serenaBar').classList.remove('collapsed');
        $('#barReopen').hidden = true;
    });

    $('#barSignals').addEventListener('click', (e) => {
        e.stopPropagation();
        showSignalsPopover();
    });

    // Top header buttons
    $('#viewUserBtn').addEventListener('click', () => {
        document.body.classList.toggle('user-preview');
        $('#viewUserBtn').classList.toggle('active', document.body.classList.contains('user-preview'));
    });
    $('#compareBtn').addEventListener('click', async () => {
        if (state.mode !== 'admin') return;
        if (state.compareMode) {
            setCompareMode(false);
            await createConversation();
        } else {
            setCompareMode(true);
            await createConversation('comparison');
        }
    });

    initSettings();

    // Debug toggle
    $('#debugToggle').addEventListener('click', () => {
        $('#debugToggle').classList.toggle('open');
        const body = $('#debugBody');
        body.hidden = !body.hidden;
    });

    // Emergency banner close
    $('#emergencyClose').addEventListener('click', () => {
        state.emergencyDismissed = true;
        hideEmergencyBanner();
    });

    // Scroll button
    const messagesEl = $('#messages');
    messagesEl.addEventListener('scroll', () => {
        const distance = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
        state.autoScroll = distance < 80;
        $('#scrollBtn').hidden = state.autoScroll;
    });
    $('#scrollBtn').addEventListener('click', () => {
        state.autoScroll = true;
        scrollToBottom(true);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
            e.preventDefault();
            createConversation();
        }
        if (e.key === 'Escape') {
            const modal = $('#confirmModal');
            if (!modal.hidden) { closeModal(); return; }
            const about = $('#aboutModal');
            if (!about.hidden) { about.hidden = true; return; }
            if (state.sidebarOpen) closeSidebarMobile();
            toggleSettings(false);
        }
    });

    initModal();
    initProfileModal();

    $('#bannerClose').addEventListener('click', () => { $('#reconnectBanner').hidden = true; });

    if (window.visualViewport) {
        const onResize = () => {
            const vh = window.visualViewport.height;
            document.documentElement.style.setProperty('--viewport-h', `${vh}px`);
        };
        window.visualViewport.addEventListener('resize', onResize);
        onResize();
    }

    // Window resize: kill compare mode if window narrows below 1024
    window.addEventListener('resize', () => {
        if (state.compareMode && window.innerWidth <= 1024) {
            setCompareMode(false);
        }
    });

    connectWS();
    updateSendBtn();
}

function showSignalsPopover() {
    const pop = $('#signalsPopover');
    const body = $('#signalsPopoverBody');
    const signals = state.lastSnapshot?.signals || {};
    body.innerHTML = '';
    if (Object.keys(signals).length === 0) {
        body.innerHTML = `<span class="muted">${t('no_signals_detected')}</span>`;
    } else {
        for (const [name, info] of Object.entries(signals)) {
            const chip = document.createElement('span');
            chip.className = 'signal-chip';
            chip.textContent = `${name} · T${info.first_seen ?? '?'} ×${info.count ?? 1}`;
            body.appendChild(chip);
        }
    }
    pop.hidden = false;
    setTimeout(() => {
        document.addEventListener('click', () => { pop.hidden = true; }, { once: true });
    });
}

document.addEventListener('DOMContentLoaded', init);
