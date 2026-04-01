/* SP-404 JAMBOX — Main Application */

const state = {
    banks: [],
    currentBank: null,
    selectedPad: null,
    playingPad: null,
    fetchJobId: null,
    sidebarOpen: false,
    libraryPath: '',
};

const audio = document.getElementById('audio-player');

// ── Init ──
async function init() {
    const data = await api('/api/banks');
    state.banks = data;

    renderBankTabs();
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

    // Bank edit
    document.getElementById('btn-edit-bank').onclick = openBankEdit;
    document.getElementById('bank-edit-close').onclick = closeBankEdit;
    document.getElementById('btn-save-bank').onclick = saveBankEdit;

    // Tutorial
    document.getElementById('tutorial-close').onclick = hideTutorial;
    document.getElementById('tutorial-go').onclick = hideTutorial;

    // Show tutorial on first visit
    if (!localStorage.getItem('jambox-tutorial-seen')) {
        showTutorial();
    }

    // Sidebar close
    document.getElementById('sidebar-close').onclick = () => toggleLibrary(false);

    // Library search
    let searchTimer;
    document.getElementById('library-search').oninput = (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => searchLibrary(e.target.value), 300);
    };

    // Audio ended
    audio.onended = () => {
        if (state.playingPad !== null) {
            const el = document.querySelector(`.pad[data-num="${state.playingPad}"]`);
            if (el) el.classList.remove('playing');
            state.playingPad = null;
        }
    };
}

// ── API Helper ──
async function api(url, opts) {
    const resp = await fetch(url, opts);
    return resp.json();
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
            <span class="pad-label">${pad.description || 'empty'}</span>
        `;

        el.onclick = () => selectPad(pad);

        // Double click to preview
        el.ondblclick = (e) => {
            e.preventDefault();
            if (pad.status === 'filled') previewPad(bank.letter, pad.num);
        };

        grid.appendChild(el);
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
    await api(`/api/banks/${bankLetter}/pads/${padNum}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({description: desc}),
    });
    // Refresh bank data
    const updated = await api(`/api/banks/${bankLetter}`);
    const bankIdx = state.banks.findIndex(b => b.letter === bankLetter);
    if (bankIdx >= 0) state.banks[bankIdx] = updated;
    if (state.currentBank.letter === bankLetter) {
        state.currentBank = updated;
        renderPadGrid(updated);
    }
    toast('Description saved', 'success');
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
    audio.play();
    state.playingPad = padNum;
    const el = document.querySelector(`.pad[data-num="${padNum}"]`);
    if (el) el.classList.add('playing');
}

function previewLibraryFile(path) {
    audio.src = `/api/audio/library/${encodeURIComponent(path)}`;
    audio.play();
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
    showProgress();
    pollFetchStatus(result.job_id);
}

async function pollFetchStatus(jobId) {
    const data = await api(`/api/pipeline/status/${jobId}`);

    if (data.status === 'running' || data.status === 'starting') {
        document.getElementById('progress-text').textContent = data.progress || 'Starting...';
        document.getElementById('progress-fill').style.width = '50%';
        setTimeout(() => pollFetchStatus(jobId), 2000);
    } else {
        hideProgress();
        if (data.status === 'done') {
            toast(`Fetch complete: ${data.result}`, 'success');
        } else {
            toast(`Fetch error: ${data.result}`, 'error');
        }
        // Refresh bank data
        const banks = await api('/api/banks');
        state.banks = banks;
        if (state.currentBank) {
            const updated = banks.find(b => b.letter === state.currentBank.letter);
            if (updated) switchBank(updated);
        }
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
        toast('Build had errors — check console', 'error');
        console.log(padinfo, patterns);
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

function showProgress() {
    document.getElementById('progress-bar').classList.remove('hidden');
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

// ── Tag Cloud ──
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

    // Instruments
    html += renderTagSection('Instruments', data.instruments, 'instrument');

    // Genres
    html += renderTagSection('Genres', data.genres, 'genre');

    // Duration types
    html += renderTagSection('Type', data.types, 'type');

    // BPM (show as compact list)
    const bpmTags = {};
    for (const [bpm, count] of Object.entries(data.bpms || {})) {
        bpmTags[bpm + 'bpm'] = count;
    }
    html += renderTagSection('BPM', bpmTags, 'bpm');

    sections.innerHTML = html;
    renderActiveTags();
}

function renderTagSection(title, tagMap, category) {
    if (!tagMap || Object.keys(tagMap).length === 0) return '';

    const entries = Object.entries(tagMap).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;

    let html = `<div class="tag-section">
        <div class="tag-section-title">${title}</div>
        <div class="tag-cloud">`;

    for (const [tag, count] of entries) {
        const ratio = count / maxCount;
        const size = ratio > 0.7 ? 5 : ratio > 0.4 ? 4 : ratio > 0.2 ? 3 : ratio > 0.1 ? 2 : 1;
        const isActive = state.activeTags.includes(tag);
        html += `<span class="tag tag-size-${size} ${isActive ? 'active' : ''}"
                       onclick="toggleTag('${tag}')"
                       title="${count} samples">${tag}<span class="tag-count">${count}</span></span>`;
    }

    html += '</div></div>';
    return html;
}

function toggleTag(tag) {
    const idx = state.activeTags.indexOf(tag);
    if (idx >= 0) {
        state.activeTags.splice(idx, 1);
    } else {
        state.activeTags.push(tag);
    }
    renderTagCloud();
    if (state.activeTags.length > 0) {
        fetchByTags();
    } else {
        document.getElementById('tag-results').innerHTML = '';
    }
}

function renderActiveTags() {
    const container = document.getElementById('active-tags');
    if (state.activeTags.length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = state.activeTags.map(tag =>
        `<span class="active-tag" onclick="toggleTag('${tag}')">${tag}<span class="remove">&times;</span></span>`
    ).join('');
}

async function fetchByTags() {
    const params = state.activeTags.map(t => `tag=${encodeURIComponent(t)}`).join('&');
    const data = await api(`/api/library/by-tag?${params}&limit=50`);
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
        const meta = [r.bpm ? r.bpm + 'bpm' : '', r.key || '', dur].filter(Boolean).join(' · ');
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
function truncate(str, len) {
    return str.length > len ? str.slice(0, len) + '...' : str;
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

    await api(`/api/banks/${letter}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data),
    });

    closeBankEdit();
    const updated = await api(`/api/banks/${letter}`);
    const idx = state.banks.findIndex(b => b.letter === letter);
    if (idx >= 0) state.banks[idx] = updated;
    switchBank(updated);
    toast('Bank settings saved', 'success');
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

// ── Go ──
init();
