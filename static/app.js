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
                    <button class="btn btn-danger" onclick="deleteNovel(${novel.id})">🗑️</button>
                </div>
            </div>
            <div class="card-buttons">
                <button class="btn btn-primary" onclick="refreshNovel(${novel.id})" id="refresh-${novel.id}">
                    🔄 Refresh Chapters
                </button>
                <button class="btn btn-success" onclick="viewMissing(${novel.id})">
                    📋 View Missing
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
                btn.textContent = '🔄 Refresh Chapters';
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
        listDiv.innerHTML = "✅ Synced!";
    } else {
        const missing = Array.isArray(data.missing) ? data.missing.slice() : [];
        missing.sort((a, b) => {
            const av = Number(a.vol || 0);
            const bv = Number(b.vol || 0);
            if (av !== bv) return av - bv;
            return Number(a.ch) - Number(b.ch);
        });

        const summary = `<div style="margin-bottom:12px;color:var(--text-muted);">Missing: <strong>${data.count}</strong></div>`;
        const items = missing.map(m => {
            const vol = Number(m.vol || 0);
            const ch = Number(m.ch);
            return `<div class="chapter-item"><span class="chapter-name">V${vol} C${ch}</span></div>`;
        }).join('');
        listDiv.innerHTML = `${summary}<div class="chapters-list">${items}</div>`;
        
        const btn = document.createElement('button');
        btn.className = 'btn btn-primary';
        btn.innerText = `Submit ${data.count}`;
        btn.onclick = async () => {
            await fetch(`/api/novels/${novelId}/submit`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chapters: data.missing})
            });
            alert("Submitted!");
            closeMissingModal();
        };
        actionsDiv.appendChild(btn);
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
