// ═══════════════════════════════════════════════════════════
// Karaoke mode — prep songs, rehearse with lyrics, hear + edit the drop sheet
// Party-time playback happens on the Windows deck (deck/karaoke_deck.py);
// this is the kitchen. Depends on api(), toast(), escapeHtml() from app.js.
// ═══════════════════════════════════════════════════════════

const KARAOKE_ROLE_NAMES = {
    cheer: 'Crowd cheer', applause: 'Applause', airhorn: 'Air horn', choir: 'Choir stab',
    crash: 'Crash', rewind: 'Rewind', riser: 'Riser', impact: 'Impact',
    hype_vox: 'Hype vox', scratch: 'Scratch', laser: 'Laser', gong: 'Gong',
};
// Keyboard → drop pad while rehearsing ("play along to write the sheet").
const KARAOKE_KEY_PADS = { '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '0': 10, '-': 11, '=': 12 };

const kara = {
    songs: [],
    status: null,
    current: null,      // {dir, song, lyrics, has_guide, has_cover}
    drops: [],
    dirty: false,
    hearDrops: true,
    lastPos: 0,
    raf: null,
    jobTimer: null,
    searchTimer: null,
    padAudio: {},
};

// app.js api() returns {error} instead of throwing; karaoke code wants exceptions.
async function karaApi(url, opts) {
    const data = await api(url, opts);
    if (data.error || data.ok === false) throw new Error(data.error || 'Request failed');
    return data;
}

function karaPadName(bank, pad) {
    if (kara.status && bank === kara.status.drop_bank) {
        const role = Object.keys(kara.status.drop_pads).find(r => kara.status.drop_pads[r] === pad);
        if (role) return KARAOKE_ROLE_NAMES[role] || role;
    }
    return `${bank}${pad}`;
}

function karaFmt(t) {
    if (t == null || isNaN(t)) return '–:––';
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Open / close ──

async function openKaraoke() {
    document.getElementById('karaoke-view').classList.remove('hidden');
    document.addEventListener('keydown', karaKeydown);
    try {
        kara.status = await karaApi('/api/karaoke/status');
        const t = kara.status.tools || {};
        const chip = (ok, name) => `<span class="kara-chip ${ok ? 'ok' : 'off'}">${ok ? '✓' : '✕'} ${name}</span>`;
        document.getElementById('karaoke-tools').innerHTML =
            chip(t.plex, 'Plex') + chip(t.karaoke_gen, 'karaoke-gen') +
            (t.remote_lane ? chip(true, `lane: ${escapeHtml(t.remote_lane)}`) : '') + chip(t.ytdlp, 'yt-dlp') +
            chip(t.demucs, 'Demucs') + chip(t.librosa, 'librosa');
        applyKaraokeCapabilities();
    } catch (e) {
        toast(`Karaoke status failed: ${e.message}`, 'error');
    }
    await loadKaraokeSongs();
    const plexOn = kara.status && kara.status.capabilities && kara.status.capabilities.sources
        && kara.status.capabilities.sources.plex;
    if (plexOn || !kara.status || !kara.status.capabilities) loadKaraokePlaylists();
}

function applyKaraokeCapabilities() {
    const cap = kara.status && kara.status.capabilities;
    if (!cap || !cap.separate) return;
    const sep = cap.separate;
    const extras = cap.extras || {};
    const model = document.getElementById('karaoke-model');
    const canGen = !!(sep.karaoke_gen || sep.remote_lane);
    const canDemucs = !!sep.demucs;
    for (const opt of model.options) {
        opt.disabled = opt.value === 'karaoke-gen' ? !canGen : !canDemucs;
    }
    if (sep.default) {
        const chosen = model.querySelector(`option[value="${sep.default}"]`);
        if (chosen && !chosen.disabled) model.value = sep.default;
    }
    const videos = document.getElementById('karaoke-videos');
    videos.disabled = !extras.ytdlp;
    if (!extras.ytdlp) videos.checked = false;
    const prep = document.getElementById('karaoke-prep-btn');
    prep.disabled = !sep.default;
    const filePrep = document.getElementById('karaoke-file-prep');
    if (filePrep) filePrep.disabled = !sep.default;
    const plex = document.getElementById('karaoke-plex-source');
    if (plex) plex.classList.toggle('hidden', !(cap.sources && cap.sources.plex));
    if (!sep.default && !kara.jobTimer) {
        const job = document.getElementById('karaoke-job');
        job.classList.remove('hidden');
        job.textContent = sep.reason || 'No vocal separator installed.';
    }
}

function closeKaraoke() {
    karaStop();
    document.getElementById('karaoke-view').classList.add('hidden');
    document.removeEventListener('keydown', karaKeydown);
}

async function loadKaraokePlaylists() {
    const sel = document.getElementById('karaoke-playlist');
    try {
        const data = await karaApi('/api/karaoke/playlists');
        const lists = data.playlists || [];
        sel.innerHTML = '<option value="">Plex playlist…</option>' + lists.map(p =>
            `<option value="${escapeHtml(p.title)}"${/karaoke/i.test(p.title) ? ' selected' : ''}>${escapeHtml(p.title)} (${p.track_count})</option>`
        ).join('');
    } catch (e) {
        sel.innerHTML = '<option value="">Plex unavailable</option>';
    }
}

async function loadKaraokeSongs() {
    try {
        const data = await karaApi('/api/karaoke/songs');
        kara.songs = data.songs || [];
    } catch (e) {
        kara.songs = [];
        toast(`Could not list karaoke songs: ${e.message}`, 'error');
    }
    renderKaraokeSongs();
}

function renderKaraokeSongs() {
    const list = document.getElementById('karaoke-song-list');
    const q = (document.getElementById('karaoke-filter').value || '').toLowerCase();
    const songs = kara.songs.filter(s => !q || `${s.artist} ${s.title}`.toLowerCase().includes(q));
    if (!songs.length) {
        list.innerHTML = `<div class="karaoke-empty small">${kara.songs.length ? 'No matches' : 'No songs prepped yet'}</div>`;
        return;
    }
    list.innerHTML = songs.map(s => `
        <div class="kara-song ${kara.current && kara.current.dir === s.dir ? 'active' : ''}" onclick="selectKaraokeSong(${escapeHtml(JSON.stringify(s.dir))})">
            <img class="kara-thumb" src="/api/karaoke/cover/${encodeURIComponent(s.dir)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
            <div class="kara-song-text">
                <div class="kara-song-title">${escapeHtml(s.title || s.dir)}</div>
                <div class="kara-song-meta">${escapeHtml(s.artist || '')} · ${s.bpm ? Math.round(s.bpm) + ' bpm' : '? bpm'}${s.key ? ' · ' + escapeHtml(s.key) : ''}</div>
            </div>
            <div class="kara-song-badges">
                ${s.has_lyrics ? '<span class="kara-chip ok">lyrics</span>' : '<span class="kara-chip off">no lyrics</span>'}
                ${s.has_video ? '<span class="kara-chip ok">video</span>' : ''}
                <span class="kara-chip">${s.drops} ✦</span>
            </div>
        </div>`).join('');
}

// ── Song detail ──

async function selectKaraokeSong(dir) {
    if (kara.dirty && kara.current && !confirm('Drop sheet has unsaved changes. Discard them?')) return;
    karaStop();
    let data;
    try {
        data = await karaApi(`/api/karaoke/song/${encodeURIComponent(dir)}`);
    } catch (e) {
        toast(e.message, 'error');
        return;
    }
    kara.current = data;
    kara.drops = (data.song.drops || []).map(d => ({ ...d }));
    kara.dirty = false;
    renderKaraokeSongs();
    renderKaraokeDetail();
}

function renderKaraokeDetail() {
    const c = kara.current;
    const s = c.song;
    const enc = encodeURIComponent(c.dir);
    const presetOpts = (kara.presetRefs || []).map(r => `<option value="${escapeHtml(r)}"${r === s.preset ? ' selected' : ''}>${escapeHtml(r)}</option>`).join('');
    document.getElementById('karaoke-detail').innerHTML = `
        <div class="kara-head">
            ${c.has_cover ? `<img class="kara-cover" src="/api/karaoke/cover/${enc}" alt="">` : '<div class="kara-cover blank">♪</div>'}
            <div class="kara-head-text">
                <div class="kara-title">${escapeHtml(s.title || c.dir)}</div>
                <div class="kara-artist">${escapeHtml(s.artist || '')}</div>
                <div class="kara-chips">
                    <span class="kara-chip">${s.bpm ? Math.round(s.bpm) + ' bpm' : 'bpm ?'}</span>
                    <span class="kara-chip">${escapeHtml(s.key || 'key ?')}</span>
                    <span class="kara-chip">${escapeHtml(s.energy || '')} energy</span>
                    <span class="kara-chip ${s.has_lyrics ? 'ok' : 'off'}">lyrics: ${escapeHtml(s.lyrics_source || 'none')}</span>
                    ${c.has_video ? `<span class="kara-chip ok" title="${escapeHtml(s.video.title || '')}${s.video.channel ? ' · ' + escapeHtml(s.video.channel) : ''}">video: ${escapeHtml(s.video.mode)}</span>` : ''}
                    <span class="kara-chip">bank: <select id="kara-preset" onchange="karaMarkDirty()"><option value="">—</option>${presetOpts}</select></span>
                </div>
            </div>
            <div class="kara-head-actions">
                <button class="btn btn-sm" onclick="reprepKaraoke(false)" title="Keep stems; redo analysis, lyrics and drops">Refresh</button>
                <button class="btn btn-sm" onclick="reprepKaraoke(true)" title="Re-run Demucs from scratch">Re-split</button>
                <button class="btn btn-sm" onclick="refetchKaraokeVideo()" title="Find the music video again (YouTube via yt-dlp)">Video</button>
            </div>
        </div>

        <div id="kara-stage" class="kara-stage" ondblclick="karaFullscreen()">
            ${c.has_cover ? `<div class="kara-stage-bg" style="background-image:url('/api/karaoke/cover/${enc}')"></div>` : ''}
            <div id="kara-flash" class="kara-flash"></div>
            <div id="kara-line-now" class="kara-line-now"><span class="kara-fill"></span><span class="kara-text">${escapeHtml(s.title || '')}</span></div>
            <div id="kara-line-next" class="kara-line-next">${c.lyrics.length ? 'press play' : (c.plain_lyrics ? 'unsynced lyrics only' : 'instrumental: no lyrics found')}</div>
        </div>

        <div class="kara-transport">
            <button id="kara-play" class="btn btn-accent" onclick="karaTogglePlay()">▶ Play</button>
            <span id="kara-time" class="kara-time">0:00 / ${karaFmt(s.duration_s)}</span>
            <label class="kara-toggle" title="Play bank ${escapeHtml(kara.status ? kara.status.drop_bank : 'A')} pad previews at drop times"><input type="checkbox" id="kara-hear" ${kara.hearDrops ? 'checked' : ''} onchange="kara.hearDrops=this.checked"> hear drops</label>
            ${c.has_guide ? `<label class="kara-toggle" title="Guide vocal level">guide <input type="range" id="kara-guide-vol" min="0" max="100" value="0" oninput="karaGuideVol(this.value)"></label>` : ''}
            <button class="btn btn-sm" onclick="karaFullscreen()" title="Full-screen lyrics (double-click the stage too)">⛶ Stage</button>
        </div>

        <div id="kara-timeline" class="kara-timeline" onclick="karaTimelineClick(event)">
            <div id="kara-choruses"></div>
            <div id="kara-markers"></div>
            <div id="kara-playhead" class="kara-playhead"></div>
        </div>

        <div class="kara-drops-head">
            <h4>Drop sheet <span id="kara-lock" class="kara-chip"></span></h4>
            <div class="kara-drops-actions">
                <span class="kara-hint">While playing, keys 1–9 0 - = drop pads 1–12 at the playhead</span>
                <button class="btn btn-sm" onclick="karaAddDrop()">+ At playhead</button>
                <button class="btn btn-sm" onclick="karaSnapAll()" ${s.bpm ? '' : 'disabled'}>Snap to bar</button>
                <button class="btn btn-sm" onclick="karaRedraft()">Redraft</button>
                <button id="kara-save" class="btn btn-sm btn-accent" onclick="karaSave()" disabled>Save</button>
            </div>
        </div>
        <div id="kara-drop-table" class="kara-drop-table"></div>

        <audio id="kara-backing" preload="auto" src="/api/karaoke/audio/${enc}/backing"></audio>
        ${c.has_guide ? `<audio id="kara-guide" preload="auto" src="/api/karaoke/audio/${enc}/guide"></audio>` : ''}
    `;
    const backing = document.getElementById('kara-backing');
    backing.addEventListener('ended', () => karaStop());
    backing.addEventListener('seeked', () => { kara.lastPos = backing.currentTime; karaSyncGuide(true); });
    if (c.has_guide) document.getElementById('kara-guide').volume = 0;
    renderKaraokeTimeline();
    renderKaraokeDrops();
    if (!kara.presetRefs) karaLoadPresetRefs();
}

async function karaLoadPresetRefs() {
    try {
        const data = await karaApi('/api/presets?category=genre');
        kara.presetRefs = (data.presets || []).map(p => p.ref || `genre/${p.slug}`).sort();
        if (kara.current) {
            const sel = document.getElementById('kara-preset');
            const cur = kara.current.song.preset;
            if (sel) sel.innerHTML = '<option value="">—</option>' + kara.presetRefs.map(r =>
                `<option value="${escapeHtml(r)}"${r === cur ? ' selected' : ''}>${escapeHtml(r)}</option>`).join('');
        }
    } catch (e) { kara.presetRefs = []; }
}

// ── Timeline + drop table ──

function karaDuration() {
    const a = document.getElementById('kara-backing');
    return (kara.current && kara.current.song.duration_s) || (a && a.duration) || 1;
}

function renderKaraokeTimeline() {
    const dur = karaDuration();
    const pct = t => `${Math.max(0, Math.min(100, t / dur * 100))}%`;
    document.getElementById('kara-choruses').innerHTML = (kara.current.song.choruses || []).map(([a, b]) =>
        `<div class="kara-chorus" style="left:${pct(a)};width:calc(${pct(b)} - ${pct(a)})" title="chorus ${karaFmt(a)}"></div>`).join('');
    document.getElementById('kara-markers').innerHTML = kara.drops.map((d, i) =>
        `<div class="kara-marker" data-i="${i}" style="left:${pct(d.t)}" title="${karaFmt(d.t)} ${escapeHtml(karaPadName(d.bank, d.pad))}: ${escapeHtml(d.label || '')}" onclick="event.stopPropagation();karaSeek(${d.t - 2})"></div>`).join('');
}

function renderKaraokeDrops() {
    const banks = 'ABCDEFGHIJ'.split('');
    const padOpts = (bank, sel) => Array.from({ length: 12 }, (_, i) => i + 1).map(p =>
        `<option value="${p}"${p === sel ? ' selected' : ''}>${p} ${bank === (kara.status && kara.status.drop_bank) ? escapeHtml(karaPadName(bank, p)) : ''}</option>`).join('');
    const rows = kara.drops.map((d, i) => `
        <div class="kara-drop-row" data-i="${i}">
            <button class="kara-drop-go" title="Jump 2s before" onclick="karaSeek(${d.t - 2})">▸</button>
            <input type="number" step="0.1" min="0" value="${d.t.toFixed(2)}" onchange="karaEditDrop(${i},'t',this.value)" title="seconds">
            <select onchange="karaEditDrop(${i},'bank',this.value)">${banks.map(b => `<option${b === d.bank ? ' selected' : ''}>${b}</option>`).join('')}</select>
            <select onchange="karaEditDrop(${i},'pad',this.value)">${padOpts(d.bank, d.pad)}</select>
            <input type="number" min="1" max="127" value="${d.vel}" onchange="karaEditDrop(${i},'vel',this.value)" title="velocity">
            <input type="text" value="${escapeHtml(d.label || '')}" placeholder="label" onchange="karaEditDrop(${i},'label',this.value)">
            <button class="kara-drop-del" title="Preview pad" onclick="karaFirePad('${d.bank}',${d.pad},${d.vel})">♪</button>
            <button class="kara-drop-del" title="Delete" onclick="karaDeleteDrop(${i})">✕</button>
        </div>`).join('');
    document.getElementById('kara-drop-table').innerHTML = rows || '<div class="karaoke-empty small">No drops. Hit play and tap 1–9 to write some.</div>';
    const locked = kara.current.song.drops_locked;
    document.getElementById('kara-lock').textContent = kara.dirty ? 'unsaved' : (locked ? 'hand-edited' : 'auto draft');
    document.getElementById('kara-save').disabled = !kara.dirty;
}

function karaMarkDirty() {
    kara.dirty = true;
    renderKaraokeTimeline();
    renderKaraokeDrops();
}

function karaEditDrop(i, field, value) {
    const d = kara.drops[i];
    if (field === 't') d.t = Math.max(0, parseFloat(value) || 0);
    else if (field === 'pad') d.pad = parseInt(value, 10);
    else if (field === 'vel') d.vel = Math.max(1, Math.min(127, parseInt(value, 10) || 100));
    else d[field] = value;
    if (field === 't') kara.drops.sort((a, b) => a.t - b.t);
    karaMarkDirty();
}

function karaDeleteDrop(i) {
    kara.drops.splice(i, 1);
    karaMarkDirty();
}

function karaSnap(t) {
    const s = kara.current.song;
    if (!s.bpm) return Math.round(t * 100) / 100;
    const bar = 240 / s.bpm;
    const off = s.beat_offset_s || 0;
    return Math.round((off + Math.round((t - off) / bar) * bar) * 1000) / 1000;
}

function karaAddDrop(pad, snap = true) {
    const bank = (kara.status && kara.status.drop_bank) || 'A';
    const a = document.getElementById('kara-backing');
    const p = pad || 3;
    const t = snap ? karaSnap(a.currentTime) : Math.round(a.currentTime * 1000) / 1000;
    if (kara.drops.some(d => d.bank === bank && d.pad === p && Math.abs(d.t - t) < 0.05)) return;
    kara.drops.push({ t: Math.max(0, t), bank, pad: p, vel: 110, label: karaPadName(bank, p).toLowerCase() });
    kara.drops.sort((x, y) => x.t - y.t);
    karaMarkDirty();
}

function karaSnapAll() {
    kara.drops.forEach(d => { d.t = Math.max(0, karaSnap(d.t)); });
    kara.drops.sort((a, b) => a.t - b.t);
    karaMarkDirty();
}

async function karaSave() {
    const sel = document.getElementById('kara-preset');
    try {
        const data = await karaApi(`/api/karaoke/song/${encodeURIComponent(kara.current.dir)}/drops`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ drops: kara.drops, locked: true, preset: sel ? sel.value : null }),
        });
        kara.drops = data.drops;
        kara.current.song.drops = data.drops;
        kara.current.song.drops_locked = data.drops_locked;
        if (sel) kara.current.song.preset = sel.value || null;
        kara.dirty = false;
        renderKaraokeTimeline();
        renderKaraokeDrops();
        toast('Drop sheet saved (locked against re-prep)', 'success');
        loadKaraokeSongs();
    } catch (e) {
        toast(`Save failed: ${e.message}`, 'error');
    }
}

async function karaRedraft() {
    if (!confirm('Replace this drop sheet with a fresh auto-draft?')) return;
    try {
        const data = await karaApi(`/api/karaoke/song/${encodeURIComponent(kara.current.dir)}/redraft`, { method: 'POST' });
        kara.drops = data.drops;
        kara.current.song.drops_locked = false;
        kara.dirty = false;
        renderKaraokeTimeline();
        renderKaraokeDrops();
        loadKaraokeSongs();
    } catch (e) {
        toast(`Redraft failed: ${e.message}`, 'error');
    }
}

// ── Playback, lyrics, drop previews ──

function karaTogglePlay() {
    const a = document.getElementById('kara-backing');
    if (!a) return;
    if (a.paused) {
        a.play().catch(e => toast(`Playback failed: ${e.message}`, 'error'));
        karaSyncGuide(true);
        const g = document.getElementById('kara-guide');
        if (g) g.play().catch(() => {});
        kara.lastPos = a.currentTime;
        document.getElementById('kara-play').textContent = '❚❚ Pause';
        cancelAnimationFrame(kara.raf);
        kara.raf = requestAnimationFrame(karaTick);
    } else {
        karaStop();
    }
}

function karaStop() {
    const a = document.getElementById('kara-backing');
    const g = document.getElementById('kara-guide');
    if (a) a.pause();
    if (g) g.pause();
    cancelAnimationFrame(kara.raf);
    const btn = document.getElementById('kara-play');
    if (btn) btn.textContent = '▶ Play';
}

function karaSeek(t) {
    const a = document.getElementById('kara-backing');
    if (!a) return;
    a.currentTime = Math.max(0, t);
    kara.lastPos = a.currentTime;
    karaSyncGuide(true);
    karaRenderLyrics(a.currentTime);
    karaRenderPlayhead(a.currentTime);
}

function karaTimelineClick(ev) {
    const el = document.getElementById('kara-timeline');
    const r = el.getBoundingClientRect();
    karaSeek((ev.clientX - r.left) / r.width * karaDuration());
}

function karaSyncGuide(force) {
    const a = document.getElementById('kara-backing');
    const g = document.getElementById('kara-guide');
    if (a && g && (force || Math.abs(g.currentTime - a.currentTime) > 0.08)) g.currentTime = a.currentTime;
}

function karaGuideVol(v) {
    const g = document.getElementById('kara-guide');
    if (g) g.volume = Math.pow(v / 100, 2);
}

function karaTick() {
    const a = document.getElementById('kara-backing');
    if (!a || a.paused) return;
    const pos = a.currentTime;
    if (pos > kara.lastPos && pos - kara.lastPos < 1) {
        for (const d of kara.drops) {
            if (d.t > kara.lastPos && d.t <= pos) karaFireDrop(d);
        }
    }
    kara.lastPos = pos;
    karaSyncGuide(false);
    karaRenderLyrics(pos);
    karaRenderPlayhead(pos);
    kara.raf = requestAnimationFrame(karaTick);
}

function karaRenderPlayhead(pos) {
    const ph = document.getElementById('kara-playhead');
    if (ph) ph.style.left = `${Math.min(100, pos / karaDuration() * 100)}%`;
    const t = document.getElementById('kara-time');
    if (t) t.textContent = `${karaFmt(pos)} / ${karaFmt(karaDuration())}`;
}

function karaRenderLyrics(pos) {
    const lines = kara.current.lyrics;
    if (!lines.length) return;
    let i = -1;
    for (let k = 0; k < lines.length; k++) { if (lines[k].t <= pos) i = k; else break; }
    const nowEl = document.getElementById('kara-line-now');
    const nextEl = document.getElementById('kara-line-next');
    const cur = i >= 0 ? lines[i] : null;
    const upcoming = lines.slice(i + 1).find(l => l.text.trim());
    const firstSung = lines.find(l => l.text.trim());
    let text = cur && cur.text.trim() ? cur.text : '';
    let frac = 0;
    if (!text && firstSung && pos < firstSung.t) {
        const left = firstSung.t - pos;
        text = left <= 3 ? '●'.repeat(Math.ceil(left)) : (kara.current.song.title || '');
    } else if (!text) {
        text = '♪';
    } else {
        const end = lines[i + 1] ? lines[i + 1].t : cur.t + 5;
        frac = Math.min(1, (pos - cur.t) / Math.max(0.5, Math.min(8, end - cur.t) * 0.9));
    }
    if (nowEl.dataset.text !== text) {
        nowEl.dataset.text = text;
        nowEl.querySelector('.kara-text').textContent = text;
        nowEl.querySelector('.kara-fill').textContent = text;
    }
    nowEl.querySelector('.kara-fill').style.clipPath = `inset(0 ${100 - frac * 100}% 0 0)`;
    nextEl.textContent = upcoming ? upcoming.text : '';
}

function karaFireDrop(d) {
    const name = karaPadName(d.bank, d.pad);
    const flash = document.getElementById('kara-flash');
    if (flash) {
        flash.textContent = `✦ ${d.label || name}`;
        flash.classList.remove('go');
        void flash.offsetWidth;
        flash.classList.add('go');
    }
    const idx = kara.drops.indexOf(d);
    const m = document.querySelector(`.kara-marker[data-i="${idx}"]`);
    if (m) { m.classList.remove('hit'); void m.offsetWidth; m.classList.add('hit'); }
    if (kara.hearDrops) karaFirePad(d.bank, d.pad, d.vel);
}

function karaFirePad(bank, pad, vel = 110) {
    // Plays whatever is currently loaded on that pad (Load Karaoke Set + Fetch first).
    const url = `/api/audio/preview/${bank.toLowerCase()}/${pad}`;
    if (kara.padAudio[url] === false) return;
    const snd = new Audio(url);
    snd.volume = Math.max(0.1, Math.min(1, vel / 127)) * 0.8;
    snd.play().catch(() => { kara.padAudio[url] = false; });
}

function karaFullscreen() {
    const el = document.getElementById('kara-stage');
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen().catch(() => {});
}

function karaKeydown(ev) {
    if (document.getElementById('karaoke-view').classList.contains('hidden')) return;
    const tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (ev.key === 'Escape' && !document.fullscreenElement) { closeKaraoke(); return; }
    if (!kara.current) return;
    if (ev.key === ' ') { ev.preventDefault(); karaTogglePlay(); return; }
    if (ev.key === 'ArrowLeft') { karaSeek(document.getElementById('kara-backing').currentTime - 5); return; }
    if (ev.key === 'ArrowRight') { karaSeek(document.getElementById('kara-backing').currentTime + 5); return; }
    const pad = KARAOKE_KEY_PADS[ev.key];
    if (pad) {
        const bank = (kara.status && kara.status.drop_bank) || 'A';
        karaFirePad(bank, pad, 110);
        const a = document.getElementById('kara-backing');
        if (a && !a.paused) karaAddDrop(pad, !ev.shiftKey);   // Shift = don't snap to the bar
    }
}

// ── Prep ──

function prepKaraokePlaylist() {
    const playlist = document.getElementById('karaoke-playlist').value;
    if (!playlist) { toast('Pick a Plex playlist first', 'error'); return; }
    startKaraokePrep({ playlist });
}

function prepKaraokeFile() {
    const input = document.getElementById('karaoke-file');
    const file = input.files && input.files[0];
    if (!file) { toast('Choose an audio file first', 'error'); return; }
    const modelSel = document.getElementById('karaoke-model');
    const opt = modelSel.selectedOptions[0];
    if (!modelSel.value || (opt && opt.disabled)) {
        toast('No vocal separator available for that model', 'error');
        return;
    }
    const body = new FormData();
    body.append('file', file);
    const artist = document.getElementById('karaoke-artist').value;
    const title = document.getElementById('karaoke-title').value;
    if (artist) body.append('artist', artist);
    if (title) body.append('title', title);
    body.append('model', modelSel.value);
    if (document.getElementById('karaoke-videos').checked) body.append('videos', '1');
    karaApi('/api/karaoke/upload', { method: 'POST', body }).then(data => {
        input.value = '';
        toast(`Prepping ${data.total} song${data.total === 1 ? '' : 's'}…`);
        pollKaraokeJob(data.job_id);
    }).catch(e => toast(`Prep failed: ${e.message}`, 'error'));
}

function reprepKaraoke(force) {
    if (!kara.current) return;
    const model = document.getElementById('karaoke-model').value;
    const label = model === 'karaoke-gen' ? 'karaoke-gen'
        : (model === 'htdemucs_ft' ? 'Demucs (clean)' : 'Demucs (fast)');
    if (force && !confirm(`Re-run ${label} on this song? Takes a few minutes.`)) return;
    startKaraokePrep({ dir: kara.current.dir, force: !!force, refresh: !force });
}

function refetchKaraokeVideo() {
    if (!kara.current) return;
    startKaraokePrep({ dir: kara.current.dir, revideo: true });
}

function searchKaraokeTrack(q) {
    clearTimeout(kara.searchTimer);
    const box = document.getElementById('karaoke-track-results');
    if (!q || q.length < 2) { box.innerHTML = ''; return; }
    kara.searchTimer = setTimeout(async () => {
        try {
            const data = await karaApi(`/api/music/search?q=${encodeURIComponent(q)}`);
            const tracks = (data.results || []).filter(r => r.type === 'track' || r.title).slice(0, 8);
            box.innerHTML = tracks.map(t => `
                <div class="kara-result" onclick="startKaraokePrep({track_id:${parseInt(t.id, 10)}});document.getElementById('karaoke-track-results').innerHTML='';">
                    <span>${escapeHtml(t.artist || '')} – ${escapeHtml(t.title || '')}</span><span class="kara-chip">+ prep</span>
                </div>`).join('') || '<div class="karaoke-empty small">No tracks</div>';
        } catch (e) {
            box.innerHTML = '<div class="karaoke-empty small">Search unavailable</div>';
        }
    }, 250);
}

async function startKaraokePrep(body) {
    const modelSel = document.getElementById('karaoke-model');
    const opt = modelSel.selectedOptions[0];
    if (!modelSel.value || (opt && opt.disabled)) {
        toast('No vocal separator available for that model', 'error');
        return;
    }
    body.model = modelSel.value;
    if (body.videos === undefined) body.videos = document.getElementById('karaoke-videos').checked;
    try {
        const data = await karaApi('/api/karaoke/prep', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        toast(`Prepping ${data.total} song${data.total === 1 ? '' : 's'}…`);
        pollKaraokeJob(data.job_id);
    } catch (e) {
        toast(`Prep failed: ${e.message}`, 'error');
    }
}

function pollKaraokeJob(jobId) {
    const box = document.getElementById('karaoke-job');
    box.classList.remove('hidden');
    clearInterval(kara.jobTimer);
    const tick = async () => {
        let job;
        try { job = await karaApi(`/api/karaoke/prep-status/${jobId}`); } catch (e) { clearInterval(kara.jobTimer); return; }
        const pct = job.total ? Math.round(((job.done || 0) + (job.failed || 0)) / job.total * 100) : 0;
        const label = job.status === 'done' ? 'Done'
            : job.status === 'partial' ? 'Partial'
            : job.status === 'error' ? 'Error' : 'Prepping';
        box.innerHTML = `
            <div class="kara-job-line">${label} ${(job.done || 0) + (job.failed || 0)}/${job.total}${job.failed ? ` · ${job.failed} failed` : ''}${job.videos ? ` · ${job.videos} video${job.videos === 1 ? '' : 's'}` : ''}</div>
            ${job.current ? `<div class="kara-job-current">${escapeHtml(job.current)}</div>` : ''}
            <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
            ${job.error ? `<div class="kara-job-err">${escapeHtml(job.error)}</div>` : ''}
            <pre class="kara-job-log">${escapeHtml((job.log || []).slice(-6).join('\n'))}</pre>`;
        if (job.status === 'done' || job.status === 'partial' || job.status === 'error') {
            clearInterval(kara.jobTimer);
            kara.jobTimer = null;
            await loadKaraokeSongs();
            if (kara.current && !kara.dirty) selectKaraokeSong(kara.current.dir);
            if (job.status === 'done') toast('Karaoke prep finished', 'success');
            else if (job.status === 'partial') toast(`${job.failed} of ${job.total} songs failed`, 'error');
            else toast(job.error ? `Prep error: ${job.error}` : 'Prep failed', 'error');
        } else if ((job.done || 0) > 0) {
            loadKaraokeSongs();
        }
    };
    tick();
    kara.jobTimer = setInterval(tick, 3000);
}

// ── Karaoke set ──

async function showKaraokeSetPlan() {
    try {
        const data = await karaApi('/api/karaoke/set-plan');
        document.getElementById('karaoke-set-plan').innerHTML = data.plan.map(p =>
            `<div><b>${p.bank.toUpperCase()}</b> ${escapeHtml(p.preset)}</div>`).join('');
        document.getElementById('karaoke-set-modal').classList.remove('hidden');
    } catch (e) {
        toast(`Could not plan set: ${e.message}`, 'error');
    }
}

async function loadKaraokeSet() {
    document.getElementById('karaoke-set-modal').classList.add('hidden');
    try {
        const data = await karaApi('/api/karaoke/load-set', { method: 'POST' });
        toast(`Loaded ${data.loaded.length} karaoke banks. Fetch All, then Export.`, 'success');
        if (data.errors && data.errors.length) toast(`Some banks failed: ${data.errors.map(e => e.bank.toUpperCase()).join(', ')}`, 'error');
        if (typeof refreshBanks === 'function') refreshBanks();
    } catch (e) {
        toast(`Load failed: ${e.message}`, 'error');
    }
}
