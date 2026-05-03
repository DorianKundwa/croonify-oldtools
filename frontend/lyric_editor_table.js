/* ================================================================
 * LYRIC EDITOR  —  Part 3: Fragment Table + Keyboard Shortcuts
 * ================================================================ */
(function () {
'use strict';
const LE = window.LyricEditor;

/* ── hover-preview debounce ── */
let _hoverTimer = null;

/* ── build / refresh the entire table ── */
LE.renderTable = function () {
    const tbody = document.getElementById('fragmentTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    LE.fragments.forEach((f, i) => {
        const tr = document.createElement('tr');
        if (i === LE.selectedIdx) tr.classList.add('selected');
        tr.dataset.idx = i;

        /* ── # ── */
        const tdN = document.createElement('td');
        tdN.textContent = i + 1;
        tdN.style.color = 'rgba(200,200,200,0.45)';
        tdN.style.fontVariantNumeric = 'tabular-nums';
        tr.appendChild(tdN);

        /* ── lyric text (inline-editable) ── */
        const tdT = document.createElement('td');
        tdT.className = 'lyric-text';
        tdT.contentEditable = 'true';
        tdT.spellcheck = false;
        tdT.textContent = f.text;
        tdT.title = 'Click to edit lyric text';
        tdT.addEventListener('focus', () => {
            LE.selectedIdx = i;
            LE.drawTimeline();
        });
        tdT.addEventListener('blur', () => {
            const newText = tdT.textContent.trim();
            if (newText !== f.text) {
                LE.pushHistory();
                f.text = newText;
                LE.dirty = true;
                LE.drawTimeline();
            }
        });
        tdT.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); tdT.blur(); }
            if (e.key === 'Escape') { tdT.textContent = f.text; tdT.blur(); }
        });
        tr.appendChild(tdT);

        /* ── start input ── */
        tr.appendChild(makeTimeCell(i, 'start'));

        /* ── start adjust buttons ── */
        const tdSB = document.createElement('td');
        tdSB.className = 'adjust-cell';
        tdSB.innerHTML =
            `<button class="micro-btn neg" data-idx="${i}" data-field="start" data-d="-0.1" title="−100 ms">−100</button>` +
            `<button class="micro-btn neg" data-idx="${i}" data-field="start" data-d="-0.05" title="−50 ms">−50</button>` +
            `<button class="micro-btn pos" data-idx="${i}" data-field="start" data-d="0.05" title="+50 ms">+50</button>` +
            `<button class="micro-btn pos" data-idx="${i}" data-field="start" data-d="0.1" title="+100 ms">+100</button>`;
        tr.appendChild(tdSB);

        /* ── end input ── */
        tr.appendChild(makeTimeCell(i, 'end'));

        /* ── end adjust buttons ── */
        const tdEB = document.createElement('td');
        tdEB.className = 'adjust-cell';
        tdEB.innerHTML =
            `<button class="micro-btn neg" data-idx="${i}" data-field="end" data-d="-0.1" title="−100 ms">−100</button>` +
            `<button class="micro-btn neg" data-idx="${i}" data-field="end" data-d="-0.05" title="−50 ms">−50</button>` +
            `<button class="micro-btn pos" data-idx="${i}" data-field="end" data-d="0.05" title="+50 ms">+50</button>` +
            `<button class="micro-btn pos" data-idx="${i}" data-field="end" data-d="0.1" title="+100 ms">+100</button>`;
        tr.appendChild(tdEB);

        /* ── duration (read-only) ── */
        const tdD = document.createElement('td');
        tdD.className = 'dur-cell';
        const dur = Math.max(0, f.end - f.start);
        tdD.textContent = dur.toFixed(2) + 's';
        tr.appendChild(tdD);

        /* ── Set from playhead buttons ── */
        const tdPH = document.createElement('td');
        tdPH.className = 'ph-cell';
        tdPH.innerHTML =
            `<button class="micro-btn ph-btn" data-idx="${i}" data-ph="start" title="Set start = current video time">⏱S</button>` +
            `<button class="micro-btn ph-btn" data-idx="${i}" data-ph="end"   title="Set end = current video time">⏱E</button>`;
        tr.appendChild(tdPH);

        /* ── row click → select + seek ── */
        tr.addEventListener('click', e => {
            if (e.target.closest('[contenteditable]') ||
                e.target.closest('.micro-btn') ||
                e.target.closest('input')) return;
            LE.selectedIdx = i;
            LE.renderTable();
            LE.drawTimeline();
            const vid = document.getElementById('videoPreview');
            if (vid) vid.currentTime = f.start;
        });

        /* ── row hover → debounced preview seek ── */
        tr.addEventListener('mouseenter', () => {
            clearTimeout(_hoverTimer);
            _hoverTimer = setTimeout(() => {
                const vid = document.getElementById('videoPreview');
                if (vid && vid.paused) vid.currentTime = f.start;
            }, 250);
        });
        tr.addEventListener('mouseleave', () => clearTimeout(_hoverTimer));

        tbody.appendChild(tr);
    });

    /* delegate events */
    tbody.addEventListener('change', onTableChange);
    tbody.addEventListener('click',  onMicroClick);

    /* scroll selected row into view */
    if (LE.selectedIdx >= 0) {
        const selRow = tbody.querySelector(`tr[data-idx="${LE.selectedIdx}"]`);
        if (selRow) selRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
};

function makeTimeCell(idx, field) {
    const td = document.createElement('td');
    const inp = document.createElement('input');
    inp.type = 'text'; inp.className = 'ts-input';
    inp.value = LE.toHMS(LE.fragments[idx][field]);
    inp.dataset.idx   = idx;
    inp.dataset.field = field;
    inp.title = field === 'start' ? 'Start time (m:ss.mmm)' : 'End time (m:ss.mmm)';
    td.appendChild(inp);
    return td;
}

/* ── update a single row after drag ── */
LE.updateTableRow = function (idx) {
    const tbody = document.getElementById('fragmentTableBody');
    if (!tbody) return;
    const row = tbody.querySelector(`tr[data-idx="${idx}"]`);
    if (!row) return;
    const f = LE.fragments[idx];

    row.querySelectorAll('.ts-input[data-field]').forEach(inp => {
        if (inp.dataset.field === 'start') inp.value = LE.toHMS(f.start);
        if (inp.dataset.field === 'end')   inp.value = LE.toHMS(f.end);
    });

    /* update duration cell */
    const durCell = row.querySelector('.dur-cell');
    if (durCell) durCell.textContent = Math.max(0, f.end - f.start).toFixed(2) + 's';
};

/* ── change handler (ts-input edits) ── */
function onTableChange(e) {
    const inp = e.target;
    if (!inp.dataset || inp.dataset.field === undefined) return;
    const idx   = parseInt(inp.dataset.idx, 10);
    const field = inp.dataset.field;
    const f     = LE.fragments[idx];
    if (!f) return;

    if (field === 'start' || field === 'end') {
        const v = LE.parseHMS(inp.value);
        if (!isNaN(v) && v >= 0) {
            LE.pushHistory();
            f[field] = parseFloat(v.toFixed(3));
            LE.syncAfterEdit();
        }
    } else if (field === 'y_offset') {
        const v = parseInt(inp.value, 10);
        if (!isNaN(v)) {
            LE.pushHistory();
            f.y_offset = v;
            LE.dirty = true;
        }
    }
}

/* ── micro-button + playhead-set clicks ── */
function onMicroClick(e) {
    /* playhead set */
    const phBtn = e.target.closest('.ph-btn');
    if (phBtn) {
        const idx  = parseInt(phBtn.dataset.idx, 10);
        const edge = phBtn.dataset.ph; // 'start' or 'end'
        const vid  = document.getElementById('videoPreview');
        if (!vid) return;
        const f = LE.fragments[idx];
        if (!f) return;
        LE.pushHistory();
        f[edge] = parseFloat(vid.currentTime.toFixed(3));
        // enforce start < end
        if (edge === 'start' && f.start >= f.end) f.end = parseFloat((f.start + 0.1).toFixed(3));
        if (edge === 'end'   && f.end <= f.start) f.start = parseFloat((f.end - 0.1).toFixed(3));
        LE.syncAfterEdit();
        return;
    }

    /* ms adjustment */
    const btn = e.target.closest('.micro-btn:not(.ph-btn)');
    if (!btn) return;
    const idx   = parseInt(btn.dataset.idx, 10);
    const field = btn.dataset.field;
    const delta = parseFloat(btn.dataset.d);
    const f     = LE.fragments[idx];
    if (!f || isNaN(delta)) return;
    LE.pushHistory();
    f[field] = parseFloat(Math.max(0, f[field] + delta).toFixed(3));
    LE.syncAfterEdit();
}

/* ── keyboard shortcuts ── */
LE.initKeyboard = function () {
    document.addEventListener('keydown', e => {
        const body = document.getElementById('lyricEditorBody');
        if (!body || !body.classList.contains('open')) return;

        const focus   = document.activeElement;
        const inInput = focus && (focus.tagName === 'INPUT' || focus.tagName === 'TEXTAREA' ||
                                  focus.contentEditable === 'true');

        /* Ctrl+S → Save */
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            const saveBtn = document.getElementById('editorSaveBtn');
            if (saveBtn) saveBtn.click();
            return;
        }

        /* Undo / Redo — always intercept */
        if (e.ctrlKey && !e.shiftKey && e.key === 'z') { e.preventDefault(); LE.undo(); return; }
        if (e.ctrlKey && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) { e.preventDefault(); LE.redo(); return; }

        if (inInput) return;

        const idx = LE.selectedIdx;
        if (idx < 0 || idx >= LE.fragments.length) return;
        const f = LE.fragments[idx];
        const delta = e.shiftKey ? 0.1 : 0.01;

        /* Arrow keys — shift whole fragment */
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            LE.pushHistory();
            f.start = Math.max(0, parseFloat((f.start - delta).toFixed(3)));
            f.end   = Math.max(f.start + 0.05, parseFloat((f.end - delta).toFixed(3)));
            LE.syncAfterEdit();
            return;
        }
        if (e.key === 'ArrowRight') {
            e.preventDefault();
            LE.pushHistory();
            f.start = parseFloat((f.start + delta).toFixed(3));
            f.end   = parseFloat((f.end + delta).toFixed(3));
            LE.syncAfterEdit();
            return;
        }

        /* [ ] — adjust start only */
        if (e.key === '[') { e.preventDefault(); LE.pushHistory(); f.start = Math.max(0, parseFloat((f.start - delta).toFixed(3))); LE.syncAfterEdit(); return; }
        if (e.key === ']') { e.preventDefault(); LE.pushHistory(); f.start = parseFloat((f.start + delta).toFixed(3)); LE.syncAfterEdit(); return; }

        /* { } — adjust end only */
        if (e.key === '{') { e.preventDefault(); LE.pushHistory(); f.end = Math.max(f.start + 0.05, parseFloat((f.end - delta).toFixed(3))); LE.syncAfterEdit(); return; }
        if (e.key === '}') { e.preventDefault(); LE.pushHistory(); f.end = parseFloat((f.end + delta).toFixed(3)); LE.syncAfterEdit(); return; }

        /* I / O — set start / end from playhead */
        if (e.key === 'i' || e.key === 'I') {
            e.preventDefault();
            const vid = document.getElementById('videoPreview');
            if (vid) { LE.pushHistory(); f.start = parseFloat(vid.currentTime.toFixed(3)); LE.syncAfterEdit(); }
            return;
        }
        if (e.key === 'o' || e.key === 'O') {
            e.preventDefault();
            const vid = document.getElementById('videoPreview');
            if (vid) { LE.pushHistory(); f.end = parseFloat(vid.currentTime.toFixed(3)); LE.syncAfterEdit(); }
            return;
        }

        /* Navigate rows (up/down without Shift) */
        if (e.key === 'ArrowUp' && !e.shiftKey && LE.selectedIdx > 0) {
            e.preventDefault();
            LE.selectedIdx--;
            LE.renderTable();
            LE.drawTimeline();
            const vid = document.getElementById('videoPreview');
            if (vid) vid.currentTime = LE.fragments[LE.selectedIdx].start;
            return;
        }
        if (e.key === 'ArrowDown' && !e.shiftKey && LE.selectedIdx < LE.fragments.length - 1) {
            e.preventDefault();
            LE.selectedIdx++;
            LE.renderTable();
            LE.drawTimeline();
            const vid = document.getElementById('videoPreview');
            if (vid) vid.currentTime = LE.fragments[LE.selectedIdx].start;
            return;
        }
    });
};

/* ── Y-offset drag handle ── */
LE.initYHandle = function () {
    const handle  = document.getElementById('yOffsetHandle');
    const overlay = document.getElementById('lyricsOverlay');
    if (!handle || !overlay) return;

    let dragging = false, startY = 0, startOff = 0;

    handle.addEventListener('mousedown', e => {
        if (!LE.yModeActive || LE.selectedIdx < 0) return;
        dragging = true;
        startY   = e.clientY;
        startOff = LE.fragments[LE.selectedIdx].y_offset || 0;
        e.preventDefault();
    });
    window.addEventListener('mousemove', e => {
        if (!dragging || LE.selectedIdx < 0) return;
        const dy = e.clientY - startY;
        const f  = LE.fragments[LE.selectedIdx];
        f.y_offset = startOff + Math.round(dy);
        const wh   = document.getElementById('videoWrapper');
        const oH   = overlay.offsetHeight;
        const baseY = wh ? (wh.offsetHeight - oH) / 2 : 0;
        overlay.style.bottom = '';
        overlay.style.top    = Math.max(0, baseY + f.y_offset) + 'px';
        LE.updateTableRow(LE.selectedIdx);
    });
    window.addEventListener('mouseup', () => {
        if (dragging) { dragging = false; LE.pushHistory(); LE.dirty = true; }
    });

    const toggleBtn = document.getElementById('editorYToggleBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            LE.yModeActive = !LE.yModeActive;
            toggleBtn.classList.toggle('active-mode', LE.yModeActive);
            if (LE.yModeActive) {
                handle.classList.add('visible');
                LE.setStatus('Y-offset mode: drag the ↕ handle on the video to reposition the selected lyric.', 'info');
            } else {
                handle.classList.remove('visible');
                overlay.style.top = ''; overlay.style.bottom = '12%';
                LE.setStatus('', '');
            }
        });
    }
};

})();
