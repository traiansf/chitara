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

if (typeof module !== "undefined") {
  module.exports = {
    normalizeToken, transposeNote, transposeName, splitRootBass,
    lookupFingering, shiftFingering, fingerFor, transposedLabel,
  };
}
