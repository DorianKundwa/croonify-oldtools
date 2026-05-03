/* ================================================================
 * LYRIC EDITOR  —  Part 2: Timeline Canvas
 * ================================================================ */
(function () {
'use strict';
const LE = window.LyricEditor;

/* ── zoom / pan state ── */
let zoom       = 1;
let panOffset  = 0;
let totalDur   = 0;
let canvasW    = 1;
let canvasH    = 1;

/* ── drag state ── */
let dragState  = null;
// { type: 'body'|'left'|'right'|'pan', idx, startX, origStart, origEnd, panStart }

/* ── hover state ── */
let hoverInfo  = null; // { idx, x, y }

/* ── snap ── */
const SNAP_SEC = 0.05; // snap radius in seconds
const SNAP_PX  = 6;    // snap only when within 6 px

const BLOCK_COLORS = [
    'rgba(78,205,196,0.82)', 'rgba(69,183,209,0.82)',
    'rgba(150,206,180,0.82)', 'rgba(255,200,87,0.82)',
    'rgba(255,107,107,0.82)', 'rgba(199,125,255,0.82)'
];

function secToX(s) {
    return ((s - panOffset) / totalDur) * canvasW * zoom;
}
function xToSec(x) {
    return panOffset + (x / (canvasW * zoom)) * totalDur;
}
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

/* ── snap helper: find nearest fragment edge within SNAP_PX ── */
function snapSec(candidateSec, excludeIdx, excludeEdge) {
    let best = candidateSec;
    let bestDist = SNAP_SEC;
    LE.fragments.forEach((f, i) => {
        if (i === excludeIdx) return;
        [f.start, f.end].forEach(edge => {
            const d = Math.abs(edge - candidateSec);
            if (d < bestDist) { bestDist = d; best = edge; }
        });
    });
    // also snap to round seconds
    const rounded = Math.round(candidateSec * 10) / 10;
    if (Math.abs(rounded - candidateSec) < bestDist) best = rounded;
    return best;
}

LE.drawTimeline = function () {
    const canvas = document.getElementById('timelineCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvasW = canvas.offsetWidth;
    canvasH = canvas.offsetHeight;
    canvas.width  = canvasW * dpr;
    canvas.height = canvasH * dpr;
    ctx.scale(dpr, dpr);

    /* resolve total duration from video element */
    const vid = document.getElementById('videoPreview');
    if (vid && vid.duration && isFinite(vid.duration)) totalDur = vid.duration;
    if (!totalDur || totalDur < 1) totalDur = 60;

    /* ── background ── */
    ctx.fillStyle = 'rgba(8,12,22,0.92)';
    ctx.fillRect(0, 0, canvasW, canvasH);

    /* ── gap highlighting (amber wash between fragments) ── */
    const frags = LE.fragments;
    if (frags.length > 1) {
        ctx.fillStyle = 'rgba(255,180,50,0.07)';
        for (let i = 0; i < frags.length - 1; i++) {
            const gapStart = frags[i].end;
            const gapEnd   = frags[i + 1].start;
            if (gapEnd <= gapStart) continue;
            const gx1 = secToX(gapStart);
            const gx2 = secToX(gapEnd);
            if (gx2 < 0 || gx1 > canvasW) continue;
            ctx.fillRect(Math.max(0, gx1), 18, Math.min(canvasW, gx2) - Math.max(0, gx1), canvasH - 26);
        }
    }

    /* ── ruler ticks ── */
    const step = chooseTick(totalDur / zoom);
    const startSec = Math.floor(panOffset / step) * step;
    for (let t = startSec; t <= panOffset + totalDur / zoom; t += step) {
        const x = secToX(t);
        if (x < 0 || x > canvasW) continue;
        ctx.fillStyle = 'rgba(255,255,255,0.07)';
        ctx.fillRect(x, 0, 1, canvasH);
        ctx.fillStyle = 'rgba(200,200,200,0.55)';
        ctx.font = '9px monospace';
        ctx.fillText(LE.toHMS(t), x + 3, 12);
    }

    /* ── fragment blocks ── */
    for (let i = 0; i < frags.length; i++) {
        const f   = frags[i];
        const x1  = secToX(f.start);
        const x2  = secToX(f.end);
        const w   = Math.max(4, x2 - x1);
        if (x2 < 0 || x1 > canvasW) continue;

        const isSelected = (i === LE.selectedIdx);
        const isHovered  = (hoverInfo && hoverInfo.idx === i);
        const col        = BLOCK_COLORS[i % BLOCK_COLORS.length];

        /* block body */
        ctx.fillStyle = isSelected
            ? col.replace('0.82', '1')
            : isHovered
                ? col.replace('0.82', '0.92')
                : col;
        ctx.beginPath();
        ctx.roundRect(x1, 20, w, canvasH - 30, 5);
        ctx.fill();

        /* selection border */
        if (isSelected) {
            ctx.strokeStyle = 'rgba(255,255,255,0.9)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.roundRect(x1, 20, w, canvasH - 30, 5);
            ctx.stroke();
        }

        /* edge handles — wider for touch */
        const hW = 8;
        ctx.fillStyle = isSelected ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.4)';
        ctx.fillRect(x1,               22, hW, canvasH - 34);
        ctx.fillRect(Math.max(x1, x2 - hW), 22, hW, canvasH - 34);

        /* label */
        if (w > 20) {
            ctx.fillStyle = isSelected ? '#000' : 'rgba(0,0,0,0.85)';
            ctx.font = `${isSelected ? 'bold ' : ''}10px sans-serif`;
            ctx.save();
            ctx.beginPath();
            ctx.rect(x1 + hW + 2, 20, w - hW * 2 - 4, canvasH - 30);
            ctx.clip();
            ctx.fillText(f.text, x1 + hW + 4, canvasH - 12);
            ctx.restore();
        }
    }

    /* ── playhead ── */
    if (vid) {
        const px = secToX(vid.currentTime);
        if (px >= 0 && px <= canvasW) {
            /* glow */
            ctx.shadowColor = '#ff4444';
            ctx.shadowBlur  = 6;
            ctx.strokeStyle = '#ff5555';
            ctx.lineWidth   = 2;
            ctx.beginPath();
            ctx.moveTo(px, 0); ctx.lineTo(px, canvasH);
            ctx.stroke();
            ctx.shadowBlur = 0;
            /* triangle head */
            ctx.fillStyle = '#ff5555';
            ctx.beginPath();
            ctx.moveTo(px - 5, 0);
            ctx.lineTo(px + 5, 0);
            ctx.lineTo(px, 7);
            ctx.closePath();
            ctx.fill();
            /* time label */
            ctx.fillStyle = '#ff9999';
            ctx.font = '9px monospace';
            const tl = LE.toHMS(vid.currentTime);
            ctx.fillText(tl, Math.min(px + 4, canvasW - 40), 20);
        }
    }

    /* ── zoom badge ── */
    const zoomLabel = zoom.toFixed(1) + '×';
    ctx.font = 'bold 10px monospace';
    ctx.fillStyle = 'rgba(78,205,196,0.8)';
    ctx.textAlign = 'right';
    ctx.fillText(zoomLabel, canvasW - 6, canvasH - 6);
    ctx.textAlign = 'left';

    /* ── hover tooltip ── */
    if (hoverInfo && hoverInfo.idx >= 0) {
        const f  = frags[hoverInfo.idx];
        const tx = Math.min(hoverInfo.x + 10, canvasW - 140);
        const ty = Math.max(hoverInfo.y - 30, 24);
        const label = `${f.text}  ${LE.toHMS(f.start)} → ${LE.toHMS(f.end)}`;
        ctx.font = '10px sans-serif';
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(15,20,40,0.92)';
        ctx.beginPath();
        ctx.roundRect(tx - 4, ty - 13, tw + 10, 18, 4);
        ctx.fill();
        ctx.fillStyle = '#e0e0e0';
        ctx.fillText(label, tx, ty);
    }
};

function chooseTick(dur) {
    const targets = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60];
    for (const t of targets) if (dur / t < 20) return t;
    return 60;
}

/* ── hit test ── */
function hitTest(x, y) {
    const hW = 10; // wider hit zone
    for (let i = LE.fragments.length - 1; i >= 0; i--) {
        const f  = LE.fragments[i];
        const x1 = secToX(f.start);
        const x2 = secToX(f.end);
        if (y < 18 || y > canvasH - 6) continue;
        if (x >= x1 - 2 && x <= x1 + hW) return { type: 'left',  idx: i };
        if (x >= x2 - hW && x <= x2 + 2) return { type: 'right', idx: i };
        if (x >  x1 + hW && x <  x2 - hW) return { type: 'body', idx: i };
    }
    return { type: 'pan', idx: -1 };
}

/* ── unified pointer handler (used by both mouse and touch) ── */
function pointerDown(x, y) {
    const hit = hitTest(x, y);
    if (hit.type === 'pan') {
        /* click on empty area → seek video to that time */
        const t = xToSec(x);
        const vid = document.getElementById('videoPreview');
        if (vid && t >= 0 && t <= totalDur) vid.currentTime = t;
        dragState = { type: 'pan', startX: x, panStart: panOffset };
    } else {
        const f = LE.fragments[hit.idx];
        LE.selectedIdx = hit.idx;
        dragState = { type: hit.type, idx: hit.idx, startX: x,
                      origStart: f.start, origEnd: f.end };
        const vid = document.getElementById('videoPreview');
        if (vid) vid.currentTime = f.start;
        LE.renderTable();
        // scroll selected row into view
        const tbody = document.getElementById('fragmentTableBody');
        const row = tbody && tbody.querySelector(`tr[data-idx="${hit.idx}"]`);
        if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    LE.drawTimeline();
}

function pointerMove(x) {
    if (!dragState) return;
    const dx = x - dragState.startX;
    const ds = dx / (canvasW * zoom / totalDur);

    if (dragState.type === 'pan') {
        panOffset = clamp(dragState.panStart - ds, 0, Math.max(0, totalDur * (1 - 1 / zoom)));
        LE.drawTimeline();
        return;
    }

    const f = LE.fragments[dragState.idx];
    const MIN_DUR = 0.05;

    if (dragState.type === 'body') {
        const dur = dragState.origEnd - dragState.origStart;
        let ns = clamp(dragState.origStart + ds, 0, totalDur - dur);
        ns = snapSec(ns, dragState.idx, 'start');
        f.start = parseFloat(ns.toFixed(3));
        f.end   = parseFloat((ns + dur).toFixed(3));
    } else if (dragState.type === 'left') {
        let ns = clamp(dragState.origStart + ds, 0, f.end - MIN_DUR);
        ns = snapSec(ns, dragState.idx, 'start');
        f.start = parseFloat(ns.toFixed(3));
    } else if (dragState.type === 'right') {
        let ne = clamp(dragState.origEnd + ds, f.start + MIN_DUR, totalDur);
        ne = snapSec(ne, dragState.idx, 'end');
        f.end = parseFloat(ne.toFixed(3));
    }
    LE.drawTimeline();
    LE.updateTableRow(dragState.idx);
}

function pointerUp() {
    if (dragState && dragState.type !== 'pan') {
        LE.pushHistory();
        LE.syncAfterEdit();
    }
    dragState = null;
}

LE.initTimeline = function () {
    const canvas = document.getElementById('timelineCanvas');
    if (!canvas) return;

    /* ── Mouse events ── */
    canvas.addEventListener('mousedown', e => {
        const rect = canvas.getBoundingClientRect();
        pointerDown(e.clientX - rect.left, e.clientY - rect.top);
        e.preventDefault();
    });
    window.addEventListener('mousemove', e => {
        if (!dragState) return;
        const rect = canvas.getBoundingClientRect();
        pointerMove(e.clientX - rect.left);
    });
    window.addEventListener('mouseup', pointerUp);

    /* ── Hover tooltip ── */
    canvas.addEventListener('mousemove', e => {
        if (dragState) return;
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const hit = hitTest(x, y);
        hoverInfo = hit.idx >= 0 ? { idx: hit.idx, x, y } : null;
        canvas.style.cursor = hit.type === 'left' || hit.type === 'right'
            ? 'ew-resize' : hit.type === 'body' ? 'grab' : 'crosshair';
    });
    canvas.addEventListener('mouseleave', () => { hoverInfo = null; });

    /* ── Touch events ── */
    canvas.addEventListener('touchstart', e => {
        const rect = canvas.getBoundingClientRect();
        const t = e.touches[0];
        pointerDown(t.clientX - rect.left, t.clientY - rect.top);
        e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchmove', e => {
        const rect = canvas.getBoundingClientRect();
        pointerMove(e.touches[0].clientX - rect.left);
        e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchend', pointerUp, { passive: false });

    /* ── Wheel zoom ── */
    canvas.addEventListener('wheel', e => {
        e.preventDefault();
        const rect  = canvas.getBoundingClientRect();
        const mx    = e.clientX - rect.left;
        const pivot = xToSec(mx);
        zoom = clamp(zoom * (e.deltaY < 0 ? 1.18 : 0.85), 1, 50);
        panOffset = clamp(pivot - mx / (canvasW * zoom / totalDur), 0, Math.max(0, totalDur * (1 - 1 / zoom)));
        LE.drawTimeline();
    }, { passive: false });

    /* ── Pinch-to-zoom (touch) ── */
    let lastPinchDist = null;
    canvas.addEventListener('touchstart', e => {
        if (e.touches.length === 2) {
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            lastPinchDist = Math.hypot(dx, dy);
        }
    }, { passive: true });
    canvas.addEventListener('touchmove', e => {
        if (e.touches.length === 2 && lastPinchDist) {
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            const dist = Math.hypot(dx, dy);
            const ratio = dist / lastPinchDist;
            zoom = clamp(zoom * ratio, 1, 50);
            lastPinchDist = dist;
            LE.drawTimeline();
        }
    }, { passive: true });
    canvas.addEventListener('touchend', () => { lastPinchDist = null; }, { passive: true });

    /* ── rAF playhead loop ── */
    (function phLoop() {
        LE.drawTimeline();
        requestAnimationFrame(phLoop);
    })();
};

})();
