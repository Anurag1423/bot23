// API Base URL
const API_BASE = '/api';

// State
let novels = [];
let refreshIntervals = {};
window.currentMissingChapters = null;

/* =========================
   NOTIFICATION SOUND
========================= */
function playDoneSound(isError = false) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const masterGain = ctx.createGain();
        masterGain.gain.setValueAtTime(0.9, ctx.currentTime);
        masterGain.connect(ctx.destination);

        // Three-tone chime: low → mid → high (or descending for error)
        const tones = isError
            ? [520, 390, 260]
            : [520, 660, 880];

        tones.forEach((freq, i) => {
            const osc = ctx.createOscillator();
            const env = ctx.createGain();
            osc.connect(env);
            env.connect(masterGain);

            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, ctx.currentTime);

            const start = ctx.currentTime + i * 0.18;
            const end = start + 0.35;
            env.gain.setValueAtTime(0, start);
            env.gain.linearRampToValueAtTime(1.0, start + 0.02);
            env.gain.exponentialRampToValueAtTime(0.001, end);

            osc.start(start);
            osc.stop(end);
        });

        setTimeout(() => ctx.close(), 1500);
    } catch (e) {
        // AudioContext unavailable — silent fallback
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadNovels();
    setupAddNovelForm();
});

/* =========================
   NOVELS
========================= */

// Load novels from API — fetch all including missing so we can show both sections
async function loadNovels() {
    try {
        const response = await fetch(`${API_BASE}/novels?all=1`);
        novels = await response.json();
        renderNovels();
    } catch (error) {
        showToast('Error loading novels: ' + error.message, 'error');
    }
}

function _novelCard(novel, isMissing) {
    const meta = [
        novel.group_name ? escapeHtml(novel.group_name) : null,
        novel.nu_series_id ? `sid:${escapeHtml(String(novel.nu_series_id))}` : null,
        novel.last_checked ? formatDate(novel.last_checked) : 'never checked',
    ].filter(Boolean).join(' · ');

    const actions = isMissing
        ? `<button class="btn" onclick="reactivateNovel(${novel.id})">reactivate</button>
           <button class="btn btn-danger" onclick="deleteNovel(${novel.id})">del</button>`
        : `<button class="btn" onclick="refreshNovel(${novel.id})" id="refresh-${novel.id}">refresh</button>
           <button class="btn btn-success" onclick="viewMissing(${novel.id})">missing</button>
           <button class="btn btn-danger" onclick="deleteNovel(${novel.id})">del</button>`;

    return `
    <div class="novel-card${isMissing ? ' novel-card--missing' : ''}">
        <div class="novel-row">
            <div>
                <div class="novel-title">${escapeHtml(novel.name)}</div>
                <div class="novel-meta">${meta}</div>
            </div>
            <div class="novel-actions">${actions}</div>
        </div>
        ${!isMissing ? `
        <div class="novel-progress" id="progress-${novel.id}" style="display:none;">
            <div class="progress-bar"><div class="progress-fill" id="progress-fill-${novel.id}"></div></div>
            <div class="progress-text" id="progress-text-${novel.id}"></div>
        </div>` : ''}
    </div>`;
}

// Render novels list — active novels then a collapsible missing section
function renderNovels() {
    const listEl = document.getElementById('novelsList');
    const q = (document.getElementById('novelSearch')?.value || '').toLowerCase().trim();

    const match  = n => !q || n.name.toLowerCase().includes(q);
    const active  = novels.filter(n => (n.status || 'active') === 'active' && match(n));
    const missing = novels.filter(n => n.status === 'missing' && match(n));

    let html = '';

    if (active.length === 0 && missing.length === 0) {
        listEl.innerHTML = '<div class="loading">No novels tracked yet.</div>';
        return;
    }

    if (active.length > 0) {
        html += active.map(n => _novelCard(n, false)).join('');
    } else {
        html += '<div class="loading">No active novels.</div>';
    }

    if (missing.length > 0) {
        html += `
        <div class="missing-section">
            <button class="missing-toggle" onclick="this.parentElement.classList.toggle('open')">
                Missing / DMCA'd (${missing.length}) ▸
            </button>
            <div class="missing-list">
                ${missing.map(n => _novelCard(n, true)).join('')}
            </div>
        </div>`;
    }

    listEl.innerHTML = html;
}

/* =========================
   MODAL (SINGLE SOURCE)
========================= */

function openMissingModal() {
    const modal = document.getElementById('missingModal');
    modal.style.display = '';
    modal.classList.add('show');
}

function closeMissingModal() {
    const modal = document.getElementById('missingModal');
    modal.classList.remove('show');
    modal.style.display = '';
    window.currentMissingChapters = null;
}

// Close on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.id === 'missingModal') {
        closeMissingModal();
    }
});

// Close on ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('missingModal');
        if (modal && modal.classList.contains('show')) {
            closeMissingModal();
        }
    }
});

/* =========================
   ADD NOVEL
========================= */

function setupAddNovelForm() {
    document.getElementById('addNovelForm').addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = {
            name: document.getElementById('novelName').value,
            fenrir_url: document.getElementById('fenrirUrl').value,
            nu_url: document.getElementById('nuUrl').value,
            group_name: document.getElementById('groupName').value || 'Fenrir Realm',
            nu_series_id: (document.getElementById('nuSeriesId')?.value || '').trim() || null,
            nu_group_id: (document.getElementById('nuGroupId')?.value || '').trim() || null,
        };

        try {
            const res = await fetch(`${API_BASE}/novels`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            if (!res.ok) throw new Error('Failed to add novel');

            showToast('Novel added successfully!', 'success');
            e.target.reset();
            loadNovels();
        } catch (err) {
            showToast(err.message, 'error');
        }
    });
}

/* =========================
   DELETE
========================= */

async function deleteNovel(id) {
    if (!confirm('Delete this novel?')) return;

    try {
        const res = await fetch(`${API_BASE}/novels/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        showToast('Novel deleted', 'success');
        loadNovels();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

/* =========================
   REACTIVATE
========================= */

async function reactivateNovel(id) {
    try {
        const res = await fetch(`${API_BASE}/novels/${id}/reactivate`, { method: 'POST' });
        if (!res.ok) throw new Error('Reactivate failed');
        showToast('Novel reactivated — refresh it to scan for chapters.', 'success');
        loadNovels();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

/* =========================
   REFRESH
========================= */

// Returns a Promise that resolves when the refresh task finishes (or rejects on error).
function _refreshNovelAndWait(id) {
    return new Promise(async (resolve, reject) => {
        const btn  = document.getElementById(`refresh-${id}`);
        const prog = document.getElementById(`progress-${id}`);
        const fill = document.getElementById(`progress-fill-${id}`);
        const text = document.getElementById(`progress-text-${id}`);

        if (btn)  { btn.disabled = true; btn.textContent = 'refreshing…'; }
        if (prog) prog.style.display = 'block';

        try {
            const res = await fetch(`${API_BASE}/novels/${id}/refresh`, { method: 'POST' });
            if (!res.ok) { const e = await res.json(); throw new Error(e.error || res.status); }
            const { task_id } = await res.json();

            const poll = setInterval(async () => {
                try {
                    const s = await fetch(`${API_BASE}/tasks/${task_id}`).then(r => r.json());
                    if (fill) fill.style.width = `${s.progress || 0}%`;
                    if (text) text.textContent = s.message || '';

                    if (s.status === 'completed' || s.status === 'error') {
                        clearInterval(poll);
                        if (btn)  { btn.disabled = false; btn.textContent = 'refresh'; }
                        if (prog) prog.style.display = 'none';
                        resolve(s.status);
                    }
                } catch (pollErr) {
                    clearInterval(poll);
                    reject(pollErr);
                }
            }, 1000);

        } catch (err) {
            if (btn)  { btn.disabled = false; btn.textContent = 'refresh'; }
            if (prog) prog.style.display = 'none';
            reject(err);
        }
    });
}

async function refreshNovel(id) {
    try {
        const status = await _refreshNovelAndWait(id);
        playDoneSound(status === 'error');
        loadNovels();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function refreshAllNovels() {
    const active = novels.filter(n => (n.status || 'active') === 'active');
    if (active.length === 0) { showToast('No active novels to refresh.', 'info'); return; }

    const btn       = document.getElementById('refreshAllBtn');
    const statusEl  = document.getElementById('refreshAllStatus');
    btn.disabled    = true;
    statusEl.style.display = 'block';

    let done = 0;
    let errors = 0;

    for (const novel of active) {
        statusEl.textContent = `Refreshing ${done + 1} / ${active.length} — ${novel.name}`;
        try {
            const result = await _refreshNovelAndWait(novel.id);
            if (result === 'error') errors++;
        } catch (e) {
            errors++;
        }
        done++;
        // Reload list so last_checked updates after each novel
        await loadNovels();
    }

    btn.disabled = false;
    statusEl.textContent = `Done — ${active.length} novels refreshed${errors ? `, ${errors} error(s)` : ''}.`;
    playDoneSound(errors > 0);
    setTimeout(() => { statusEl.style.display = 'none'; }, 5000);
}

/* =========================
   VIEW MISSING
========================= */

async function viewMissing(novelId) {
    const listDiv = document.getElementById('missingChaptersList');
    const actionsDiv = document.getElementById('missingChaptersActions');
    openMissingModal();
    listDiv.textContent = 'Loading...';
    actionsDiv.innerHTML = '';
    
    let data;
    try {
        const res = await fetch(`/api/novels/${novelId}/missing`);
        data = await res.json();
    } catch (err) {
        listDiv.textContent = '';
        showToast('Error loading missing chapters: ' + err.message, 'error');
        return;
    }

    if (data.count === 0) {
        listDiv.innerHTML = "Synced!";
    } else {
        const missing = Array.isArray(data.missing) ? data.missing.slice() : [];
        missing.sort((a, b) => {
            const av = Number(a.vol || 0);
            const bv = Number(b.vol || 0);
            if (av !== bv) return av - bv;
            return Number(a.ch) - Number(b.ch);
        });

        const parseStart = (raw) => {
            const s = String(raw || '').trim().toLowerCase().replace(/\s+/g, '');
            if (!s) return null;
            let m = s.match(/^v(\d+)c(\d+)$/i);
            if (m) return { vol: Number(m[1]), ch: Number(m[2]) };
            m = s.match(/^c(\d+)$/i);
            if (m) return { vol: 0, ch: Number(m[1]) };
            return null;
        };

        const isAtOrAfter = (item, start) => {
            if (!start) return true;
            const v = Number(item.vol || 0);
            const c = Number(item.ch);
            if (v > Number(start.vol || 0)) return true;
            if (v < Number(start.vol || 0)) return false;
            return c >= Number(start.ch);
        };

        let filteredMissing = missing.slice();

        const render = () => {
            const startVal = document.getElementById(`startFrom-${novelId}`)?.value || '';
            const startParsed = parseStart(startVal);
            filteredMissing = missing.filter(m => isAtOrAfter(m, startParsed));

            const summary = `<div style="margin-bottom:12px;color:var(--text-muted);">Missing: <strong>${data.count}</strong></div>`;
            const controls = `
                <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;">
                    <label style="color:var(--text-muted);">Start from</label>
                    <input id="startFrom-${novelId}" value="${escapeHtml(String(startVal))}" placeholder="v2c78 or c32" style="flex:1;" />
                </div>
            `;

            const items = filteredMissing.map((m, idx) => {
                const vol = Number(m.vol || 0);
                const ch = Number(m.ch);
                const label = vol > 0 ? `V${vol} C${ch}` : `C${ch}`;
                const id = `miss-${novelId}-${idx}`;
                return `
                    <label class="chapter-item" for="${id}" style="display:flex;align-items:center;gap:10px;">
                        <input type="checkbox" id="${id}" class="missing-chk" data-idx="${idx}" checked />
                        <span class="chapter-name">${label}</span>
                    </label>
                `;
            }).join('');
            listDiv.innerHTML = `${summary}${controls}<div class="chapters-list">${items}</div>`;

            const startEl = document.getElementById(`startFrom-${novelId}`);
            if (startEl) {
                startEl.addEventListener('input', () => {
                    render();
                });
            }

            document.querySelectorAll('#missingChaptersList .missing-chk').forEach(c => {
                c.addEventListener('change', updateSubmitLabel);
            });

            updateSubmitLabel();
        };

        const getSelected = () => {
            const checks = Array.from(document.querySelectorAll('#missingChaptersList .missing-chk'));
            const selectedIdx = checks
                .filter(c => c.checked)
                .map(c => Number(c.dataset.idx))
                .filter(n => Number.isFinite(n));
            return selectedIdx.map(i => filteredMissing[i]).filter(Boolean);
        };

        const updateSubmitLabel = () => {
            const selected = getSelected();
            submitBtn.innerText = `Submit Selected (${selected.length})`;
            submitBtn.disabled = selected.length === 0;
        };

        const selectAllBtn = document.createElement('button');
        selectAllBtn.className = 'btn btn-secondary';
        selectAllBtn.innerText = 'Select All';

        const selectNoneBtn = document.createElement('button');
        selectNoneBtn.className = 'btn btn-secondary';
        selectNoneBtn.innerText = 'Select None';

        const submitBtn = document.createElement('button');
        submitBtn.className = 'btn btn-primary';

        selectAllBtn.onclick = () => {
            document.querySelectorAll('#missingChaptersList .missing-chk').forEach(c => { c.checked = true; });
            updateSubmitLabel();
        };

        selectNoneBtn.onclick = () => {
            document.querySelectorAll('#missingChaptersList .missing-chk').forEach(c => { c.checked = false; });
            updateSubmitLabel();
        };

        submitBtn.onclick = async () => {
            const selected = getSelected();
            if (selected.length === 0) return;
            await fetch(`/api/novels/${novelId}/submit`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chapters: selected})
            });
            alert("Submitted!");
            closeMissingModal();
        };

        actionsDiv.appendChild(selectAllBtn);
        actionsDiv.appendChild(selectNoneBtn);
        actionsDiv.appendChild(submitBtn);

        render();
    }
}
/* =========================
   SYNC FROM FENRIR REALM
========================= */

async function syncFenrir() {
    const btn = document.getElementById('syncBtn');
    const progress = document.getElementById('syncProgress');
    const fill = document.getElementById('syncProgressFill');
    const text = document.getElementById('syncProgressText');

    btn.disabled = true;
    btn.textContent = 'Syncing...';
    progress.style.display = 'block';
    fill.style.width = '0%';
    text.textContent = 'Starting...';

    try {
        const res = await fetch('/api/sync-fenrir', { method: 'POST' });
        const { task_id } = await res.json();

        const poll = setInterval(async () => {
            try {
                const s = await fetch(`/api/tasks/${task_id}`).then(r => r.json());
                fill.style.width = `${s.progress || 0}%`;
                text.textContent = s.message || '';

                if (s.status === 'completed') {
                    clearInterval(poll);
                    playDoneSound(false);
                    btn.disabled = false;
                    btn.textContent = 'Sync Novels from Fenrir Realm';
                    showToast(s.message || 'Sync complete!', 'success');
                    loadNovels();
                } else if (s.status === 'error') {
                    clearInterval(poll);
                    playDoneSound(true);
                    btn.disabled = false;
                    btn.textContent = 'Sync Novels from Fenrir Realm';
                    progress.style.display = 'none';
                    showToast('Sync error: ' + s.message, 'error');
                }
            } catch (err) {
                clearInterval(poll);
                btn.disabled = false;
                btn.textContent = 'Sync Novels from Fenrir Realm';
                progress.style.display = 'none';
                showToast('Polling error: ' + err.message, 'error');
            }
        }, 1500);

    } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Sync Novels from Fenrir Realm';
        progress.style.display = 'none';
        showToast('Failed to start sync: ' + err.message, 'error');
    }
}

/* =========================
   UTILS
========================= */

function showToast(msg, type = 'info') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast ${type} show`;
    setTimeout(() => t.classList.remove('show'), 3000);
}

function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function formatDate(d) {
    return new Date(d).toLocaleString();
}
