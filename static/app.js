/**
 * app.js - Interview Orchestrator Frontend
 * 
 * REFACTOR #3: Typed Error Handling (Frontend)
 * ----------------------------------------------
 * The api() function now preserves the error_type from the backend.
 * showError() shows contextual help based on the error type:
 *   - api_key_error    → "Check your .env file"
 *   - rate_limit_error → "Wait a moment and retry"
 *   - model_error      → "Check Model Registry in Settings"
 *   - validation_error → shows the message as-is
 *   - others           → generic display
 * 
 * Also includes #6 (dynamic model dropdowns, registry UI, temperature).
 */

let autoRoute = true;
let selectedAgentId = 1;
let activeThreadId = 1;
let agents = [];
let currentReport = null;
let currentSessionId = null;
let modelRegistry = [];

const AGENT_ICONS = { 1: '🪞', 2: '🛑', 3: '🎯', 4: '⚙️', 5: '🛡️' };

// ── Error Type → Help Text Mapping ───────────────────────────────
// When the backend returns an error_type, we show a specific hint
// so the user knows what to do about it.
const ERROR_HINTS = {
    api_key_error:    '🔑 Check your GEMINI_API_KEY in the .env file.',
    rate_limit_error: '⏳ Gemini rate limit reached. Wait a moment and retry.',
    model_error:      '🔧 Model unavailable. Open Settings → Model Registry to update.',
    agent_not_found:  '❓ Agent not found. This may be a configuration issue.',
    validation_error: '',   // Message is already clear enough
    ai_response_error:'🤖 The AI returned an unusable response. Try again.',
};

// ── Initialization ───────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('messageInput');
    input.addEventListener('input', () => { document.getElementById('sendBtn').disabled = !input.value.trim(); });
    loadModels();
    loadAgents();
    loadSessions();
});

async function api(url, options = {}) {
    try {
        const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            // ── #3: Create a richer error that carries the error_type ──
            const err = new Error(errorData.error || `Server error: ${response.status}`);
            err.errorType = errorData.error_type || 'unknown_error';
            err.status = response.status;
            throw err;
        }
        return await response.json();
    } catch (err) {
        // If it's our enriched error, show it with context
        showError(err.message, err.errorType);
        throw err;
    }
}

// ── NEW: Load Model Registry ─────────────────────────────────────

async function loadModels() {
    try {
        modelRegistry = await api('/api/models');
    } catch (e) {
        console.error("Failed to load model registry", e);
        modelRegistry = [];
    }
}

// ── UI Utilities ─────────────────────────────────────────────────

function showStatus(text, icon = '⏳') {
    document.getElementById('statusBar').classList.remove('hidden');
    document.getElementById('statusText').textContent = text;
    document.getElementById('statusIcon').textContent = icon;
}
function hideStatus() { document.getElementById('statusBar').classList.add('hidden'); }

function showError(text, errorType) {
    /**
     * REFACTOR #3: Contextual error display.
     * If we know the error_type, append a helpful hint so the user
     * knows what to do — not just what went wrong.
     */
    const hint = (errorType && ERROR_HINTS[errorType]) ? ERROR_HINTS[errorType] : '';
    const fullMessage = hint ? `${text}\n${hint}` : text;
    
    const errorBar = document.getElementById('errorBar');
    const errorText = document.getElementById('errorText');
    
    errorBar.classList.remove('hidden');
    errorText.innerHTML = escapeHtml(text) + (hint ? `<br><span class="text-xs opacity-75">${escapeHtml(hint)}</span>` : '');
    
    // Rate limit errors get a longer display time
    const timeout = errorType === 'rate_limit_error' ? 15000 : 8000;
    setTimeout(hideError, timeout);
}
function hideError() { document.getElementById('errorBar').classList.add('hidden'); }

// ── Session Management ───────────────────────────────────────────

async function loadSessions() {
    try {
        const sessions = await api('/api/sessions');
        const list = document.getElementById('sessionList');
        
        if (sessions.length === 0) {
            list.innerHTML = '<p class="text-themeMuted text-xs italic p-2 text-center">No active sessions.</p>';
            showWelcome();
            return;
        }

        list.innerHTML = sessions.map(s => `
            <div class="flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors group ${s.id === currentSessionId ? 'bg-themeAccent/10 text-themeAccent font-bold border border-themeAccent/30 shadow-sm' : 'text-themeText hover:bg-themeSurface border border-transparent'}" onclick="selectSession(${s.id}, '${escapeHtml(s.name.replace(/'/g, "\\'"))}')">
                <div class="truncate text-sm flex-1 pr-2">${escapeHtml(s.name)}</div>
                <button onclick="deleteSession(event, ${s.id})" class="hidden group-hover:block text-themeMuted hover:text-red-600 text-lg leading-none" title="Delete">&times;</button>
            </div>
        `).join('');

        if (!currentSessionId && sessions.length > 0) selectSession(sessions[0].id, sessions[0].name);
    } catch (err) { console.error("Failed to load sessions", err); }
}

async function selectSession(id, name) {
    currentSessionId = id;
    document.getElementById('currentSessionTitle').textContent = name || `Session ${id}`;

    const convos = await api(`/api/sessions/${id}/conversations`);
    if (convos.length > 0) {
        hideWelcome();
        await loadThread(activeThreadId);
        await loadRoutingLogs();
        document.getElementById('finalizeBtn').disabled = false;
    } else {
        showWelcome();
    }
    const sessions = await api('/api/sessions');
    const list = document.getElementById('sessionList');
    list.innerHTML = sessions.map(s => `<div class="flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors group ${s.id === currentSessionId ? 'bg-themeAccent/10 text-themeAccent font-bold border border-themeAccent/30 shadow-sm' : 'text-themeText hover:bg-themeSurface border border-transparent'}" onclick="selectSession(${s.id}, '${escapeHtml(s.name.replace(/'/g, "\\'"))}')"><div class="truncate text-sm flex-1 pr-2">${escapeHtml(s.name)}</div><button onclick="deleteSession(event, ${s.id})" class="hidden group-hover:block text-themeMuted hover:text-red-600 text-lg leading-none" title="Delete">&times;</button></div>`).join('');
}

async function startNewSession() {
    showStatus('Creating and initializing session...');
    try {
        const res = await api('/api/sessions', { method: 'POST', body: JSON.stringify({}) });
        currentSessionId = res.id;
        document.getElementById('currentSessionTitle').textContent = res.name;
        
        const initRes = await api(`/api/sessions/${currentSessionId}/initialize`, { method: 'POST' });
        
        hideWelcome();
        document.getElementById('finalizeBtn').disabled = false;

        await loadSessions();
        await loadThread(1);
        await loadRoutingLogs();
        hideStatus();
        
        if (initRes.agents && initRes.agents['1']) {
            displayResponse({
                agent_id: 1, agent_name: 'Brand Spine', routing_reason: 'Session initialized', response: initRes.agents['1']
            });
        }
    } catch (err) { showError("Failed to create session"); hideStatus(); }
}

async function deleteSession(event, id) {
    event.stopPropagation();
    if (!confirm('Delete this session permanently?')) return;
    try {
        await api(`/api/sessions/${id}`, { method: 'DELETE' });
        if (currentSessionId === id) currentSessionId = null;
        await loadSessions();
    } catch (err) { showError("Failed to delete session"); }
}

function showWelcome() {
    document.getElementById('welcomeSection').classList.remove('hidden');
    document.getElementById('mainContent').classList.add('hidden');
    document.getElementById('finalizeBtn').disabled = true;
}

function hideWelcome() {
    document.getElementById('welcomeSection').classList.add('hidden');
    document.getElementById('mainContent').classList.remove('hidden');
}

// ── Orchestration & Input ────────────────────────────────────────

function toggleAutoRoute() {
    autoRoute = document.getElementById('autoRouteToggle').checked;
    const selector = document.getElementById('manualSelector');
    if (autoRoute) selector.classList.add('hidden');
    else { selector.classList.remove('hidden'); selectAgent(selectedAgentId); }
}

function selectAgent(id) {
    selectedAgentId = id;
    document.querySelectorAll('.agent-tab').forEach(t => t.classList.toggle('active', parseInt(t.dataset.agent) === id));
}

function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(e); }
}

async function handleSend(e) {
    if (e) e.preventDefault();
    if (!currentSessionId) return;

    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    document.getElementById('sendBtn').disabled = true;
    showStatus('Routing & Analyzing...');
    document.getElementById('sendIcon').innerHTML = '<span class="spinner"></span>';

    try {
        let result = autoRoute 
            ? await api(`/api/sessions/${currentSessionId}/send`, { method: 'POST', body: JSON.stringify({ message }) })
            : await api(`/api/sessions/${currentSessionId}/send-manual`, { method: 'POST', body: JSON.stringify({ agent_id: selectedAgentId, message }) });

        displayResponse(result);
        await loadThread(result.agent_id || selectedAgentId);
        await loadRoutingLogs();
        
        if(result.session_renamed) {
            document.getElementById('currentSessionTitle').textContent = result.session_renamed;
            loadSessions();
        }
    } catch (err) { console.error('Send failed:', err); } 
    finally { hideStatus(); document.getElementById('sendIcon').textContent = '▶'; document.getElementById('sendBtn').disabled = false; }
}

function displayResponse(result) {
    document.getElementById('responseSection').classList.remove('hidden');
    const agentId = result.agent_id || selectedAgentId;
    document.getElementById('routeIcon').textContent = AGENT_ICONS[agentId] || '🤖';
    document.getElementById('routeAgent').textContent = `Routed to: ${result.agent_name || 'Agent ' + agentId}`;
    document.getElementById('routeReason').textContent = result.routing_reason || '';

    const parsed = parseAgentResponse(result.response || '');
    document.getElementById('nextQuestion').innerHTML = formatMarkdown(parsed.question || 'No specific question suggested.');
    document.getElementById('analysisContent').innerHTML = formatMarkdown(parsed.analysis || 'No analysis provided.');
    document.getElementById('pivotContent').innerHTML = formatMarkdown(parsed.pivot || 'No tactical pivot provided.');
    showThread(agentId);
}

function parseAgentResponse(text) {
    const r = { analysis: '', pivot: '', question: '' };
    const aMatch = text.match(/🧠\s*(?:SILENT ANALYSIS|Silent Analysis)[^\n]*\n([\s\S]*?)(?=🎯|$)/i);
    const pMatch = text.match(/🎯\s*(?:TACTICAL PIVOT|Tactical Pivot)[^\n]*\n([\s\S]*?)(?=☕|$)/i);
    const qMatch = text.match(/☕\s*(?:YOUR NEXT QUESTION|THE CONSULTANT'S SCRIPT|Next Question)[^\n]*\n([\s\S]*?)$/i);
    if (aMatch) r.analysis = aMatch[1].trim();
    if (pMatch) r.pivot = pMatch[1].trim();
    if (qMatch) r.question = qMatch[1].trim();
    if (!r.analysis && !r.pivot && !r.question) r.question = text;
    return r;
}

function formatMarkdown(text) {
    // SECURITY: Escape HTML entities FIRST, then apply markdown formatting.
    // This prevents any <script>, <img onerror=...>, etc. from executing.
    // Without this, AI-reflected input could run arbitrary JS in the browser.
    return escapeHtml(text)
               .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
               .replace(/\*(.+?)\*/g, '<em>$1</em>')
               .replace(/^[\s]*[-*]\s+/gm, '• ')
               .replace(/\n/g, '<br>');
}

// ── Threads & Logs ───────────────────────────────────────────────

function showThread(agentId) {
    activeThreadId = agentId;
    document.querySelectorAll('.thread-tab').forEach(t => t.classList.toggle('active', parseInt(t.dataset.thread) === agentId));
    loadThread(agentId);
}

async function loadThread(agentId) {
    if (!currentSessionId) return;
    try {
        const msgs = await api(`/api/sessions/${currentSessionId}/conversations?agent_id=${agentId}`);
        const c = document.getElementById('threadContent');
        if (msgs.length === 0) {
            c.innerHTML = '<p class="text-themeMuted text-sm italic text-center py-8">No messages in this thread yet.</p>';
            return;
        }
        c.innerHTML = msgs.map(m => `
            <div class="thread-message ${m.role === 'user' ? 'user' : 'model'}">
                <span class="role-label">${m.role === 'user' ? 'Consultant' : AGENT_ICONS[agentId] + ' ' + escapeHtml(m.agent_name || 'Agent')}</span>
                <div>${formatMarkdown(m.content)}</div>
            </div>
        `).join('');
        c.scrollTop = c.scrollHeight;
    } catch (err) {}
}

async function loadRoutingLogs() {
    if (!currentSessionId) return;
    try {
        const logs = await api(`/api/sessions/${currentSessionId}/routing-logs`);
        const c = document.getElementById('routingLog');
        if (logs.length === 0) { c.innerHTML = '<p class="text-themeMuted text-sm italic">No routing decisions yet.</p>'; return; }
        c.innerHTML = logs.map(l => `
            <div class="routing-entry mb-2">
                <div class="flex justify-between items-center mb-1">
                    <span class="font-bold text-themeAccent">${AGENT_ICONS[l.agent_id]||'🤖'} ${escapeHtml(l.agent_name)}</span>
                    <span class="text-themeMuted text-xs">${new Date(l.timestamp + 'Z').toLocaleTimeString()}</span>
                </div>
                <div class="text-themeText italic">"${escapeHtml(truncate(l.input_text, 80))}"</div>
                ${l.reason ? `<div class="text-themeMuted mt-1 text-xs opacity-80">${escapeHtml(l.reason)}</div>` : ''}
            </div>
        `).join('');
    } catch (err) {}
}
function truncate(t, m) { return t && t.length > m ? t.substring(0, m) + '...' : t; }

// ── Graceful Finalization (The Traffic Cop) ──────────────────────

function showFinalizeConfirm() {
    showConfirm('Finalize Interview?', 'This will ask each agent to summarize their findings and generate the Architecture Specification.', () => startFinalize(false));
}

async function startFinalize(force = false) {
    if (!currentSessionId) return;
    closeConfirm();
    closeTriage();
    showStatus('Evaluating agent readiness & summarizing...');
    document.getElementById('finalizeBtn').disabled = true;

    try {
        const result = await api(`/api/sessions/${currentSessionId}/finalize`, { method: 'POST', body: JSON.stringify({ force }) });
        
        if (result.status === 'warning') {
            hideStatus();
            document.getElementById('finalizeBtn').disabled = false;
            showTriageModal(result.sparse_agents);
            return;
        }

        currentReport = result;
        if (result.errors?.length > 0) showError('Some agents had issues: ' + result.errors.join('; '));
        showReport(result);
    } catch (err) { console.error(err); } 
    finally { hideStatus(); document.getElementById('finalizeBtn').disabled = false; }
}

function showTriageModal(sparse) {
    const list = document.getElementById('triageAgentList');
    list.innerHTML = sparse.map(a => `<li>${AGENT_ICONS[a.id]} ${escapeHtml(a.name)}</li>`).join('');
    document.getElementById('triageModal').classList.remove('hidden');
}
function closeTriage() { document.getElementById('triageModal').classList.add('hidden'); }
function forcePartialReport() { startFinalize(true); }

function showReport(r) {
    document.getElementById('reportModal').classList.remove('hidden');
    document.getElementById('reportContent').innerHTML = formatMarkdown(r.synthesis || 'No synthesis generated.');
    const agentNames = { 1: 'Brand Spine', 2: 'Founder Invariants', 3: 'Customer Reality', 4: 'Architecture Translation' };
    document.getElementById('payloadsContent').innerHTML = Object.entries(r.payloads || {}).map(([id, txt]) => `
        <div class="bg-themeSurface rounded-lg p-3 border border-themeBorder">
            <h4 class="text-xs font-bold text-themeAccent mb-1 uppercase">${AGENT_ICONS[id] || '🤖'} ${agentNames[id] || 'Agent ' + id}</h4>
            <div class="text-xs text-themeText whitespace-pre-wrap">${formatMarkdown(txt)}</div>
        </div>
    `).join('');
}
function closeReport() { document.getElementById('reportModal').classList.add('hidden'); }

function downloadReport() {
    if (!currentReport) return;
    let t = "INTERVIEW ORCHESTRATOR - FINAL REPORT\n" + "=".repeat(50) + `\nGenerated: ${new Date().toLocaleString()}\n\n`;
    const names = { 1: 'Brand Spine', 2: 'Founder Invariants', 3: 'Customer Reality', 4: 'Architecture Translation' };
    for (const [id, c] of Object.entries(currentReport.payloads || {})) { t += `\n--- ${names[id] || 'Agent '+id} ---\n${c}\n`; }
    t += "\n\n" + "=".repeat(50) + "\nGRAND SYNTHESIS\n" + "=".repeat(50) + `\n\n${currentReport.synthesis || ''}`;
    const url = URL.createObjectURL(new Blob([t], { type: 'text/plain' }));
    const a = document.createElement('a'); a.href = url; a.download = `Architecture-Spec-${new Date().toISOString().split('T')[0]}.txt`;
    a.click(); URL.revokeObjectURL(url);
}

// ── Settings & Configurations ────────────────────────────────────

async function loadAgents() { try { agents = await api('/api/agents'); } catch(e){} }
function openSettings() { document.getElementById('settingsModal').classList.remove('hidden'); renderAgentSettings(); }
function closeSettings() { document.getElementById('settingsModal').classList.add('hidden'); }

function buildModelOptions(selectedModel) {
    const active = modelRegistry.filter(m => m.status === 'active');
    const deprecated = modelRegistry.filter(m => m.status !== 'active');
    
    let html = '';
    for (const m of active) {
        html += `<option value="${escapeHtml(m.id)}" ${selectedModel === m.id ? 'selected' : ''}>${escapeHtml(m.label)}</option>`;
    }
    if (deprecated.length > 0) {
        html += '<optgroup label="── Deprecated ──">';
        for (const m of deprecated) {
            html += `<option value="${escapeHtml(m.id)}" ${selectedModel === m.id ? 'selected' : ''}>${escapeHtml(m.label)}</option>`;
        }
        html += '</optgroup>';
    }
    const allIds = modelRegistry.map(m => m.id);
    if (selectedModel && !allIds.includes(selectedModel)) {
        html += `<optgroup label="── Not in Registry ──">`;
        html += `<option value="${escapeHtml(selectedModel)}" selected>⚠️ ${escapeHtml(selectedModel)}</option>`;
        html += `</optgroup>`;
    }
    return html;
}

function buildThinkingOptions(currentLevel) {
    return `
        <option value="" ${!currentLevel ? 'selected' : ''}>Off</option>
        <option value="LOW" ${currentLevel === 'LOW' ? 'selected' : ''}>Low</option>
        <option value="MEDIUM" ${currentLevel === 'MEDIUM' ? 'selected' : ''}>Medium (Default)</option>
        <option value="HIGH" ${currentLevel === 'HIGH' ? 'selected' : ''}>High</option>
    `;
}

function modelSupportsThinking(modelId) {
    const model = modelRegistry.find(m => m.id === modelId);
    return model ? model.supports_thinking : false;
}

async function renderAgentSettings() {
    await loadModels();
    const c = document.getElementById('agentSettings');
    
    let rModel = '';
    try {
        const routerData = await api('/api/config/router-model');
        rModel = routerData.model || '';
    } catch (err) {}
    
    const tLevels = {};
    const temps = {};
    for (const a of agents) {
        try { 
            const data = await api(`/api/config/thinking-level/${a.id}`);
            tLevels[a.id] = data.thinking_level || ''; 
        } catch(e) { tLevels[a.id] = ''; }
        try { 
            const data = await api(`/api/config/temperature/${a.id}`);
            temps[a.id] = data.temperature || ''; 
        } catch(e) { temps[a.id] = ''; }
    }

    let html = '';

    html += `
        <div class="agent-config-card" style="border-left: 3px solid var(--color-teal);">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-xl">📡</span>
                <span class="font-semibold">Router Model</span>
                <span class="text-xs text-gray-400">(classifies inputs → picks agent 1-4)</span>
            </div>
            <div class="flex items-center gap-2">
                <select id="routerModelSelect" class="flex-1 text-xs">
                    ${buildModelOptions(rModel)}
                </select>
                <button onclick="saveRouterModel()" class="btn-primary text-xs">Save</button>
            </div>
            <p class="text-xs text-gray-400 mt-2">
                The Router strictly forces MINIMAL thinking in the backend for near-instant classification.
            </p>
        </div>
    `;

    html += agents.map(a => {
        const supportsThinking = modelSupportsThinking(a.model);
        const tl = tLevels[a.id] || '';
        const temp = temps[a.id] || '';
        
        return `
        <div class="agent-config-card" data-config-id="${a.id}">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-xl">${AGENT_ICONS[a.id] || '🤖'}</span>
                <input type="text" value="${escapeHtml(a.name)}"
                       class="font-semibold flex-1"
                       data-field="name" data-agent="${a.id}">
            </div>
            <div class="flex items-center gap-2 mb-3">
                <label class="text-xs text-gray-500 w-20">Model:</label>
                <select data-field="model" data-agent="${a.id}"
                        class="flex-1 text-xs"
                        onchange="toggleThinking(${a.id}, this.value)">
                    ${buildModelOptions(a.model)}
                </select>
            </div>
            <div class="flex items-center gap-2 mb-3" id="thinking-row-${a.id}"
                 style="display: ${supportsThinking ? 'flex' : 'none'}">
                <label class="text-xs text-gray-500 w-20">Thinking:</label>
                <select data-field="thinking" data-agent="${a.id}" class="flex-1 text-xs">
                    ${buildThinkingOptions(tl)}
                </select>
            </div>
            <div class="flex items-center gap-2 mb-3">
                <label class="text-xs text-gray-500 w-20">Temp:</label>
                <input type="number" data-field="temperature" data-agent="${a.id}"
                       value="${escapeHtml(temp)}"
                       min="0" max="2" step="0.1"
                       placeholder="Model default"
                       class="flex-1 text-xs">
                <span class="text-xs text-gray-400">0.0–2.0</span>
            </div>
            <textarea rows="8" data-field="prompt" data-agent="${a.id}"
                      placeholder="System prompt...">${escapeHtml(a.prompt || '')}</textarea>
            <div class="flex justify-end mt-2">
                <button onclick="saveAgentConfig(${a.id})" class="btn-primary text-xs">
                    Save Changes
                </button>
            </div>
        </div>
        `;
    }).join('');

    html += renderModelRegistrySection();
    c.innerHTML = html;
}

function toggleThinking(agentId, modelValue) {
    const row = document.getElementById(`thinking-row-${agentId}`);
    if (row) {
        row.style.display = modelSupportsThinking(modelValue) ? 'flex' : 'none';
    }
}

async function saveAgentConfig(id) {
    const card = document.querySelector(`[data-config-id="${id}"]`);
    try {
        await api(`/api/agents/${id}`, { method: 'PUT', body: JSON.stringify({
            name: card.querySelector('[data-field="name"]').value,
            model: card.querySelector('[data-field="model"]').value,
            prompt: card.querySelector('[data-field="prompt"]').value
        })});
        
        await api(`/api/config/thinking-level/${id}`, { method: 'PUT', body: JSON.stringify({
            thinking_level: card.querySelector('[data-field="thinking"]')?.value || ''
        })});
        
        const tempValue = card.querySelector('[data-field="temperature"]')?.value || '';
        await api(`/api/config/temperature/${id}`, { method: 'PUT', body: JSON.stringify({
            temperature: tempValue
        })});
        
        await loadAgents();
        showStatus('Saved.', '✅');
        setTimeout(hideStatus, 2000);
    } catch(e){}
}

async function saveRouterModel() {
    try {
        await api('/api/config/router-model', { method: 'PUT', body: JSON.stringify({
            model: document.getElementById('routerModelSelect').value
        })});
        showStatus('Saved.', '✅');
        setTimeout(hideStatus, 2000);
    } catch(e){}
}

// ── Model Registry Maintenance UI ────────────────────────────────

function renderModelRegistrySection() {
    let cards = '';
    
    for (let i = 0; i < modelRegistry.length; i++) {
        const m = modelRegistry[i];
        cards += `
        <div class="registry-model-card" data-registry-index="${i}">
            <div class="flex items-center gap-2 mb-2">
                <span class="text-xs font-bold ${m.status === 'active' ? 'text-green-600' : 'text-orange-500'} uppercase">${m.status}</span>
                <div class="flex-1"></div>
                <button onclick="deleteRegistryModel(${i})" 
                        class="text-red-400 hover:text-red-600 text-sm" title="Remove model">🗑️</button>
            </div>
            <div class="flex gap-2 mb-2">
                <div class="flex-1">
                    <label class="text-xs text-gray-400">API Model ID</label>
                    <input type="text" value="${escapeHtml(m.id)}" 
                           data-reg="id" data-idx="${i}" class="text-xs w-full font-mono">
                </div>
                <div class="flex-1">
                    <label class="text-xs text-gray-400">Display Label</label>
                    <input type="text" value="${escapeHtml(m.label)}" 
                           data-reg="label" data-idx="${i}" class="text-xs w-full">
                </div>
            </div>
            <div class="flex gap-2 mb-2 items-end">
                <div>
                    <label class="text-xs text-gray-400">Status</label>
                    <select data-reg="status" data-idx="${i}" class="text-xs">
                        <option value="active" ${m.status === 'active' ? 'selected' : ''}>Active</option>
                        <option value="deprecated" ${m.status === 'deprecated' ? 'selected' : ''}>Deprecated</option>
                    </select>
                </div>
                <div>
                    <label class="text-xs text-gray-400">Thinking</label>
                    <select data-reg="supports_thinking" data-idx="${i}" class="text-xs">
                        <option value="true" ${m.supports_thinking ? 'selected' : ''}>Yes</option>
                        <option value="false" ${!m.supports_thinking ? 'selected' : ''}>No</option>
                    </select>
                </div>
                <div>
                    <label class="text-xs text-gray-400">Default Think</label>
                    <select data-reg="default_thinking" data-idx="${i}" class="text-xs">
                        <option value="OFF" ${m.default_thinking === 'OFF' ? 'selected' : ''}>Off</option>
                        <option value="LOW" ${m.default_thinking === 'LOW' ? 'selected' : ''}>Low</option>
                        <option value="MEDIUM" ${m.default_thinking === 'MEDIUM' ? 'selected' : ''}>Medium</option>
                        <option value="HIGH" ${m.default_thinking === 'HIGH' ? 'selected' : ''}>High</option>
                    </select>
                </div>
                <div>
                    <label class="text-xs text-gray-400">Default Temp</label>
                    <input type="number" value="${m.default_temperature}" 
                           data-reg="default_temperature" data-idx="${i}"
                           min="0" max="2" step="0.1" class="text-xs w-16">
                </div>
            </div>
            <div class="flex gap-2 mb-1 items-center">
                <label class="text-xs text-gray-400 flex items-center gap-1">
                    <input type="checkbox" data-reg="requires_thought_signatures" data-idx="${i}"
                           ${m.requires_thought_signatures ? 'checked' : ''}>
                    Requires Thought Signatures
                </label>
            </div>
            <div>
                <label class="text-xs text-gray-400">Notes</label>
                <input type="text" value="${escapeHtml(m.notes || '')}" 
                       data-reg="notes" data-idx="${i}" 
                       class="text-xs w-full" placeholder="Deprecation date, usage notes...">
            </div>
        </div>
        `;
    }

    return `
    <details class="agent-config-card" style="border-left: 3px solid var(--color-muted);">
        <summary class="font-semibold cursor-pointer flex items-center gap-2 hover:text-themeAccent transition-colors">
            <span class="text-xl">🔧</span>
            Model Registry Maintenance
            <span class="text-xs text-gray-400 font-normal">(${modelRegistry.length} models)</span>
        </summary>
        <div class="mt-4 space-y-3" id="registryCards">
            ${cards}
        </div>
        <div class="flex gap-2 mt-4">
            <button onclick="addRegistryModel()" class="btn-secondary text-xs">+ Add Model</button>
            <button onclick="saveRegistryToServer()" class="btn-primary text-xs">💾 Save Registry</button>
        </div>
        <p class="text-xs text-gray-400 mt-2">
            Changes are saved to both the database and models.json.
            Active models appear in agent dropdowns. Deprecated models sort to the bottom.
        </p>
    </details>
    `;
}

function addRegistryModel() {
    modelRegistry.push({
        id: "", label: "New Model", supports_thinking: false,
        default_thinking: "MEDIUM", temperature_range: [0.0, 2.0],
        default_temperature: 1.0, requires_thought_signatures: false,
        status: "active", notes: ""
    });
    renderAgentSettings();
}

function deleteRegistryModel(index) {
    const model = modelRegistry[index];
    const label = model.label || model.id || 'this model';
    if (!confirm(`Remove "${label}" from the registry?`)) return;
    modelRegistry.splice(index, 1);
    renderAgentSettings();
}

async function saveRegistryToServer() {
    const updatedModels = [];
    
    for (let i = 0; i < modelRegistry.length; i++) {
        const getId = (field) => {
            const el = document.querySelector(`[data-reg="${field}"][data-idx="${i}"]`);
            if (!el) return '';
            if (el.type === 'checkbox') return el.checked;
            return el.value;
        };
        
        updatedModels.push({
            id: getId('id').trim(),
            label: getId('label').trim() || getId('id').trim(),
            supports_thinking: getId('supports_thinking') === 'true' || getId('supports_thinking') === true,
            default_thinking: getId('default_thinking'),
            temperature_range: modelRegistry[i].temperature_range || [0.0, 2.0],
            default_temperature: parseFloat(getId('default_temperature')) || 1.0,
            requires_thought_signatures: getId('requires_thought_signatures'),
            status: getId('status'),
            notes: getId('notes')
        });
    }
    
    const emptyIds = updatedModels.filter(m => !m.id);
    if (emptyIds.length > 0) {
        showError('Every model must have an API Model ID.', 'validation_error');
        return;
    }
    
    try {
        await api('/api/models', { method: 'PUT', body: JSON.stringify({ models: updatedModels }) });
        modelRegistry = updatedModels;
        showStatus('Registry saved.', '✅');
        setTimeout(hideStatus, 2000);
        renderAgentSettings();
    } catch (e) {}
}

// ── Config Export/Import ─────────────────────────────────────────

async function exportConfig() {
    try {
        const url = URL.createObjectURL(new Blob([JSON.stringify(await api('/api/export-config'), null, 2)], {type:'application/json'}));
        const a = document.createElement('a'); a.href = url; a.download = 'orchestrator-config.json'; a.click(); URL.revokeObjectURL(url);
    } catch(e){}
}
async function importConfig(e) {
    const file = e.target.files?.[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = async (ev) => {
        try {
            await api('/api/import-config', { method: 'POST', body: ev.target.result });
            await loadAgents(); renderAgentSettings(); showStatus('Imported.', '✅'); setTimeout(hideStatus, 2000);
        } catch(err){}
    }; reader.readAsText(file); e.target.value = '';
}

function showConfirm(t, m, fn) { document.getElementById('confirmTitle').textContent=t; document.getElementById('confirmMessage').textContent=m; document.getElementById('confirmAction').onclick=fn; document.getElementById('confirmModal').classList.remove('hidden'); }
function closeConfirm() { document.getElementById('confirmModal').classList.add('hidden'); }
function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
