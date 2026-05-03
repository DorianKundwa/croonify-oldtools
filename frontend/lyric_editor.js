/* ================================================================
 * LYRIC EDITOR  —  Part 1: State, Undo/Redo, Helpers
 * ================================================================ */
(function () {
'use strict';

/* ── shared state ── */
const LE = window.LyricEditor = {};

LE.jobId         = null;
LE.apiBase       = null;
LE.fragments     = [];   // working copy [{i, start, end, text, y_offset, words}]
LE.originalFrags = [];   // deep-copy of server version for Reset
LE.selectedIdx   = -1;
LE.yModeActive   = false;
LE.dirty         = false;

/* ── undo/redo stack ── */
const MAX_HIST = 50;
let _hist = [];
let _histPos = -1;

function _deepCopy(arr) {
    return arr.map(f => Object.assign({}, f, { words: f.words ? f.words.map(w => Object.assign({}, w)) : [] }));
}

LE.pushHistory = function () {
    _hist = _hist.slice(0, _histPos + 1);
    _hist.push(_deepCopy(LE.fragments));
    if (_hist.length > MAX_HIST) _hist.shift();
    _histPos = _hist.length - 1;
    LE.dirty = true;
    LE.updateUndoRedoBtns();
};

LE.undo = function () {
    if (_histPos <= 0) return;
    _histPos--;
    LE.fragments = _deepCopy(_hist[_histPos]);
    LE.syncAfterEdit();
};

LE.redo = function () {
    if (_histPos >= _hist.length - 1) return;
    _histPos++;
    LE.fragments = _deepCopy(_hist[_histPos]);
    LE.syncAfterEdit();
};

LE.updateUndoRedoBtns = function () {
    const u = document.getElementById('editorUndoBtn');
    const r = document.getElementById('editorRedoBtn');
    if (u) u.disabled = (_histPos <= 0);
    if (r) r.disabled = (_histPos >= _hist.length - 1);
};

/* ── time helpers ── */
LE.toHMS = function (sec) {
    const s = Math.max(0, sec);
    const m = Math.floor(s / 60);
    const ss = (s - m * 60).toFixed(3);
    return m + ':' + (ss < 10 ? '0' : '') + ss;
};

LE.parseHMS = function (str) {
    str = String(str || '').trim();
    const parts = str.split(':');
    if (parts.length === 2) return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
    return parseFloat(str) || 0;
};

/* ── status bar ── */
LE.setStatus = function (msg, cls) {
    const el = document.getElementById('editorStatus');
    if (!el) return;
    el.textContent = msg;
    el.className = cls || 'info';
};

/* ── sync live overlay after any edit ── */
LE.syncAfterEdit = function () {
    // Propagate corrected timings back into the main rAF overlay
    if (window.alignmentEntries) {
        window.alignmentEntries = LE.fragments.map(f => ({
            i: f.i, start: f.start, end: f.end,
            text: f.text, words: f.words || []
        }));
    }
    LE.renderTable();
    LE.drawTimeline();
    LE.updateUndoRedoBtns();
    LE.dirty = true;
};

/* ── initialise from alignment data ── */
LE.init = function (jobId, apiBase, fragments) {
    LE.jobId   = jobId;
    LE.apiBase = apiBase.replace(/\/$/, '');
    LE.fragments = fragments.map((f, i) => ({
        i,
        start:    Math.max(0, parseFloat(f.begin || f.start || 0)),
        end:      Math.max(0, parseFloat(f.end   || 0)),
        text:     Array.isArray(f.lines) ? (f.lines[0] || '') : (f.lines || f.text || ''),
        y_offset: parseInt(f.y_offset || 0, 10),
        words:    Array.isArray(f.words) ? f.words.map(w => Object.assign({}, w)) : []
    })).sort((a, b) => a.start - b.start);
    LE.originalFrags = _deepCopy(LE.fragments);
    _hist = [_deepCopy(LE.fragments)];
    _histPos = 0;
    LE.selectedIdx = -1;
    LE.dirty = false;
    LE.updateUndoRedoBtns();
    LE.setStatus('Editor ready. ' + LE.fragments.length + ' lyric segments loaded.', 'info');
    LE.renderTable();
    LE.initTimeline();
    LE.initYHandle();
    LE.initKeyboard();
};

})();
