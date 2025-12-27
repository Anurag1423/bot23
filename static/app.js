// API Base URL
const API_BASE = '/api';

// State
let novels = [];
let refreshIntervals = {};
window.currentMissingChapters = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadNovels();
    setupAddNovelForm();
});

/* =========================
   NOVELS
========================= */

// Load novels from API
async function loadNovels() {
    try {
        const response = await fetch(`${API_BASE}/novels`);
        novels = await response.json();
        renderNovels();
    } catch (error) {
        showToast('Error loading novels: ' + error.message, 'error');
    }
}

// Render novels list
function renderNovels() {
    const listEl = document.getElementById('novelsList');

    if (novels.length === 0) {
        listEl.innerHTML = '<div class="loading">No novels added yet. Add one above to get started!</div>';
        return;
    }

    listEl.innerHTML = novels.map(novel => `
        <div class="novel-card">
            <div class="novel-header">
                <div>
                    <div class="novel-title">${escapeHtml(novel.name)}</div>
                    <div class="novel-info">
                        <div class="novel-info-item">Group: ${escapeHtml(novel.group_name)}</div>
                        ${novel.nu_series_id
                            ? `<div class="novel-info-item">NU Series ID: ${escapeHtml(String(novel.nu_series_id))}</div>`
                            : ''
                        }
                        ${novel.nu_group_id
                            ? `<div class="novel-info-item">NU Group ID: ${escapeHtml(String(novel.nu_group_id))}</div>`
                            : ''
                        }
                        ${novel.last_checked
                            ? `<div class="novel-info-item">Last checked: ${formatDate(novel.last_checked)}</div>`
                            : '<div class="novel-info-item">Never checked</div>'
                        }
                    </div>
                </div>
                <div class="novel-actions">
                    <button class="btn btn-danger" onclick="deleteNovel(${novel.id})">Delete</button>
                </div>
            </div>
            <div class="card-buttons">
                <button class="btn btn-primary" onclick="refreshNovel(${novel.id})" id="refresh-${novel.id}">
                    Refresh Chapters
                </button>
                <button class="btn btn-success" onclick="viewMissing(${novel.id})">
                    View Missing
                </button>

                <div id="progress-${novel.id}" style="display:none;margin-top:10px;">
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-fill-${novel.id}"></div>
                    </div>
                    <div id="progress-text-${novel.id}" class="progress-text"></div>
                </div>
            </div>
        </div>
    `).join('');
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
   REFRESH
========================= */

async function refreshNovel(id) {
    const btn = document.getElementById(`refresh-${id}`);
    const progress = document.getElementById(`progress-${id}`);
    const fill = document.getElementById(`progress-fill-${id}`);
    const text = document.getElementById(`progress-text-${id}`);

    btn.disabled = true;
    btn.textContent = 'Refreshing...';
    progress.style.display = 'block';

    try {
        const res = await fetch(`${API_BASE}/novels/${id}/refresh`, { method: 'POST' });
        const { task_id } = await res.json();

        const poll = setInterval(async () => {
            const s = await fetch(`${API_BASE}/tasks/${task_id}`).then(r => r.json());

            fill.style.width = `${s.progress || 0}%`;
            text.textContent = s.message || '';

            if (s.status === 'completed' || s.status === 'error') {
                clearInterval(poll);
                btn.disabled = false;
                btn.textContent = 'Refresh Chapters';
                progress.style.display = 'none';
                loadNovels();
            }
        }, 1000);

    } catch (err) {
        btn.disabled = false;
        progress.style.display = 'none';
        showToast(err.message, 'error');
    }
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
