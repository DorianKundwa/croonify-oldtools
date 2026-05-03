/* ================================================================
 * LYRIC EDITOR  —  Part 4: Save, Re-render, Reset, Panel init
 * ================================================================ */
(function () {
'use strict';
const LE = window.LyricEditor;

/* ── auto-save debounce ── */
let _autoSaveTimer = null;
const AUTO_SAVE_DELAY = 4000; // 4 seconds after last edit

function scheduleAutoSave() {
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = setTimeout(() => {
        if (LE.dirty) _silentSave();
    }, AUTO_SAVE_DELAY);
}

async function _silentSave() {
    try {
        const res = await fetch(`${LE.apiBase}/alignment/${LE.jobId}`, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(buildPayload())
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        LE.dirty = false;
        updateDirtyIndicator();
        showFloatingToast('💾 Auto-saved', 'success');
    } catch (e) {
        /* silent — don't bother the user for auto-save failures */
        console.warn('[AutoSave] failed:', e.message);
    }
}

/* ── dirty indicator on save button ── */
function updateDirtyIndicator() {
    const btn = document.getElementById('editorSaveBtn');
    if (!btn) return;
    if (LE.dirty) {
        btn.classList.add('dirty');
        btn.title = 'Unsaved changes — click to save';
    } else {
        btn.classList.remove('dirty');
        btn.title = '';
    }
}

/* ── floating toast notification ── */
let _toastTimer = null;
function showFloatingToast(msg, type = 'info') {
    let toast = document.getElementById('editorToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'editorToast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = `editor-toast show ${type}`;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
}

/* ── hook into pushHistory to trigger auto-save ── */
const _origPushHistory = LE.pushHistory.bind(LE);
LE.pushHistory = function () {
    _origPushHistory();
    updateDirtyIndicator();
    scheduleAutoSave();
};

/* ── build fragment payload for PATCH ── */
function buildPayload() {
    return {
        fragments: LE.fragments.map(f => ({
            begin:    f.start.toFixed(3),
            end:      f.end.toFixed(3),
            lines:    [f.text],
            words:    f.words || [],
            y_offset: f.y_offset || 0
        }))
    };
}

/* ── Save (PATCH /alignment/:jobId) ── */
async function saveChanges() {
    const btn = document.getElementById('editorSaveBtn');
    if (btn) btn.disabled = true;
    LE.setStatus('Saving alignment…', 'working');
    try {
        const res = await fetch(`${LE.apiBase}/alignment/${LE.jobId}`, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(buildPayload())
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        LE.dirty = false;
        updateDirtyIndicator();
        LE.setStatus('✅ Alignment saved. Click Re-render to apply changes to the video.', 'success');
        showFloatingToast('✅ Saved!', 'success');
        /* auto-clear status after 5 s */
        setTimeout(() => {
            if (document.getElementById('editorStatus').textContent.startsWith('✅ Alignment saved'))
                LE.setStatus('', '');
        }, 5000);
    } catch (e) {
        LE.setStatus('❌ Save failed: ' + e.message, 'error');
        showFloatingToast('❌ Save failed: ' + e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/* ── Re-render (POST /rerender/:jobId, then poll) ── */
async function rerenderVideo() {
    const btn = document.getElementById('editorRerenderBtn');
    if (btn) btn.disabled = true;

    /* Auto-save first */
    LE.setStatus('Saving alignment before re-render…', 'working');
    try {
        const sr = await fetch(`${LE.apiBase}/alignment/${LE.jobId}`, {
            method:  'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(buildPayload())
        });
        const sd = await sr.json();
        if (!sr.ok) throw new Error(sd.error || `HTTP ${sr.status}`);
        LE.dirty = false;
        updateDirtyIndicator();
    } catch (e) {
        LE.setStatus('❌ Could not save alignment: ' + e.message, 'error');
        if (btn) btn.disabled = false;
        return;
    }

    /* Kick off re-render */
    LE.setStatus('Re-render job queued…', 'working');
    let rerenderJobId;
    try {
        const rr = await fetch(`${LE.apiBase}/rerender/${LE.jobId}`, { method: 'POST' });
        const rd = await rr.json();
        if (!rr.ok) throw new Error(rd.error || `HTTP ${rr.status}`);
        rerenderJobId = rd.rerender_job_id;
    } catch (e) {
        LE.setStatus('❌ Re-render failed to start: ' + e.message, 'error');
        if (btn) btn.disabled = false;
        return;
    }

    /* Show re-render progress box */
    const box  = document.getElementById('rerenderStatus');
    const msg  = document.getElementById('rerenderMsg');
    const prog = document.getElementById('rerenderProgress');
    const dl   = document.getElementById('rerenderDownload');
    const lnk  = document.getElementById('rerenderLink');
    if (box) { box.classList.add('open'); }
    if (dl)  dl.style.display = 'none';
    if (prog) prog.value = 0;

    /* Poll */
    const pollIv = setInterval(async () => {
        try {
            const sr = await fetch(`${LE.apiBase}/status/${rerenderJobId}`);
            const sd = await sr.json();
            if (prog) prog.value = sd.progress || 0;
            if (msg)  msg.textContent = sd.stage || 'Processing…';

            if (sd.status === 'done') {
                clearInterval(pollIv);
                if (btn) btn.disabled = false;
                LE.setStatus('✅ Re-render complete!', 'success');
                showFloatingToast('🎬 Re-render complete!', 'success');
                const url = sd.output_url
                    ? (sd.output_url.startsWith('http') ? sd.output_url : `${LE.apiBase}${sd.output_url}`)
                    : null;
                if (url) {
                    if (lnk) lnk.href = url;
                    if (dl)  dl.style.display = 'block';
                    const vid = document.getElementById('videoPreview');
                    const dlk = document.getElementById('videoDownloadLink');
                    if (vid) { vid.src = url; vid.load(); }
                    if (dlk) dlk.href = url;
                }
                if (msg) msg.textContent = '✅ Done!';
            } else if (sd.status === 'error') {
                clearInterval(pollIv);
                if (btn) btn.disabled = false;
                LE.setStatus('❌ Re-render error: ' + (sd.error || 'unknown'), 'error');
                if (msg) msg.textContent = 'Error: ' + (sd.error || 'unknown');
            }
        } catch (e) {
            /* transient network error — keep polling */
        }
    }, 2000);
}

/* ── Reset to original ── */
function resetToOriginal() {
    if (!confirm('Reset all changes to the original server alignment? This cannot be undone.')) return;
    LE.fragments = LE.originalFrags.map(f => Object.assign({}, f, {
        words: f.words ? f.words.map(w => Object.assign({}, w)) : []
    }));
    LE.pushHistory();
    LE.syncAfterEdit();
    LE.dirty = false;
    updateDirtyIndicator();
    LE.setStatus('Reset to original alignment.', 'info');
}

/* ── Preview (seek to selected) ── */
function previewSelected() {
    if (LE.selectedIdx < 0) { LE.setStatus('Select a lyric row first.', 'info'); return; }
    const f   = LE.fragments[LE.selectedIdx];
    const vid = document.getElementById('videoPreview');
    if (vid) { vid.currentTime = f.start; vid.play && vid.play().catch(() => {}); }
}

/* ── Set selected start/end from playhead (toolbar buttons) ── */
function setStartFromPlayhead() {
    if (LE.selectedIdx < 0) { LE.setStatus('Select a lyric row first.', 'info'); return; }
    const vid = document.getElementById('videoPreview');
    if (!vid) return;
    LE.pushHistory();
    LE.fragments[LE.selectedIdx].start = parseFloat(vid.currentTime.toFixed(3));
    LE.syncAfterEdit();
    showFloatingToast('Start set from playhead', 'info');
}
function setEndFromPlayhead() {
    if (LE.selectedIdx < 0) { LE.setStatus('Select a lyric row first.', 'info'); return; }
    const vid = document.getElementById('videoPreview');
    if (!vid) return;
    LE.pushHistory();
    LE.fragments[LE.selectedIdx].end = parseFloat(vid.currentTime.toFixed(3));
    LE.syncAfterEdit();
    showFloatingToast('End set from playhead', 'info');
}

/* ── Collapsible panel toggle ── */
function initPanel() {
    const header  = document.getElementById('lyricEditorHeader');
    const body    = document.getElementById('lyricEditorBody');
    const chevron = document.getElementById('lyricEditorChevron');
    if (!header || !body) return;

    header.addEventListener('click', () => {
        const open = body.classList.toggle('open');
        if (chevron) chevron.style.transform = open ? 'rotate(180deg)' : '';
        header.setAttribute('aria-expanded', String(open));
        if (open) { LE.drawTimeline(); }
    });
    header.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); }
    });
}

/* ── Wire control buttons ── */
function wireButtons() {
    const get = id => document.getElementById(id);
    get('editorUndoBtn')        && get('editorUndoBtn').addEventListener('click',        () => LE.undo());
    get('editorRedoBtn')        && get('editorRedoBtn').addEventListener('click',        () => LE.redo());
    get('editorPreviewBtn')     && get('editorPreviewBtn').addEventListener('click',     previewSelected);
    get('editorSaveBtn')        && get('editorSaveBtn').addEventListener('click',        saveChanges);
    get('editorRerenderBtn')    && get('editorRerenderBtn').addEventListener('click',    rerenderVideo);
    get('editorResetBtn')       && get('editorResetBtn').addEventListener('click',       resetToOriginal);
    get('editorSetStartBtn')    && get('editorSetStartBtn').addEventListener('click',    setStartFromPlayhead);
    get('editorSetEndBtn')      && get('editorSetEndBtn').addEventListener('click',      setEndFromPlayhead);
}

/* ── Public entry point ── */
LE.openEditor = function (jobId, apiBase, alignmentData) {
    const panel = document.getElementById('lyricEditorPanel');
    if (!panel) return;
    panel.classList.remove('hidden');

    const frags = Array.isArray(alignmentData.fragments) ? alignmentData.fragments : [];
    LE.init(jobId, apiBase, frags);

    /* auto-open panel */
    const body    = document.getElementById('lyricEditorBody');
    const chevron = document.getElementById('lyricEditorChevron');
    if (body && !body.classList.contains('open')) {
        body.classList.add('open');
        if (chevron) chevron.style.transform = 'rotate(180deg)';
        const header = document.getElementById('lyricEditorHeader');
        if (header) header.setAttribute('aria-expanded', 'true');
    }

    /* update sub-caption with fragment count */
    const sub = document.getElementById('editorSubCaption');
    if (sub) sub.textContent = `${frags.length} segments loaded`;
};

/* ── Init on DOMContentLoaded ── */
document.addEventListener('DOMContentLoaded', () => {
    initPanel();
    wireButtons();

    /* inject toast styles if not present */
    if (!document.getElementById('editorToastStyle')) {
        const s = document.createElement('style');
        s.id = 'editorToastStyle';
        s.textContent = `
            #editorToast {
                position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%) translateY(20px);
                background: rgba(15,20,40,0.95); color: #e0e0e0;
                padding: 9px 20px; border-radius: 24px; font-size: 0.82rem;
                font-family: 'Segoe UI', Arial, sans-serif;
                box-shadow: 0 4px 20px rgba(0,0,0,0.45);
                opacity: 0; transition: opacity 0.3s ease, transform 0.3s ease;
                pointer-events: none; z-index: 9999; white-space: nowrap;
                border: 1px solid rgba(78,205,196,0.25);
            }
            #editorToast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
            #editorToast.success { border-color: rgba(76,175,80,0.5); color: #a5d6a7; }
            #editorToast.error   { border-color: rgba(255,87,87,0.5); color: #ef9a9a; }
            #editorSaveBtn.dirty::after {
                content: '';
                display: inline-block; width: 7px; height: 7px;
                background: #ffc850; border-radius: 50%;
                margin-left: 6px; vertical-align: middle;
                box-shadow: 0 0 4px rgba(255,200,80,0.8);
            }
            .editor-btn.active-mode {
                background: rgba(78,205,196,0.32) !important;
                border-color: rgba(78,205,196,0.7) !important;
                color: #4ecdc4 !important;
            }
        `;
        document.head.appendChild(s);
    }
});

})();
