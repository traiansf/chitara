// Motor de transpunere a acordurilor — fără dependințe, rulează direct în
// browser (variabilele de mai jos ajung globale printr-un <script> simplu).
// Depinde de CHORDS_DATA (NOTES, ALIAS, FINGERINGS), definit în
// chords-data.js, generat din tools/add_guitar_chords.py / add_ukulele_chords.py —
// nu retranscrie acele tabele aici.

function normalizeToken(tok) {
  tok = tok.replace(/^[()]+|[()]+$/g, "").replace(/[:.]+$/, "");
  const m = /^([A-G](?:#|b)?)(.*)$/.exec(tok);
  if (!m) return tok;
  const root = m[1];
  let rest = m[2];
  let bass = "";
  const slash = rest.indexOf("/");
  if (slash !== -1) {
    bass = "/" + rest.slice(slash + 1);
    rest = rest.slice(0, slash);
  }
  const full = CHORDS_DATA.ALIAS[root + rest];
  if (full) return full + bass;
  return (CHORDS_DATA.ALIAS[root] || root) + rest + bass;
}

function transposeNote(note, semitones) {
  const i = CHORDS_DATA.NOTES.indexOf(note);
  if (i === -1) return note;
  return CHORDS_DATA.NOTES[((i + semitones) % 12 + 12) % 12];
}

function splitRootBass(name) {
  const m = /^([A-G]#?)(.*)$/.exec(name);
  if (!m) return null;
  let rest = m[2];
  let bass = null;
  const slash = rest.indexOf("/");
  if (slash !== -1) {
    bass = rest.slice(slash + 1);
    rest = rest.slice(0, slash);
  }
  return { root: m[1], rest, bass };
}

function transposeName(normalizedName, semitones) {
  const parts = splitRootBass(normalizedName);
  if (!parts) return normalizedName;
  const root = transposeNote(parts.root, semitones);
  const bass = parts.bass ? transposeNote(parts.bass, semitones) : null;
  return root + parts.rest + (bass ? "/" + bass : "");
}

function lookupFingering(name, table) {
  const tryName = (n) => {
    if (table[n]) return table[n];
    const base = n.split("/")[0];
    if (table[base]) return table[base];
    let m = /^([A-G]#?)([0-9])$/.exec(base);
    if (m && m[2] === "5") return table[m[1]] || null;
    if (m && m[2] === "4") return table[m[1] + "sus4"] || null;
    m = /^([A-G]#?(?:m)?)(?:dim|aug|\+)([0-9]*)$/.exec(base);
    if (m) return table[m[1] + "dim7"] || table[m[1]] || null;
    if (base.endsWith("+")) return table[base.slice(0, -1) + "aug"] || table[base.slice(0, -1)] || null;
    return null;
  };
  const direct = tryName(name);
  if (direct) return direct;
  // the curated tables mix sharp and flat spellings for the same pitch
  // (e.g. ukulele only lists "Db", not "C#") — try the enharmonic flip too
  const parts = splitRootBass(name);
  if (!parts) return null;
  const FLAT = { "C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb" };
  const flat = FLAT[parts.root];
  if (!flat) return null;
  return tryName(flat + parts.rest + (parts.bass ? "/" + parts.bass : ""));
}

function shiftFingering(fingering, semitones) {
  const n = ((semitones % 12) + 12) % 12;      // 0..11
  const delta = n > 6 ? n - 12 : n;            // shortest circular step, -5..6
  const apply = (d) => {
    const out = [];
    for (const ch of fingering) {
      if (ch === "x") { out.push("x"); continue; }
      const fret = parseInt(ch, 16) + d;
      // a fret must fit one hex digit (0-15); either direction can miss —
      // the short one by going negative (an open string can't un-fret),
      // the long one by pushing an already-high fret past 15
      if (fret < 0 || fret > 15) return null;
      out.push(fret.toString(16));
    }
    return out.join("");
  };
  return apply(delta) ?? apply(delta < 0 ? delta + 12 : delta - 12);
}

function fingerFor(rawToken, semitones, originalFingering, table) {
  if (semitones === 0) return { name: rawToken, fingering: originalFingering };
  const targetName = transposeName(normalizeToken(rawToken), semitones);
  const exact = lookupFingering(targetName, table);
  if (exact) return { name: targetName, fingering: exact };
  return { name: targetName, fingering: shiftFingering(originalFingering, semitones) };
}

function transposedLabel(rawToken, semitones) {
  if (semitones === 0) return rawToken;
  return transposeName(normalizeToken(rawToken), semitones);
}

function renderAll(offset) {
  document.querySelectorAll(".ch[data-chord]").forEach((el) => {
    const raw = el.dataset.chord;
    el.textContent = offset === 0 ? raw : transposedLabel(raw, offset);
  });
  document.querySelectorAll(".fingering[data-chord]").forEach((el) => {
    const raw = el.dataset.chord;
    const orig = el.dataset.fingering;
    if (offset === 0) {
      el.textContent = `${raw} ${orig}`;
      return;
    }
    const table = CHORDS_DATA.FINGERINGS[el.dataset.instrument];
    const { name, fingering } = fingerFor(raw, offset, orig, table);
    // fingering is null when no fret shape fits (see chords.js
    // shiftFingering) — show the chord name alone rather than "null"
    el.textContent = fingering ? `${name} ${fingering}` : name;
  });
  const label = document.querySelector(".offset-label");
  if (label) label.textContent = offset > 0 ? `+${offset}` : String(offset);
}

const OFFSET_STORAGE_PREFIX = "chord-offset:";

function loadStoredOffset() {
  try {
    const raw = localStorage.getItem(OFFSET_STORAGE_PREFIX + location.pathname);
    const n = raw === null ? 0 : parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0; // localStorage unavailable (private mode, blocked, ...) — start plain
  }
}

function storeOffset(offset) {
  try {
    const key = OFFSET_STORAGE_PREFIX + location.pathname;
    if (offset === 0) localStorage.removeItem(key);
    else localStorage.setItem(key, String(offset));
  } catch {
    // ignore — nothing to persist to
  }
}

function initTranspose() {
  const controls = document.querySelector(".transpose-controls");
  if (!controls) return;
  let offset = loadStoredOffset();
  renderAll(offset); // apply a restored transposition immediately, if any
  controls.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    if (btn.dataset.action === "up") offset += 1;
    else if (btn.dataset.action === "down") offset -= 1;
    else offset = 0;
    storeOffset(offset);
    renderAll(offset);
  });
}

// --- digitație la hover/focus (tooltip) --------------------------------

const STRING_COUNT = { guitar: 6, ukulele: 4 };

function buildFingeringSVG(fingering, nStrings) {
  const w = 14, h = 18, padTop = 20, padLeft = 8, rows = 4;
  const width = padLeft * 2 + w * (nStrings - 1);
  const height = padTop + h * rows + 6;
  const fretted = fingering.split("").map((c) => (c === "x" ? null : parseInt(c, 16)));
  const played = fretted.filter((f) => f !== null);
  const maxFret = played.length ? Math.max(...played) : 0;
  const base = maxFret > rows ? maxFret - rows + 1 : 1; // "capo" fret for high barre shapes

  let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">`;
  for (let s = 0; s < nStrings; s++) {
    const x = padLeft + s * w;
    svg += `<line x1="${x}" y1="${padTop}" x2="${x}" y2="${padTop + h * rows}" stroke="#333"/>`;
  }
  for (let f = 0; f <= rows; f++) {
    const y = padTop + f * h;
    const strokeW = base === 1 && f === 0 ? 3 : 1; // thick nut only at the real fret 0
    svg += `<line x1="${padLeft}" y1="${y}" x2="${padLeft + w * (nStrings - 1)}" y2="${y}" stroke="#333" stroke-width="${strokeW}"/>`;
  }
  if (base > 1) {
    svg += `<text x="1" y="${padTop + h - 4}" font-size="9" fill="#333">${base}</text>`;
  }
  for (let s = 0; s < nStrings; s++) {
    const x = padLeft + s * w;
    const f = fretted[s];
    if (f === null) {
      svg += `<text x="${x - 3}" y="${padTop - 7}" font-size="10" fill="#8b1a1a">×</text>`;
    } else if (f === 0) {
      svg += `<circle cx="${x}" cy="${padTop - 6}" r="3" fill="none" stroke="#333" stroke-width="1.2"/>`;
    } else {
      const y = padTop + h * (f - base) + h / 2;
      svg += `<circle cx="${x}" cy="${y}" r="4" fill="#8b1a1a"/>`;
    }
  }
  svg += `</svg>`;
  return svg;
}

function currentFingeringFor(rawChord, instrument) {
  // reads the fingering-line span's CURRENT (possibly already-transposed)
  // text, rather than recomputing — keeps the tooltip in sync with
  // whatever renderAll last drew, with no duplicated logic
  const el = document.querySelector(
    '.fingering[data-chord="' + rawChord + '"][data-instrument="' + instrument + '"]'
  );
  if (!el) return null;
  const parts = el.textContent.trim().split(/\s+/);
  const last = parts[parts.length - 1];
  return /^[0-9a-fx]+$/.test(last) ? last : null;
}

function tooltipContentFor(el) {
  const raw = el.dataset.chord;
  if (el.classList.contains("fingering")) {
    const instrument = el.dataset.instrument;
    const fingering = currentFingeringFor(raw, instrument);
    return fingering ? buildFingeringSVG(fingering, STRING_COUNT[instrument]) : null;
  }
  const parts = [];
  for (const instrument of ["guitar", "ukulele"]) {
    const fingering = currentFingeringFor(raw, instrument);
    if (fingering) parts.push(buildFingeringSVG(fingering, STRING_COUNT[instrument]));
  }
  return parts.length ? parts.join("") : null;
}

function initFingeringTooltip() {
  const tip = document.createElement("div");
  tip.className = "chord-tooltip";
  tip.hidden = true;
  document.body.appendChild(tip);

  const show = (el) => {
    const content = tooltipContentFor(el);
    if (!content) return;
    // content is always SVG built by buildFingeringSVG from a fingering
    // string already regex-validated to [0-9a-fx] (currentFingeringFor)
    // plus a computed integer (base fret) — never free-form/user text —
    // so this innerHTML assignment has no injectable input
    tip.innerHTML = content;
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const tr = tip.getBoundingClientRect();
    let left = r.left + r.width / 2 - tr.width / 2;
    left = Math.max(4, Math.min(left, window.innerWidth - tr.width - 4));
    let top = r.top - tr.height - 6;
    if (top < 4) top = r.bottom + 6;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  };
  const hide = () => { tip.hidden = true; };

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest(".ch[data-chord], .fingering[data-chord]");
    if (el) show(el);
  });
  document.addEventListener("mouseout", (e) => {
    const el = e.target.closest(".ch[data-chord], .fingering[data-chord]");
    if (el) hide();
  });
  // keyboard access: only the fingering-summary line (a handful of spans
  // per song) gets a tab stop — making every inline lyric chord tabbable
  // would turn a song page into hundreds of tab stops
  document.querySelectorAll(".fingering[data-chord]").forEach((el) => {
    el.tabIndex = 0;
    el.addEventListener("focus", () => show(el));
    el.addEventListener("blur", hide);
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", initTranspose);
  document.addEventListener("DOMContentLoaded", initFingeringTooltip);
}

if (typeof module !== "undefined") {
  module.exports = {
    normalizeToken, transposeNote, transposeName, splitRootBass,
    lookupFingering, shiftFingering, fingerFor, transposedLabel,
    buildFingeringSVG,
  };
}
