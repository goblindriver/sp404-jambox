/* SP-404 JAMBOX — Main Application */

const state = {
    banks: [],
    currentBank: null,
    selectedPad: null,
    playingPad: null,
    fetchJobId: null,
    sidebarOpen: false,
    libraryPath: '',
    vibeDraft: null,
    vibeParsed: null,
    vibeSessionId: null,
};

const audio = document.getElementById('audio-player');

// ── Init ──
async function init() {
    try {
        const data = await api('/api/banks');
        if (!Array.isArray(data)) {
            throw new Error(data.error || 'Failed to load banks');
        }
        state.banks = data;

        renderBankTabs();
        setupBankTabDropZones();
        // Default to Bank B (A is empty/creative)
        switchBank(state.banks.find(b => b.letter === 'b') || state.banks[0]);

        checkSDCard();
        setInterval(checkSDCard, 10000);

        // Wire up footer buttons
        document.getElementById('btn-help').onclick = showTutorial;
        document.getElementById('btn-library').onclick = toggleLibrary;
        document.getElementById('btn-ingest').onclick = ingestDownloads;
        document.getElementById('btn-fetch-all').onclick = () => fetchSamples();
        document.getElementById('btn-build').onclick = buildAll;
        document.getElementById('btn-deploy').onclick = deploy;
        document.getElementById('btn-generate-pattern').onclick = generatePattern;
        document.getElementById('btn-watcher').onclick = toggleWatcher;
        document.getElementById('btn-presets').onclick = togglePresetSidebar;
        document.getElementById('btn-vibe-generate').onclick = generateVibeSuggestions;
        document.getElementById('btn-vibe-populate').onclick = populateBankFromVibe;
        document.getElementById('btn-daily-bank').onclick = generateDailyBank;

        // Load sets and check watcher on startup
        loadSets();
        checkWatcherStatus();

        // Bank edit
        document.getElementById('btn-edit-bank').onclick = openBankEdit;
        document.getElementById('bank-edit-close').onclick = closeBankEdit;
        document.getElementById('btn-save-bank').onclick = saveBankEdit;

        // Tutorial
        document.getElementById('tutorial-close').onclick = hideTutorial;
        document.getElementById('tutorial-go').onclick = hideTutorial;

        // Sidebar close
        document.getElementById('sidebar-close').onclick = () => toggleLibrary(false);

        // Library search
        let searchTimer;
        document.getElementById('library-search').oninput = (e) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => searchLibrary(e.target.value), 300);
        };
        document.getElementById('vibe-prompt').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') generateVibeSuggestions();
        });

        // Audio ended
        audio.onended = () => {
            if (state.playingPad !== null) {
                const el = document.querySelector(`.pad[data-num="${state.playingPad}"]`);
                if (el) el.classList.remove('playing');
                state.playingPad = null;
            }
        };
    } catch (e) {
        toast(`Failed to initialize UI: ${e.message}`, 'error');
        console.error(e);
    }
}

// ── API Helper ──
async function api(url, opts) {
    const resp = await fetch(url, opts);
    const text = await resp.text();
    let data = {};

    if (text) {
        try {
            data = JSON.parse(text);
        } catch (e) {
            throw new Error(`Request failed (${resp.status}): non-JSON response`);
        }
    }

    if (data === null || typeof data !== 'object') {
        throw new Error('Request returned an invalid response');
    }

    if (!resp.ok && !data.error) {
        data.error = `Request failed (${resp.status})`;
    }

    return data;
}

// ── Bank Tabs ──
function renderBankTabs() {
    const nav = document.getElementById('bank-tabs');
    nav.innerHTML = '';
    for (const bank of state.banks) {
        const tab = document.createElement('button');
        tab.className = 'bank-tab';
        tab.dataset.letter = bank.letter;
        tab.style.setProperty('--bank-color', bank.color);
        tab.innerHTML = `<span class="tab-dot" style="background:${bank.color}"></span>${bank.letter.toUpperCase()}`;
        tab.onclick = () => switchBank(bank);
        nav.appendChild(tab);
    }
}

function switchBank(bank) {
    state.currentBank = bank;
    state.selectedPad = null;

    // Update tab highlight
    document.querySelectorAll('.bank-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.letter === bank.letter);
    });

    // Update bank info
    document.getElementById('bank-name').textContent = bank.name;
    document.getElementById('bank-name').style.color = bank.color;
    const meta = [];
    if (bank.bpm) meta.push(`${bank.bpm} BPM`);
    if (bank.key) meta.push(`Key: ${bank.key}`);
    if (bank.notes) meta.push(bank.notes);
    document.getElementById('bank-meta').textContent = meta.join(' · ');

    // Set CSS custom properties for pad colors
    const grid = document.getElementById('pad-grid');
    grid.style.setProperty('--bank-color', bank.color);
    grid.style.setProperty('--bank-color-dim', bank.color + '44');
    grid.style.setProperty('--bank-color-glow', bank.color + '55');

    renderPadGrid(bank);
    setupPadDropZones();
    document.getElementById('pad-detail').classList.add('hidden');
}

// ── Pad Grid ──
function renderPadGrid(bank) {
    const grid = document.getElementById('pad-grid');
    grid.innerHTML = '';
    for (const pad of bank.pads) {
        const el = document.createElement('button');
        el.className = `pad ${pad.status}`;
        el.dataset.num = pad.num;
        el.style.setProperty('--bank-color', bank.color);
        el.style.setProperty('--bank-color-dim', bank.color + '44');
        el.style.setProperty('--bank-color-glow', bank.color + '55');

        const statusIcon = pad.status === 'filled' ? '●' : pad.status === 'staged' ? '◐' : '○';
        el.innerHTML = `
            <span class="pad-num">${pad.num}</span>
            <span class="pad-status-icon">${statusIcon}</span>
            <div class="pad-waveform" id="waveform-${pad.num}"></div>
            <span class="pad-label">${pad.description || 'empty'}</span>
        `;

        el.onclick = () => selectPad(pad);

        // Double click to preview
        el.ondblclick = (e) => {
            e.preventDefault();
            if (pad.status === 'filled') previewPad(bank.letter, pad.num);
        };

        grid.appendChild(el);

        // Load waveform for filled pads
        if (pad.status === 'filled') {
            loadWaveform(bank.letter, pad.num);
        }
    }
}


async function loadWaveform(bankLetter, padNum) {
    try {
        const resp = await fetch(`/api/audio/waveform/${bankLetter}/${padNum}`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.peaks || !data.peaks.length) return;

        const container = document.getElementById(`waveform-${padNum}`);
        if (!container) return;

        container.innerHTML = '';
        for (const peak of data.peaks) {
            const bar = document.createElement('div');
            bar.className = 'bar';
            bar.style.height = `${Math.max(2, peak * 100)}%`;
            container.appendChild(bar);
        }
    } catch (e) {
        // silently fail — waveform is non-critical
    }
}

// ── Pad Selection & Detail ──
function selectPad(pad) {
    state.selectedPad = pad;
    const bank = state.currentBank;
    const detail = document.getElementById('pad-detail');
    detail.classList.remove('hidden');

    // Highlight selected pad
    document.querySelectorAll('.pad').forEach(p => p.classList.remove('selected'));
    document.querySelector(`.pad[data-num="${pad.num}"]`)?.classList.add('selected');

    document.getElementById('detail-pad-num').textContent =
        `${bank.letter.toUpperCase()} · Pad ${pad.num}`;

    const statusEl = document.getElementById('detail-status');
    if (pad.status === 'filled') {
        const kb = Math.round(pad.size / 1024);
        statusEl.textContent = `● Filled (${kb}KB)`;
        statusEl.className = 'detail-status filled';
    } else {
        statusEl.textContent = '○ Empty';
        statusEl.className = 'detail-status empty';
    }

    document.getElementById('detail-desc').value = pad.description;

    const previewBtn = document.getElementById('btn-preview');
    previewBtn.disabled = pad.status !== 'filled';
    previewBtn.onclick = () => previewPad(bank.letter, pad.num);

    document.getElementById('btn-save-desc').onclick = () => saveDescription(bank.letter, pad.num);
    document.getElementById('btn-fetch-pad').onclick = () => fetchSamples(bank.letter, pad.num);
    document.getElementById('detail-close').onclick = () => {
        detail.classList.add('hidden');
        document.querySelectorAll('.pad').forEach(p => p.classList.remove('selected'));
        state.selectedPad = null;
    };
}

async function saveDescription(bankLetter, padNum) {
    const desc = document.getElementById('detail-desc').value.trim();
    try {
        const result = await api(`/api/banks/${bankLetter}/pads/${padNum}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({description: desc}),
        });
        if (!result.ok) {
            toast(result.error || 'Failed to save description', 'error');
            return;
        }

        // Refresh bank data
        const updated = await api(`/api/banks/${bankLetter}`);
        if (updated.error) {
            toast(updated.error, 'error');
            return;
        }
        const bankIdx = state.banks.findIndex(b => b.letter === bankLetter);
        if (bankIdx >= 0) state.banks[bankIdx] = updated;
        if (state.currentBank.letter === bankLetter) {
            state.currentBank = updated;
            renderPadGrid(updated);
        }
        toast('Description saved', 'success');
    } catch (e) {
        toast(`Save failed: ${e.message}`, 'error');
    }
}

// ── Audio Preview ──
function previewPad(bankLetter, padNum) {
    // Stop current
    if (state.playingPad !== null) {
        const prev = document.querySelector(`.pad[data-num="${state.playingPad}"]`);
        if (prev) prev.classList.remove('playing');
        if (state.playingPad === padNum && state.currentBank.letter === bankLetter) {
            audio.pause();
            audio.currentTime = 0;
            state.playingPad = null;
            return;
        }
    }

    audio.src = `/api/audio/preview/${bankLetter}/${padNum}`;
    audio.play().catch(() => {});
    state.playingPad = padNum;
    const el = document.querySelector(`.pad[data-num="${padNum}"]`);
    if (el) el.classList.add('playing');
}

function previewLibraryFile(path) {
    audio.src = `/api/audio/library/${encodeURIComponent(path)}`;
    audio.play().catch(() => {});
}

// ── SD Card Status ──
async function checkSDCard() {
    try {
        const data = await api('/api/sdcard/status');
        const dot = document.querySelector('.sd-dot');
        const text = document.querySelector('.sd-text');
        const deployBtn = document.getElementById('btn-deploy');

        if (data.mounted) {
            dot.className = 'sd-dot mounted';
            text.textContent = `SD: ${data.sample_count || 0} samples · ${data.free_mb || '?'}MB free`;
            deployBtn.disabled = false;
        } else {
            dot.className = 'sd-dot unmounted';
            text.textContent = 'SD: not connected';
            deployBtn.disabled = true;
        }
    } catch (e) {
        // Server not running or error
    }
}

// ── Pipeline Actions ──
async function fetchSamples(bank, pad) {
    const body = {};
    if (bank) body.bank = bank;
    if (pad) body.pad = pad;

    const label = bank ? (pad ? `Bank ${bank.toUpperCase()} Pad ${pad}` : `Bank ${bank.toUpperCase()}`) : 'all banks';
    toast(`Fetching ${label}...`);

    const result = await api('/api/pipeline/fetch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    });

    if (result.error) {
        toast(result.error, 'error');
        return;
    }

    state.fetchJobId = result.job_id;
    showProgress(`Fetching ${label}...`, 12);
    pollFetchStatus(result.job_id);
}

async function pollFetchStatus(jobId) {
    try {
        const data = await api(`/api/pipeline/status/${jobId}`);

        if (data.status === 'running' || data.status === 'starting') {
            showProgress(data.progress || 'Starting...', 55);
            setTimeout(() => pollFetchStatus(jobId), 2000);
        } else {
            showProgress(data.progress || 'Finishing...', 100);
            hideProgress();
            if (data.status === 'done') {
                toast(`Fetch complete: ${data.result}`, 'success');
            } else {
                toast(`Fetch error: ${data.result || data.error || 'Unknown fetch failure'}`, 'error');
            }
            // Refresh bank data
            const banks = await api('/api/banks');
            if (Array.isArray(banks)) {
                state.banks = banks;
                if (state.currentBank) {
                    const updated = banks.find(b => b.letter === state.currentBank.letter);
                    if (updated) switchBank(updated);
                }
            }
        }
    } catch (e) {
        hideProgress();
        toast(`Fetch status failed: ${e.message}`, 'error');
    }
}

async function buildAll() {
    toast('Building PAD_INFO.BIN + patterns...');
    const [padinfo, patterns] = await Promise.all([
        api('/api/pipeline/padinfo', {method: 'POST'}),
        api('/api/pipeline/patterns', {method: 'POST'}),
    ]);
    if (padinfo.ok && patterns.ok) {
        toast('Build complete', 'success');
    } else {
        const message = padinfo.error || patterns.error || 'Build had errors';
        toast(message, 'error');
        console.log(padinfo, patterns);
    }
}

async function generatePattern() {
    if (!state.currentBank) return;
    const variant = prompt('Pattern variant (drum, melody, trio):', 'drum');
    if (!variant) return;
    const bars = parseInt(prompt('Bars:', '2') || '2', 10);
    toast(`Generating ${variant} pattern...`);
    showProgress(`Generating ${variant} pattern...`, 25);
    try {
        const result = await api('/api/pattern/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                variant,
                bars: Number.isFinite(bars) ? bars : 2,
                bpm: state.currentBank.bpm || 120,
                key: state.currentBank.key || '',
                bank: state.currentBank.letter,
                pad: 1,
            }),
        });
        if (result.ok) {
            const message = result.fallback_used
                ? `Starter fallback pattern generated: ${result.path}`
                : `Pattern generated: ${result.path}`;
            toast(message, result.fallback_used ? 'error' : 'success');
        } else {
            toast(result.error || 'Pattern generation failed', 'error');
        }
    } finally {
        hideProgress();
    }
}

async function deploy() {
    toast('Deploying to SD card...');
    const result = await api('/api/pipeline/deploy', {method: 'POST'});
    if (result.ok) {
        toast('Deployed to SD card', 'success');
        checkSDCard();
    } else {
        toast(result.error || 'Deploy failed', 'error');
    }
}

async function generateVibeSuggestions() {
    const promptValue = document.getElementById('vibe-prompt').value.trim();
    if (!promptValue) {
        toast('Enter a vibe prompt first', 'error');
        return;
    }

    const bpmField = document.getElementById('vibe-bpm');
    const keyField = document.getElementById('vibe-key');

    const payload = {
        prompt: promptValue,
        bpm: parseInt(bpmField?.value) || state.currentBank?.bpm || null,
        key: keyField?.value?.trim() || state.currentBank?.key || null,
        bank: state.currentBank?.letter || null,
    };
    toast('Generating vibe suggestions...');
    showProgress('Parsing vibe prompt...', 20);
    try {
        const response = await api('/api/vibe/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            toast(response.error || 'Vibe generation failed', 'error');
            return;
        }
        state.vibeSessionId = response.session_id || null;
        state.vibeDraft = response.result.draft_preset || null;
        state.vibeParsed = response.result.parsed || null;
        renderVibeResults(response.result);
        document.getElementById('btn-vibe-populate').style.display = '';
        document.getElementById('btn-vibe-populate').textContent = 'Apply Draft';
        document.getElementById('vibe-bank-select').style.display = '';
        document.getElementById('vibe-auto-fetch-wrap').classList.remove('hidden');
        if (state.currentBank?.letter) {
            document.getElementById('vibe-bank-select').value = state.currentBank.letter;
        }
        const successMessage = response.result.fallback_used
            ? `Suggestions ready with keyword fallback. Review and apply when ready.`
            : 'Suggestions ready. Review the draft and apply when ready.';
        toast(successMessage, response.result.fallback_used ? 'error' : 'success');
    } finally {
        hideProgress();
    }
}

function renderVibeResults(result) {
    const container = document.getElementById('vibe-results');
    const banks = (result.bank_suggestions || []).map(
        (bank) => `${bank.bank.toUpperCase()} ${bank.name} (${bank.score})`
    );
    const samples = (result.sample_suggestions || []).slice(0, 6).map(
        (sample) => `${sample.rel_path.split('/').pop()} [${sample.score}]`
    );
    const parsed = result.parsed || {};
    const tagPills = [...(parsed.keywords || []), ...(parsed.vibe || []), ...(parsed.genre || [])].slice(0, 8)
        .map(t => `<span class="vibe-tag-pill">${escapeHtml(t)}</span>`).join('');
    const fallbackNote = result.fallback_used
        ? `<div class="vibe-result-note">Fallback used: ${escapeHtml(result.fallback_reason || 'keyword-only parsing')}</div>`
        : '';
    const draftRows = Object.entries(result.draft_preset?.pads || {})
        .sort((a, b) => Number(a[0]) - Number(b[0]))
        .map(([padNum, desc]) => `
            <div class="vibe-draft-row" data-pad="${padNum}">
                <span class="vibe-draft-pad">Pad ${padNum}</span>
                <input class="vibe-draft-input" data-pad="${padNum}" value="${escapeHtml(desc)}" />
                <button class="btn btn-sm" onclick="swapVibeDraftPads(${padNum}, -1)" ${Number(padNum) === 1 ? 'disabled' : ''}>↑</button>
                <button class="btn btn-sm" onclick="swapVibeDraftPads(${padNum}, 1)" ${Number(padNum) === 12 ? 'disabled' : ''}>↓</button>
                <button class="btn btn-sm" onclick="resetVibeDraftPad(${padNum})">Reset</button>
                <button class="btn btn-sm" onclick="clearVibeDraftPad(${padNum})">Clear</button>
            </div>
        `).join('');
    const parsedRows = [
        ["type_code", "Type Code", parsed.type_code || ""],
        ["playability", "Playability", parsed.playability || ""],
        ["keywords", "Keywords", (parsed.keywords || []).join(", ")],
        ["genre", "Genre", (parsed.genre || []).join(", ")],
        ["vibe", "Vibe", (parsed.vibe || []).join(", ")],
        ["texture", "Texture", (parsed.texture || []).join(", ")],
        ["energy", "Energy", (parsed.energy || []).join(", ")],
        ["rationale", "Rationale", parsed.rationale || ""],
    ].map(([field, label, value]) => `
        <label class="vibe-parse-row">
            <span>${label}</span>
            <input class="vibe-parse-input" data-field="${field}" value="${escapeHtml(value)}" />
        </label>
    `).join('');
    container.innerHTML = `
        <div class="vibe-result-card">
            <strong>Parsed Tags</strong><br>${tagPills || 'No tags parsed'}${fallbackNote}
        </div>
        <div class="vibe-result-card">
            <strong>Best Banks</strong><br>${banks.join('<br>') || 'No matches'}
        </div>
        <div class="vibe-result-card vibe-result-wide">
            <strong>Top Samples</strong><br>${samples.join('<br>') || 'No sample matches'}
        </div>
        <div class="vibe-result-card vibe-result-wide">
            <strong>Editable Parse</strong>
            <div class="vibe-parse-grid">${parsedRows}</div>
        </div>
        <div class="vibe-result-card vibe-result-wide">
            <strong>Draft Pads</strong>
            <div class="vibe-draft-list">${draftRows || 'No draft available'}</div>
        </div>
    `;
}

async function populateBankFromVibe() {
    if (!state.vibeDraft) {
        toast('Generate suggestions first', 'error');
        return;
    }

    const bank = document.getElementById('vibe-bank-select').value;
    const autoFetch = document.getElementById('vibe-auto-fetch')?.checked !== false;
    const draftPreset = collectVibeDraftPreset();
    const payload = {
        session_id: state.vibeSessionId,
        preset: draftPreset,
        reviewed_parsed: collectReviewedParsed(),
        bank: bank,
        fetch: autoFetch,
    };

    toast(`Applying draft to Bank ${bank.toUpperCase()}...`);
    document.getElementById('btn-vibe-populate').disabled = true;
    document.getElementById('btn-vibe-populate').textContent = 'Working...';
    showProgress(`Applying Bank ${bank.toUpperCase()} draft...`, 18);

    const response = await api('/api/vibe/apply-bank', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        toast(response.error || 'Populate failed', 'error');
        document.getElementById('btn-vibe-populate').disabled = false;
        document.getElementById('btn-vibe-populate').textContent = 'Apply Draft';
        hideProgress();
        return;
    }

    // Poll job status
    const jobId = response.job_id;
    const pollInterval = setInterval(async () => {
        try {
            const status = await api(`/api/vibe/populate-status/${jobId}`);
            document.getElementById('btn-vibe-populate').textContent = status.progress || 'Working...';
            showProgress(status.progress || 'Applying vibe draft...', vibeProgressPercent(status.status));

            if (status.status === 'done') {
                clearInterval(pollInterval);
                document.getElementById('btn-vibe-populate').disabled = false;
                document.getElementById('btn-vibe-populate').textContent = 'Apply Draft';
                hideProgress();
                const doneMessage = status.fallback_used
                    ? `Bank ${bank.toUpperCase()} applied with fallback parsing. ${status.fetched || ''}`
                    : `Bank ${bank.toUpperCase()} applied. ${status.fetched || ''}`;
                toast(doneMessage.trim(), status.fallback_used ? 'error' : 'success');
                await refreshBanks();
                const updated = state.banks.find((item) => item.letter === bank);
                if (updated) switchBank(updated);
            } else if (status.status === 'error') {
                clearInterval(pollInterval);
                document.getElementById('btn-vibe-populate').disabled = false;
                document.getElementById('btn-vibe-populate').textContent = 'Apply Draft';
                hideProgress();
                toast(`Error: ${status.progress}`, 'error');
            }
        } catch (e) {
            clearInterval(pollInterval);
            document.getElementById('btn-vibe-populate').disabled = false;
            document.getElementById('btn-vibe-populate').textContent = 'Apply Draft';
            hideProgress();
            toast(`Populate status failed: ${e.message}`, 'error');
        }
    }, 2000);
}

async function generateDailyBank() {
    if (!state.currentBank) return;
    toast('Generating daily bank...');
    const result = await api('/api/presets/daily', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({bank: state.currentBank.letter}),
    });
    if (result.ok) {
        await refreshBanks();
        await loadSets();
        toast(`Daily bank loaded from ${result.ref}`, 'success');
    } else {
        toast(result.error || 'Daily bank generation failed', 'error');
    }
}

function showProgress(text = 'Working...', percent = 18) {
    document.getElementById('progress-bar').classList.remove('hidden');
    document.getElementById('progress-text').textContent = text;
    document.getElementById('progress-fill').style.width = `${Math.max(0, Math.min(100, percent))}%`;
}

function hideProgress() {
    document.getElementById('progress-bar').classList.add('hidden');
    document.getElementById('progress-fill').style.width = '0%';
}

// ── Library Sidebar ──
state.activeTags = [];
state.tagData = null;
state.sidebarTab = 'browse';

function toggleLibrary(forceState) {
    const sidebar = document.getElementById('sidebar');
    const open = typeof forceState === 'boolean' ? forceState : sidebar.classList.contains('hidden');
    sidebar.classList.toggle('hidden', !open);
    state.sidebarOpen = open;
    if (open) {
        document.getElementById('preset-sidebar')?.classList.add('hidden');
        document.getElementById('music-sidebar')?.classList.add('hidden');
        if (state.sidebarTab === 'browse' && state.libraryPath === '') {
            browseLibrary('');
        } else if (state.sidebarTab === 'tags' && !state.tagData) {
            loadTagCloud();
        }
    }
}

function switchSidebarTab(tab) {
    state.sidebarTab = tab;
    document.querySelectorAll('.sidebar-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('tab-browse').classList.toggle('hidden', tab !== 'browse');
    document.getElementById('tab-tags').classList.toggle('hidden', tab !== 'tags');
    if (tab === 'tags' && !state.tagData) loadTagCloud();
}

async function browseLibrary(path) {
    state.libraryPath = path;
    const url = path ? `/api/library/browse/${encodeURIComponent(path)}` : '/api/library/browse';
    const data = await api(url);
    renderLibraryBrowser(data, path);
}

async function searchLibrary(query) {
    if (!query || query.length < 2) {
        browseLibrary(state.libraryPath || '');
        return;
    }
    const data = await api(`/api/library/search?q=${encodeURIComponent(query)}`);
    renderSearchResults(data.results);
}

function renderLibraryBrowser(data, path) {
    const container = document.getElementById('library-browser');
    let html = '';

    // Breadcrumb
    const parts = path ? path.split('/') : [];
    html += '<div class="lib-breadcrumb">';
    html += `<a onclick="browseLibrary('')">Library</a>`;
    let cumPath = '';
    for (const part of parts) {
        cumPath += (cumPath ? '/' : '') + part;
        const p = cumPath;
        html += ` / <a onclick="browseLibrary('${p}')">${part}</a>`;
    }
    html += '</div>';

    // Directories
    for (const dir of data.dirs) {
        html += `<div class="lib-item lib-dir" onclick="browseLibrary('${dir.path}')">
            <span>📁 ${dir.name}</span>
            <span class="lib-count">${dir.count}</span>
        </div>`;
    }

    // Files
    for (const file of data.files) {
        const kb = Math.round(file.size / 1024);
        html += `<div class="lib-item lib-file" data-library-path="${file.path}">
            <span class="lib-drag-handle" title="Drag to a pad">⠿</span>
            <button class="lib-play" onclick="previewLibraryFile('${file.path}')" title="Preview">▶</button>
            <span class="lib-name" title="${file.name}">${truncate(file.name, 28)}</span>
            <span class="lib-size">${kb}KB</span>
            <button class="lib-assign" onclick="assignFromLibrary('${file.path}')" title="Assign to selected pad">Assign</button>
        </div>`;
    }

    if (data.total_files > 200) {
        html += `<div class="lib-item" style="color:var(--text-muted)">Showing 200 of ${data.total_files} files — use search to narrow down</div>`;
    }

    container.innerHTML = html;
    setupLibraryDrag(container);
}

function renderSearchResults(results) {
    const container = document.getElementById('library-browser');
    if (!results.length) {
        container.innerHTML = '<div class="lib-item" style="color:var(--text-muted)">No results</div>';
        return;
    }
    let html = '<div class="lib-breadcrumb">Search results</div>';
    for (const r of results) {
        const name = r.path.split('/').pop();
        html += `<div class="lib-item lib-file" data-library-path="${r.path}">
            <span class="lib-drag-handle" title="Drag to a pad">⠿</span>
            <button class="lib-play" onclick="previewLibraryFile('${r.path}')" title="Preview">▶</button>
            <span class="lib-name" title="${r.path}">${truncate(name, 23)}</span>
            <span class="lib-size" style="color:var(--accent)">${r.score}pts</span>
            <button class="lib-assign" onclick="assignFromLibrary('${r.path}')" title="Assign">Assign</button>
        </div>`;
    }
    container.innerHTML = html;
    setupLibraryDrag(container);
}

async function assignFromLibrary(filepath) {
    if (!state.currentBank || !state.selectedPad) {
        toast('Select a pad first', 'error');
        return;
    }
    assignToPad(state.currentBank.letter, state.selectedPad.num, filepath);
}

function setupLibraryDrag(container) {
    container.querySelectorAll('.lib-file[data-library-path]').forEach(el => {
        makeDraggable(el, el.dataset.libraryPath);
    });
}

// ── Tag Cloud (dimension-aware) ──

// Full type code names for tooltips
const TYPE_CODE_NAMES = {
    KIK:'Kick', SNR:'Snare', CLP:'Clap', HAT:'Hi-Hat', PRC:'Percussion',
    CYM:'Cymbal', RIM:'Rimshot', BRK:'Break/Loop', DRM:'Drum',
    BAS:'Bass', GTR:'Guitar', KEY:'Keys/Piano', SYN:'Synth', PAD:'Pad',
    STR:'Strings', BRS:'Brass', PLK:'Pluck', WND:'Woodwind', VOX:'Vocal',
    SMP:'Sample', FX:'FX', AMB:'Ambient', FLY:'Foley', TPE:'Tape/Vinyl',
    RSR:'Riser', SFX:'Stinger',
};

// Dimension-aware active filters: {dimension: [values]}
state.activeFilters = {};

async function loadTagCloud() {
    const data = await api('/api/library/tags');
    if (data.error && !data.tags) {
        document.getElementById('tag-sections').innerHTML =
            `<div style="color:var(--text-muted);padding:20px;text-align:center">
                Run <code>python scripts/tag_library.py</code> to build the tag database
            </div>`;
        return;
    }
    state.tagData = data;
    renderTagCloud();
}

function renderTagCloud() {
    const data = state.tagData;
    const sections = document.getElementById('tag-sections');
    let html = '';

    html += renderTagSection('Type', data.type_codes, 'type_code');
    html += renderTagSection('Vibe', data.vibes, 'vibe');
    html += renderTagSection('Texture', data.textures, 'texture');
    html += renderTagSection('Genre', data.genres, 'genre');
    html += renderTagSection('Energy', data.energies, 'energy');
    html += renderTagSection('Source', data.sources, 'source');
    html += renderTagSection('Playability', data.playabilities, 'playability');

    const bpmTags = {};
    for (const [bpm, count] of Object.entries(data.bpms || {})) {
        bpmTags[bpm + 'bpm'] = count;
    }
    html += renderTagSection('BPM', bpmTags, 'bpm');

    sections.innerHTML = html;
    renderActiveTags();
}

function renderTagSection(title, tagMap, dimension) {
    if (!tagMap || Object.keys(tagMap).length === 0) return '';

    const entries = Object.entries(tagMap).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;
    const active = state.activeFilters[dimension] || [];

    let html = `<div class="tag-section">
        <div class="tag-section-title">${title}</div>
        <div class="tag-cloud">`;

    for (const [tag, count] of entries) {
        const ratio = count / maxCount;
        const size = ratio > 0.7 ? 5 : ratio > 0.4 ? 4 : ratio > 0.2 ? 3 : ratio > 0.1 ? 2 : 1;
        const isActive = active.includes(tag);
        const tooltip = TYPE_CODE_NAMES[tag] ? `${TYPE_CODE_NAMES[tag]} (${count})` : `${count} samples`;
        html += `<span class="tag tag-size-${size} tag-dim-${dimension} ${isActive ? 'active' : ''}"
                       onclick="toggleTag('${dimension}','${tag}')"
                       title="${tooltip}">${tag}<span class="tag-count">${count}</span></span>`;
    }

    html += '</div></div>';
    return html;
}

function toggleTag(dimension, tag) {
    if (!state.activeFilters[dimension]) {
        state.activeFilters[dimension] = [];
    }
    const arr = state.activeFilters[dimension];
    const idx = arr.indexOf(tag);
    if (idx >= 0) {
        arr.splice(idx, 1);
        if (arr.length === 0) delete state.activeFilters[dimension];
    } else {
        arr.push(tag);
    }
    renderTagCloud();
    if (Object.keys(state.activeFilters).length > 0) {
        fetchByTags();
    } else {
        document.getElementById('tag-results').innerHTML = '';
    }
}

function renderActiveTags() {
    const container = document.getElementById('active-tags');
    const allFilters = [];
    for (const [dim, vals] of Object.entries(state.activeFilters)) {
        for (const v of vals) {
            allFilters.push({dim, val: v});
        }
    }
    if (allFilters.length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = allFilters.map(f =>
        `<span class="active-tag tag-dim-${f.dim}" onclick="toggleTag('${f.dim}','${f.val}')">${f.val}<span class="remove">&times;</span></span>`
    ).join('');
}

async function fetchByTags() {
    const params = [];
    for (const [dim, vals] of Object.entries(state.activeFilters)) {
        // BPM uses flat tag search
        if (dim === 'bpm') {
            for (const v of vals) params.push(`tag=${encodeURIComponent(v)}`);
        } else {
            for (const v of vals) params.push(`${dim}=${encodeURIComponent(v)}`);
        }
    }
    const data = await api(`/api/library/by-tag?${params.join('&')}&limit=50`);
    renderTagResults(data);
}

function renderTagResults(data) {
    const container = document.getElementById('tag-results');
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="tag-results-header">No matches</div>';
        return;
    }

    let html = `<div class="tag-results-header">${data.total} matches</div>`;
    for (const r of data.results) {
        const dur = r.duration ? `${r.duration.toFixed(1)}s` : '';
        const code = r.type_code || '';
        const meta = [code, r.bpm ? r.bpm + 'bpm' : '', r.key || '', dur].filter(Boolean).join(' · ');
        html += `<div class="lib-item lib-file" data-library-path="${r.path}">
            <span class="lib-drag-handle" title="Drag to a pad">⠿</span>
            <button class="lib-play" onclick="previewLibraryFile('${r.path}')" title="Preview">▶</button>
            <span class="lib-name" title="${r.path}">${truncate(r.name, 26)}</span>
            <span class="lib-size">${meta}</span>
        </div>`;
    }
    container.innerHTML = html;
    setupLibraryDrag(container);
}

// ── Toast ──
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast show ${type}`;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.className = 'toast hidden', 3000);
}

// ── Utils ──
function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
}

function truncate(str, len) {
    return str.length > len ? str.slice(0, len) + '...' : str;
}

function collectVibeDraftPreset() {
    const draft = JSON.parse(JSON.stringify(state.vibeDraft || {}));
    draft.pads = {};
    document.querySelectorAll('.vibe-draft-input').forEach((input) => {
        draft.pads[Number(input.dataset.pad)] = input.value.trim();
    });
    return draft;
}

function getVibeDraftInput(padNum) {
    return document.querySelector(`.vibe-draft-input[data-pad="${padNum}"]`);
}

function collectReviewedParsed() {
    const reviewed = JSON.parse(JSON.stringify(state.vibeParsed || {}));
    document.querySelectorAll('.vibe-parse-input').forEach((input) => {
        const field = input.dataset.field;
        const value = input.value.trim();
        if (["keywords", "genre", "vibe", "texture", "energy"].includes(field)) {
            reviewed[field] = value
                ? value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean)
                : [];
        } else if (field === "rationale") {
            reviewed[field] = value;
        } else {
            reviewed[field] = value || null;
        }
    });
    return reviewed;
}

function swapVibeDraftPads(padNum, direction) {
    const otherPad = padNum + direction;
    if (otherPad < 1 || otherPad > 12) return;
    const current = getVibeDraftInput(padNum);
    const other = getVibeDraftInput(otherPad);
    if (!current || !other) return;
    const temp = current.value;
    current.value = other.value;
    other.value = temp;
}

function resetVibeDraftPad(padNum) {
    const input = getVibeDraftInput(padNum);
    if (!input) return;
    input.value = state.vibeDraft?.pads?.[padNum] || state.vibeDraft?.pads?.[String(padNum)] || '';
}

function clearVibeDraftPad(padNum) {
    const input = getVibeDraftInput(padNum);
    if (input) input.value = '';
}

function vibeProgressPercent(status) {
    return {
        starting: 8,
        generating: 18,
        reviewed: 25,
        saving: 45,
        loading: 65,
        fetching: 82,
        done: 100,
        error: 100,
    }[status] || 20;
}

// ── Tutorial ──
async function showTutorial() {
    document.getElementById('tutorial-overlay').classList.remove('hidden');

    // Load stats
    try {
        const stats = await api('/api/library/stats');
        const filledPads = state.banks.reduce((sum, b) =>
            sum + b.pads.filter(p => p.status === 'filled').length, 0);

        document.getElementById('tutorial-stats').innerHTML = `
            <div class="stat-item">
                <span class="stat-value">${stats.total.toLocaleString()}</span>
                <span class="stat-label">samples in library</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">${filledPads}/120</span>
                <span class="stat-label">pads filled</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">${stats.pending_packs}</span>
                <span class="stat-label">packs to ingest</span>
            </div>
        `;
    } catch (e) {
        document.getElementById('tutorial-stats').innerHTML = '';
    }
}

function hideTutorial() {
    document.getElementById('tutorial-overlay').classList.add('hidden');
    localStorage.setItem('jambox-tutorial-seen', '1');
}

// ── Ingest Downloads ──
async function ingestDownloads() {
    toast('Ingesting sample packs from Downloads...');
    document.getElementById('btn-ingest').disabled = true;

    try {
        const result = await api('/api/pipeline/ingest', { method: 'POST' });
        if (result.ok) {
            toast(result.summary || 'Ingest complete', 'success');
        } else {
            toast(result.error || 'Ingest failed', 'error');
        }
    } catch (e) {
        toast('Ingest error: ' + e.message, 'error');
    }

    document.getElementById('btn-ingest').disabled = false;
}

// ── File Watcher ──
let watcherPolling = null;

async function checkWatcherStatus() {
    try {
        const result = await api('/api/pipeline/watcher/status');
        updateWatcherUI(result.running, result.recent || []);
    } catch (e) {
        // Watcher API not available
    }
}

function updateWatcherUI(running, recent) {
    const btn = document.getElementById('btn-watcher');
    const dot = document.getElementById('watcher-dot');

    if (running) {
        btn.classList.add('watching');
        dot.classList.add('active');
    } else {
        btn.classList.remove('watching');
        dot.classList.remove('active');
    }

    // Update feed if visible
    const feed = document.getElementById('watcher-feed');
    if (!feed.classList.contains('hidden') && recent.length > 0) {
        renderWatcherFeed(recent);
    }
}

async function toggleWatcher() {
    const btn = document.getElementById('btn-watcher');
    const isRunning = btn.classList.contains('watching');

    try {
        if (isRunning) {
            await api('/api/pipeline/watcher/stop', { method: 'POST' });
            toast('Watcher stopped', 'success');
            btn.classList.remove('watching');
            document.getElementById('watcher-dot').classList.remove('active');
            stopWatcherPolling();
        } else {
            toast('Starting file watcher...');
            const result = await api('/api/pipeline/watcher/start', { method: 'POST' });
            if (result.ok) {
                toast('Watcher active — monitoring ~/Downloads', 'success');
                btn.classList.add('watching');
                document.getElementById('watcher-dot').classList.add('active');
                startWatcherPolling();
            } else {
                toast(result.error || 'Failed to start watcher', 'error');
            }
        }
    } catch (e) {
        toast('Watcher error: ' + e.message, 'error');
    }
}

function startWatcherPolling() {
    if (watcherPolling) return;
    watcherPolling = setInterval(async () => {
        try {
            const result = await api('/api/pipeline/watcher/status');
            updateWatcherUI(result.running, result.recent || []);
        } catch (e) {}
    }, 5000);
}

function stopWatcherPolling() {
    if (watcherPolling) {
        clearInterval(watcherPolling);
        watcherPolling = null;
    }
}

function toggleWatcherFeed() {
    const feed = document.getElementById('watcher-feed');
    if (feed.classList.contains('hidden')) {
        feed.classList.remove('hidden');
        // Load latest
        checkWatcherStatus().then(() => {
            api('/api/pipeline/watcher/status').then(result => {
                renderWatcherFeed(result.recent || []);
            });
        });
        startWatcherPolling();
    } else {
        feed.classList.add('hidden');
    }
}

function renderWatcherFeed(entries) {
    const list = document.getElementById('watcher-feed-list');
    if (!entries.length) {
        list.innerHTML = '<div class="watcher-empty">No recent activity</div>';
        return;
    }
    list.innerHTML = entries.slice().reverse().map(e => {
        const time = new Date(e.timestamp).toLocaleTimeString();
        const cats = e.categories ? Object.entries(e.categories).map(
            ([cat, n]) => `${cat.split('/').pop()}: ${n}`
        ).join(', ') : '';
        return `<div class="watcher-entry">
            <div class="watcher-entry-time">${time}</div>
            <div class="watcher-entry-name">${e.source}</div>
            <div class="watcher-entry-detail">${e.samples} sample${e.samples !== 1 ? 's' : ''} ${cats ? '— ' + cats : ''}</div>
        </div>`;
    }).join('');
}

// ── Disk Panel ──

async function toggleDiskPanel() {
    const panel = document.getElementById('disk-panel');
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        loadDiskReport();
    } else {
        panel.classList.add('hidden');
    }
}

function closeDiskPanel() {
    document.getElementById('disk-panel').classList.add('hidden');
}

async function loadDiskReport() {
    const el = document.getElementById('disk-report');
    try {
        const d = await api('/api/pipeline/disk-report');
        const freeClass = d.disk_free < 500 * 1024 * 1024 ? 'disk-warn' : 'disk-ok';
        el.innerHTML = `
            <div>Disk free: <span class="${freeClass}">${d.disk_free_str}</span></div>
            <div>Downloads: ${d.downloads_str}</div>
            <div>Cleanable: <strong>${d.cleanable_str}</strong> (${d.cleanable_count} ingested items)</div>
            <div>Archive (_RAW-DOWNLOADS): ${d.archive_str}</div>
            <div>Sample library: ${d.library_str}</div>
        `;
        document.getElementById('downloads-path-input').value = d.downloads_path;
    } catch (e) {
        el.innerHTML = '<div style="color:var(--text-dim)">Could not load disk report</div>';
    }
}

async function runCleanup(purgeArchive) {
    const action = purgeArchive ? 'Clean Downloads + purge archive' : 'Clean Downloads';
    if (!confirm(`${action}? This permanently deletes already-ingested files.`)) return;

    toast('Cleaning up...');
    try {
        const result = await api('/api/pipeline/cleanup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({purge_archive: purgeArchive}),
        });
        if (result.ok) {
            toast(`Freed ${result.freed_str} (${result.count} items removed)`, 'success');
            loadDiskReport();
        } else {
            toast(result.error || 'Cleanup failed', 'error');
        }
    } catch (e) {
        toast('Cleanup failed: ' + e.message, 'error');
    }
}

async function setDownloadsPath() {
    const path = document.getElementById('downloads-path-input').value.trim();
    if (!path) return;
    try {
        const result = await api('/api/pipeline/downloads-path', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path}),
        });
        if (result.ok) {
            toast(`Downloads path set to: ${result.path}`, 'success');
        } else {
            toast(result.error || 'Invalid path', 'error');
        }
    } catch (e) {
        toast('Failed: ' + e.message, 'error');
    }
}

// Also make the watcher button show the feed on right-click
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-watcher');
    if (btn) {
        btn.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            toggleWatcherFeed();
        });
    }
});

// ── Bank Edit ──
function openBankEdit() {
    if (!state.currentBank) return;
    const b = state.currentBank;
    document.getElementById('edit-bank-letter').textContent = b.letter.toUpperCase();
    document.getElementById('edit-bank-name').value = b.name || '';
    document.getElementById('edit-bank-bpm').value = b.bpm || '';
    document.getElementById('edit-bank-key').value = b.key || '';
    document.getElementById('edit-bank-notes').value = b.notes || '';
    document.getElementById('bank-edit-modal').classList.remove('hidden');
}

function closeBankEdit() {
    document.getElementById('bank-edit-modal').classList.add('hidden');
}

async function saveBankEdit() {
    const letter = state.currentBank.letter;
    const data = {
        name: document.getElementById('edit-bank-name').value.trim(),
        bpm: document.getElementById('edit-bank-bpm').value || null,
        key: document.getElementById('edit-bank-key').value.trim() || null,
        notes: document.getElementById('edit-bank-notes').value.trim(),
    };

    try {
        const result = await api(`/api/banks/${letter}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data),
        });
        if (!result.ok) {
            toast(result.error || 'Failed to save bank settings', 'error');
            return;
        }

        closeBankEdit();
        const updated = await api(`/api/banks/${letter}`);
        if (updated.error) {
            toast(updated.error, 'error');
            return;
        }
        const idx = state.banks.findIndex(b => b.letter === letter);
        if (idx >= 0) state.banks[idx] = updated;
        switchBank(updated);
        toast('Bank settings saved', 'success');
    } catch (e) {
        toast(`Bank save failed: ${e.message}`, 'error');
    }
}

// ── Drag & Drop ──
function setupPadDropZones() {
    const pads = document.querySelectorAll('.pad');
    pads.forEach(el => {
        el.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            el.classList.add('drag-over');
        });
        el.addEventListener('dragleave', () => {
            el.classList.remove('drag-over');
        });
        el.addEventListener('drop', (e) => {
            e.preventDefault();
            el.classList.remove('drag-over');
            const padNum = parseInt(el.dataset.num);

            // Check for library drag first
            const libraryPath = e.dataTransfer.getData('application/x-library-path');
            if (libraryPath) {
                assignToPad(state.currentBank.letter, padNum, libraryPath);
                return;
            }

            // OS file drop
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                uploadToPad(state.currentBank.letter, padNum, e.dataTransfer.files[0]);
            }
        });
    });
}

async function assignToPad(bankLetter, padNum, libraryPath) {
    toast(`Assigning to ${bankLetter.toUpperCase()} Pad ${padNum}...`);
    try {
        const result = await api('/api/audio/assign', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({bank: bankLetter, pad: padNum, library_path: libraryPath}),
        });
        if (result.ok) {
            toast(result.message, 'success');
            // Refresh bank
            const updated = await api(`/api/banks/${bankLetter}`);
            const idx = state.banks.findIndex(b => b.letter === bankLetter);
            if (idx >= 0) state.banks[idx] = updated;
            if (state.currentBank.letter === bankLetter) {
                state.currentBank = updated;
                renderPadGrid(updated);
                setupPadDropZones();
                if (state.selectedPad && state.selectedPad.num === padNum) {
                    const pad = updated.pads.find(p => p.num === padNum);
                    if (pad) selectPad(pad);
                }
            }
        } else {
            toast(result.error || 'Assign failed', 'error');
        }
    } catch (e) {
        toast('Assign error: ' + e.message, 'error');
    }
}

async function uploadToPad(bankLetter, padNum, file) {
    const audioExts = ['.wav', '.aif', '.aiff', '.mp3', '.flac', '.ogg', '.m4a'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!audioExts.includes(ext)) {
        toast(`Unsupported format: ${ext}`, 'error');
        return;
    }

    toast(`Uploading ${file.name}...`);
    const formData = new FormData();
    formData.append('bank', bankLetter);
    formData.append('pad', padNum);
    formData.append('file', file);

    try {
        const resp = await fetch('/api/audio/upload', { method: 'POST', body: formData });
        const result = await resp.json();
        if (result.ok) {
            toast(result.message, 'success');
            const updated = await api(`/api/banks/${bankLetter}`);
            const idx = state.banks.findIndex(b => b.letter === bankLetter);
            if (idx >= 0) state.banks[idx] = updated;
            if (state.currentBank.letter === bankLetter) {
                state.currentBank = updated;
                renderPadGrid(updated);
                setupPadDropZones();
                if (state.selectedPad && state.selectedPad.num === padNum) {
                    const pad = updated.pads.find(p => p.num === padNum);
                    if (pad) selectPad(pad);
                }
            }
        } else {
            toast(result.error || 'Upload failed', 'error');
        }
    } catch (e) {
        toast('Upload error: ' + e.message, 'error');
    }
}

function makeDraggable(el, libraryPath) {
    el.draggable = true;
    el.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('application/x-library-path', libraryPath);
        e.dataTransfer.effectAllowed = 'copy';
        el.classList.add('dragging');
    });
    el.addEventListener('dragend', () => {
        el.classList.remove('dragging');
        document.querySelectorAll('.pad.drag-over').forEach(p => p.classList.remove('drag-over'));
    });
}

// ═══════════════════════════════════════════════════════
// ── Presets & Sets ──
// ═══════════════════════════════════════════════════════

let presetData = null;
let presetCategory = null;
let presetPreviewRef = null;

function togglePresetSidebar() {
    const sidebar = document.getElementById('preset-sidebar');
    const isOpen = !sidebar.classList.contains('hidden');
    if (isOpen) {
        closePresetSidebar();
    } else {
        document.getElementById('sidebar')?.classList.add('hidden');
        document.getElementById('music-sidebar')?.classList.add('hidden');
        sidebar.classList.remove('hidden');
        if (!presetData) loadPresets();
    }
}

function closePresetSidebar() {
    document.getElementById('preset-sidebar').classList.add('hidden');
}

function switchPresetTab(tab) {
    document.querySelectorAll('#preset-sidebar .sidebar-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('preset-tab-browse')?.classList.toggle('hidden', tab !== 'browse');
    document.getElementById('preset-tab-search')?.classList.toggle('hidden', tab !== 'search');
    document.getElementById('preset-preview')?.classList.add('hidden');
}

async function loadPresets(category) {
    try {
        // Load categories
        const cats = await api('/api/presets/categories');
        renderPresetCategories(cats.categories);

        // Load presets
        let url = '/api/presets';
        if (category) url += `?category=${category}`;
        const data = await api(url);
        presetData = data.presets;
        renderPresetCards(data.presets, 'preset-list');
    } catch (e) {
        document.getElementById('preset-list').innerHTML =
            '<div style="padding:16px;color:var(--text-dim)">Error loading presets</div>';
    }
}

function renderPresetCategories(categories) {
    const el = document.getElementById('preset-categories');
    let html = `<button class="preset-cat-pill ${!presetCategory ? 'active' : ''}" onclick="filterPresetCategory(null)">All</button>`;
    for (const cat of categories) {
        if (cat.count === 0) continue;
        const active = presetCategory === cat.name ? 'active' : '';
        html += `<button class="preset-cat-pill ${active}" onclick="filterPresetCategory('${cat.name}')">${cat.name} (${cat.count})</button>`;
    }
    el.innerHTML = html;
}

function filterPresetCategory(cat) {
    presetCategory = cat;
    loadPresets(cat);
}

function renderPresetCards(presets, elId) {
    const el = document.getElementById(elId);
    if (!presets || !presets.length) {
        el.innerHTML = '<div style="padding:16px;color:var(--text-dim)">No presets found</div>';
        return;
    }
    el.innerHTML = presets.map(p => `
        <div class="preset-card" draggable="true"
             ondragstart="dragPreset(event, '${p.ref}')"
             onclick="previewPreset('${p.ref}')">
            <div class="preset-card-name">${p.name}</div>
            <div class="preset-card-meta">${p.bpm || '—'} BPM · ${p.key || '—'} · ${p.category}</div>
            ${p.vibe ? `<div class="preset-card-vibe">${p.vibe.substring(0, 60)}</div>` : ''}
            ${p.tags?.length ? `<div class="preset-card-tags">${p.tags.slice(0, 6).map(t => `<span class="preset-tag">${t}</span>`).join('')}</div>` : ''}
        </div>
    `).join('');
}

async function previewPreset(ref) {
    const data = await api(`/api/presets/${ref}`);
    if (!data || data.error) return;

    presetPreviewRef = ref;

    // Hide browse/search, show preview
    document.getElementById('preset-tab-browse')?.classList.add('hidden');
    document.getElementById('preset-tab-search')?.classList.add('hidden');
    const preview = document.getElementById('preset-preview');
    preview.classList.remove('hidden');

    // Header
    document.getElementById('preset-preview-header').innerHTML = `
        <h4>${data.name}</h4>
        <div style="font-size:11px;color:var(--text-dim)">${data.bpm || '—'} BPM · ${data.key || '—'} · ${data.category || ''}</div>
        ${data.vibe ? `<div style="font-size:11px;color:var(--text-muted);font-style:italic;margin-top:4px">${data.vibe}</div>` : ''}
        ${data.tags?.length ? `<div style="margin-top:6px">${data.tags.map(t => `<span class="preset-tag">${t}</span>`).join(' ')}</div>` : ''}
    `;

    // Pad grid
    const padsEl = document.getElementById('preset-preview-pads');
    let html = '';
    for (let i = 1; i <= 12; i++) {
        const desc = data.pads?.[i] || data.pads?.[String(i)] || '';
        html += `<div class="preset-preview-pad">
            <div class="preset-preview-pad-num">${i}</div>
            <div class="preset-preview-pad-desc">${desc || '—'}</div>
        </div>`;
    }
    padsEl.innerHTML = html;
}

function closePresetPreview() {
    document.getElementById('preset-preview').classList.add('hidden');
    const tab = document.querySelector('#preset-sidebar .sidebar-tab.active');
    const tabName = tab?.dataset.tab || 'browse';
    document.getElementById(`preset-tab-${tabName}`)?.classList.remove('hidden');
    presetPreviewRef = null;
}

async function loadPreviewedPreset() {
    if (!presetPreviewRef || !state.currentBank) return;
    const bank = state.currentBank.letter;

    try {
        const result = await api('/api/presets/load', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ref: presetPreviewRef, bank}),
        });
        if (result.ok) {
            toast(`Loaded "${result.name}" to Bank ${bank.toUpperCase()}`, 'success');
            closePresetPreview();
            closePresetSidebar();
            await refreshBanks();
        } else {
            toast(result.error || 'Load failed', 'error');
        }
    } catch (e) {
        toast('Load failed: ' + e.message, 'error');
    }
}

// Drag preset to bank tab
function dragPreset(event, ref) {
    event.dataTransfer.setData('application/x-preset-ref', ref);
    event.dataTransfer.effectAllowed = 'copy';
}

function setupBankTabDropZones() {
    document.querySelectorAll('.bank-tab').forEach(tab => {
        tab.addEventListener('dragover', (e) => {
            if (e.dataTransfer.types.includes('application/x-preset-ref')) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'copy';
                tab.classList.add('preset-drop-target');
            }
        });
        tab.addEventListener('dragleave', () => {
            tab.classList.remove('preset-drop-target');
        });
        tab.addEventListener('drop', async (e) => {
            e.preventDefault();
            tab.classList.remove('preset-drop-target');
            const ref = e.dataTransfer.getData('application/x-preset-ref');
            if (!ref) return;
            const letter = tab.dataset.letter;
            try {
                const result = await api('/api/presets/load', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ref, bank: letter}),
                });
                if (result.ok) {
                    toast(`Loaded preset to Bank ${letter.toUpperCase()}`, 'success');
                    await refreshBanks();
                }
            } catch (e) {
                toast('Drop failed', 'error');
            }
        });
    });
}

async function searchPresets(query) {
    if (!query || query.length < 2) return;
    switchPresetTab('search');
    const data = await api(`/api/presets?q=${encodeURIComponent(query)}`);
    renderPresetCards(data.presets || [], 'preset-search-results');
}

// Save current bank as preset
async function saveAsPreset() {
    if (!state.currentBank) return;
    const name = prompt('Preset name:', state.currentBank.name || '');
    if (!name) return;
    const category = prompt('Category (genre, utility, song-kits, palette, community):', 'community');
    if (!category) return;
    const vibe = prompt('Vibe description (one line):', '');

    try {
        const result = await api(`/api/presets/from-bank/${state.currentBank.letter}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, category, vibe}),
        });
        if (result.ok) {
            toast(`Saved as preset: ${result.ref}`, 'success');
            presetData = null; // force reload
            closeBankEdit();
        } else {
            toast(result.error || 'Save failed', 'error');
        }
    } catch (e) {
        toast('Save failed: ' + e.message, 'error');
    }
}

// ── Set Management ──

async function loadSets() {
    try {
        const data = await api('/api/sets');
        const sel = document.getElementById('set-selector');
        sel.innerHTML = data.sets.map(s =>
            `<option value="${s.slug}" ${s.active ? 'selected' : ''}>${s.name}</option>`
        ).join('');
    } catch (e) {}
}

async function switchSet(slug) {
    toast(`Switching to set: ${slug}...`);
    try {
        const result = await api(`/api/sets/${slug}/apply`, { method: 'POST' });
        if (result.ok) {
            toast('Set applied', 'success');
            await refreshBanks();
        } else {
            toast(result.error || 'Switch failed', 'error');
        }
    } catch (e) {
        toast('Switch failed: ' + e.message, 'error');
    }
}

async function saveCurrentSet() {
    const name = prompt('Set name:');
    if (!name) return;
    try {
        const result = await api('/api/sets/save-current', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        if (result.ok) {
            toast(`Set saved: ${result.slug}`, 'success');
            loadSets();
        } else {
            toast(result.error || 'Save failed', 'error');
        }
    } catch (e) {
        toast('Save failed: ' + e.message, 'error');
    }
}

async function refreshBanks() {
    const data = await api('/api/banks');
    state.banks = data;
    renderBankTabs();
    setupBankTabDropZones();
    if (state.currentBank) {
        const updated = data.find(b => b.letter === state.currentBank.letter);
        if (updated) switchBank(updated);
    }
}

// My Music — Plex-Powered Personal Music Library Browser
// ═══════════════════════════════════════════════════════

let musicBrowseData = null;
let musicCurrentTab = 'artists';

document.getElementById('btn-my-music')?.addEventListener('click', toggleMusicSidebar);

function toggleMusicSidebar() {
    const sidebar = document.getElementById('music-sidebar');
    const isOpen = !sidebar.classList.contains('hidden');
    if (isOpen) {
        closeMusicSidebar();
    } else {
        document.getElementById('sidebar')?.classList.add('hidden');
        document.getElementById('preset-sidebar')?.classList.add('hidden');
        sidebar.classList.remove('hidden');
        if (!musicBrowseData) loadMusicBrowse();
    }
}

function closeMusicSidebar() {
    document.getElementById('music-sidebar').classList.add('hidden');
}

async function loadMusicBrowse() {
    try {
        const status = await api('/api/music/status');
        const bar = document.getElementById('music-status-bar');
        if (status.source === 'plex') {
            bar.innerHTML = `<span class="plex-badge">PLEX</span> ${status.track_count.toLocaleString()} tracks · ${status.mood_count} moods · ${status.style_count} styles`;
        } else {
            bar.innerHTML = `${status.track_count?.toLocaleString() || 0} tracks (ID3)`;
        }

        const data = await api('/api/music/browse');
        musicBrowseData = data;
        renderMusicArtists(data.artists || []);
        renderMusicMoods(data.moods || {});
        renderMusicStyles(data.styles || {});
    } catch (e) {
        document.getElementById('music-artists-list').innerHTML =
            '<div style="padding:16px;color:var(--text-dim)">Plex not available.<br>Check database path.</div>';
    }
}

function switchMusicTab(tab) {
    musicCurrentTab = tab;
    document.querySelectorAll('#music-sidebar .sidebar-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tab));
    ['artists', 'moods', 'styles', 'search'].forEach(id =>
        document.getElementById(`music-tab-${id}`)?.classList.toggle('hidden', tab !== id));
    document.getElementById('music-detail').classList.add('hidden');
    document.getElementById('music-tag-results').classList.add('hidden');
}

function renderMusicArtists(artists) {
    const el = document.getElementById('music-artists-list');
    el.innerHTML = artists.filter(a => a.name).map(a => `
        <div class="music-item" onclick="loadArtist('${a.name.replace(/'/g, "\\'")}')">
            <span class="music-item-name">${a.name}</span>
            <span class="music-item-meta">${a.album_count} albums · ${a.track_count} tracks</span>
        </div>
    `).join('');
}

function renderMusicMoods(moods) {
    const el = document.getElementById('music-moods-list');
    const max = Math.max(...Object.values(moods), 1);
    el.innerHTML = Object.entries(moods).map(([mood, count]) => {
        const size = 0.7 + (count / max) * 0.6;
        const opacity = 0.5 + (count / max) * 0.5;
        return `<span class="mood-tag" style="font-size:${size}em;opacity:${opacity}"
                      onclick="loadMoodResults('${mood}')" title="${count} tracks">${mood}</span>`;
    }).join(' ');
}

function renderMusicStyles(styles) {
    const el = document.getElementById('music-styles-list');
    const max = Math.max(...Object.values(styles), 1);
    el.innerHTML = Object.entries(styles).map(([style, count]) => {
        const size = 0.7 + (count / max) * 0.5;
        const opacity = 0.5 + (count / max) * 0.5;
        return `<span class="style-tag" style="font-size:${size}em;opacity:${opacity}"
                      onclick="loadStyleResults('${style.replace(/'/g, "\\'")}')" title="${count} tracks">${style}</span>`;
    }).join(' ');
}

async function loadMoodResults(mood) {
    document.querySelectorAll('#music-sidebar .sidebar-tab-content').forEach(t => t.classList.add('hidden'));
    const container = document.getElementById('music-tag-results');
    container.classList.remove('hidden');
    document.getElementById('music-tag-results-title').textContent = `Mood: ${mood}`;
    document.getElementById('music-tag-results-list').innerHTML = '<div style="padding:16px;color:var(--text-dim)">Loading...</div>';

    const data = await api(`/api/music/mood/${encodeURIComponent(mood)}`);
    renderTrackResults(data.results || [], 'music-tag-results-list');
}

async function loadStyleResults(style) {
    document.querySelectorAll('#music-sidebar .sidebar-tab-content').forEach(t => t.classList.add('hidden'));
    const container = document.getElementById('music-tag-results');
    container.classList.remove('hidden');
    document.getElementById('music-tag-results-title').textContent = `Style: ${style}`;
    document.getElementById('music-tag-results-list').innerHTML = '<div style="padding:16px;color:var(--text-dim)">Loading...</div>';

    const data = await api(`/api/music/style/${encodeURIComponent(style)}`);
    renderTrackResults(data.results || [], 'music-tag-results-list');
}

function renderTrackResults(tracks, elId) {
    const el = document.getElementById(elId);
    if (!tracks.length) {
        el.innerHTML = '<div style="padding:16px;color:var(--text-dim)">No tracks found</div>';
        return;
    }
    el.innerHTML = tracks.map(r => `
        <div class="music-track">
            ${r.thumb_url ? `<img class="music-track-art" src="${r.thumb_url}" onerror="this.style.display='none'" />` : ''}
            <div class="music-track-info">
                <span class="music-track-title">${r.title || 'Unknown'}</span>
                <span class="music-item-meta">${r.artist || ''} · ${r.album || ''}</span>
            </div>
            <span class="music-track-dur">${r.duration_str || ''}</span>
            <button class="btn btn-sm btn-accent music-split-btn"
                    onclick="splitTrack(${r.id}, this)" title="Split into stems">Split</button>
        </div>
    `).join('');
}

async function loadArtist(name) {
    const data = await api(`/api/music/artist/${encodeURIComponent(name)}`);
    if (!data || data.error) return;

    document.querySelectorAll('#music-sidebar .sidebar-tab-content').forEach(t => t.classList.add('hidden'));
    const detail = document.getElementById('music-detail');
    detail.classList.remove('hidden');

    // Artist header with bio + vibes
    const header = document.getElementById('music-detail-header');
    let headerHtml = `<h4 style="color:var(--accent);margin-bottom:4px">${data.name}</h4>`;
    if (data.vibes && data.vibes.length) {
        headerHtml += `<div class="music-vibes">${data.vibes.map(v => `<span class="vibe-chip">${v}</span>`).join('')}</div>`;
    }
    if (data.styles && data.styles.length) {
        headerHtml += `<div class="music-styles-line">${data.styles.slice(0, 5).join(' · ')}</div>`;
    }
    if (data.country && data.country.length) {
        headerHtml += `<div class="music-meta-line">${data.country.join(', ')}</div>`;
    }
    if (data.summary) {
        const bio = data.summary.length > 200 ? data.summary.substring(0, 200) + '...' : data.summary;
        headerHtml += `<div class="music-bio">${bio}</div>`;
    }
    header.innerHTML = headerHtml;

    // Albums and tracks
    const tracksEl = document.getElementById('music-detail-tracks');
    let html = '';
    for (const album of (data.albums || [])) {
        const artUrl = album.thumb_url || '';
        html += `<div class="music-album-header">
            ${artUrl ? `<img class="music-album-art" src="${artUrl}" onerror="this.style.display='none'" />` : ''}
            <div>
                <span class="music-album-title">${album.title}</span>
                ${album.year ? `<span class="music-album-year">${album.year}</span>` : ''}
                ${album.studio ? `<span class="music-album-label">${album.studio}</span>` : ''}
            </div>
        </div>`;

        for (const t of (album.tracks || [])) {
            const vibeChips = (t.vibes || []).map(v => `<span class="vibe-chip vibe-sm">${v}</span>`).join('');
            html += `
                <div class="music-track">
                    <span class="music-track-num">${t.track_num || ''}</span>
                    <div class="music-track-info">
                        <span class="music-track-title">${t.title}</span>
                        ${vibeChips ? `<div class="music-track-vibes">${vibeChips}</div>` : ''}
                    </div>
                    <span class="music-track-dur">${t.duration_str || ''}</span>
                    <button class="btn btn-sm btn-accent music-split-btn"
                            onclick="splitTrack(${t.id}, this)" title="Split into stems">Split</button>
                </div>
            `;
        }
    }
    tracksEl.innerHTML = html;
}

function backToMusicBrowse() {
    document.getElementById('music-detail').classList.add('hidden');
    document.getElementById('music-tag-results').classList.add('hidden');
    const tabEl = document.getElementById(`music-tab-${musicCurrentTab}`);
    if (tabEl) tabEl.classList.remove('hidden');
}

let searchTimeout = null;
async function searchMyMusic(query) {
    if (searchTimeout) clearTimeout(searchTimeout);
    if (!query || query.length < 2) return;

    switchMusicTab('search');
    document.getElementById('music-search').value = query;

    searchTimeout = setTimeout(async () => {
        const data = await api(`/api/music/search?q=${encodeURIComponent(query)}`);
        renderTrackResults(data.results || [], 'music-search-results');
    }, 300);
}

async function splitTrack(trackId, btn) {
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Splitting...';
    }

    try {
        const data = await api('/api/music/split', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({track_id: trackId}),
        });

        if (data.error) {
            toast(`Split error: ${data.error}`, 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Split'; }
            return;
        }

        const jobId = data.job_id;
        toast(`Splitting: ${data.track}...`);

        const poll = setInterval(async () => {
            try {
                const status = await api(`/api/music/split/status/${jobId}`);
                if (status.status === 'done') {
                    clearInterval(poll);
                    const stems = status.result.stems;
                    toast(`Split into ${stems.length} stems (${status.result.source})`, 'success');
                    if (btn) { btn.disabled = false; btn.textContent = 'Done'; }
                } else if (status.status === 'error') {
                    clearInterval(poll);
                    toast(`Split error: ${status.result}`, 'error');
                    if (btn) { btn.disabled = false; btn.textContent = 'Split'; }
                } else if (status.error || !status.status) {
                    clearInterval(poll);
                    toast(`Split error: ${status.error || 'Job not found'}`, 'error');
                    if (btn) { btn.disabled = false; btn.textContent = 'Split'; }
                }
            } catch (e) {
                clearInterval(poll);
                toast(`Split status failed: ${e.message}`, 'error');
                if (btn) { btn.disabled = false; btn.textContent = 'Split'; }
            }
        }, 2000);
    } catch (e) {
        toast(`Split failed: ${e.message}`, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Split'; }
    }
}

// ── Go ──
init();
