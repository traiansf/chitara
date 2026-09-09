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

if (typeof module !== "undefined") {
  module.exports = { normalizeToken, transposeNote, transposeName, splitRootBass };
}
