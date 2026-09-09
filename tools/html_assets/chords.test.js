const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// chords.js e un script simplu (fără module/bundler, încărcat cu <script> în
// pagină) care se sprijină pe variabila globală CHORDS_DATA definită de
// chords-data.js. Aici punem un fixture mic înainte de a-l încărca.
global.CHORDS_DATA = {
  NOTES: ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"],
  ALIAS: {
    Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#",
    Dbm: "C#m", Ebm: "D#m", Gbm: "F#m", Abm: "G#m", Bbm: "A#m",
    Cb: "B", Fb: "E", "E#": "F", "B#": "C",
    "Cm#": "C#m", "Fm#": "F#m", CaddG: "C",
  },
  FINGERINGS: {
    guitar: {
      Am: "x02210", Cm: "x35543", "C#m": "x46654",
      G: "320003", D6: "xx0202",
    },
    ukulele: { Am: "2000", Db: "1114" },
  },
};
const src = fs.readFileSync(path.join(__dirname, "chords.js"), "utf8");
new Function("module", "exports", src)(module, module.exports);
const { normalizeToken, transposeNote, transposeName } = module.exports;
const { lookupFingering, shiftFingering, fingerFor, transposedLabel } = module.exports;

test("normalizeToken passes through a plain chord", () => {
  assert.equal(normalizeToken("Am"), "Am");
});

test("normalizeToken resolves a flat to its sharp spelling", () => {
  assert.equal(normalizeToken("Db"), "C#");
});

test("normalizeToken keeps the bass note when resolving the root", () => {
  assert.equal(normalizeToken("Db/F"), "C#/F");
});

test("normalizeToken fixes the source typo Cm#", () => {
  assert.equal(normalizeToken("Cm#"), "C#m");
});

test("transposeNote wraps around the octave upward", () => {
  assert.equal(transposeNote("B", 1), "C");
});

test("transposeNote wraps around the octave downward", () => {
  assert.equal(transposeNote("C", -1), "B");
});

test("transposeName shifts only the root, keeps quality and bass", () => {
  assert.equal(transposeName("D/F#", 2), "E/G#");
});

test("transposeName at offset 0 is a no-op", () => {
  assert.equal(transposeName("Am7", 0), "Am7");
});

test("lookupFingering finds an exact match", () => {
  assert.equal(lookupFingering("Am", CHORDS_DATA.FINGERINGS.guitar), "x02210");
});

test("lookupFingering returns null when nothing matches", () => {
  assert.equal(lookupFingering("F#maj7", CHORDS_DATA.FINGERINGS.guitar), null);
});

test("lookupFingering falls back to the enharmonic-flat spelling", () => {
  // ukulele table only has "Db", not "C#" — a transposed target named "C#"
  // must still find it.
  assert.equal(lookupFingering("C#", CHORDS_DATA.FINGERINGS.ukulele), "1114");
});

test("shiftFingering moves every fretted string by the same amount", () => {
  // Am (x02210) up 3 semitones is the same shape as the curated Cm (x35543)
  assert.equal(shiftFingering("x02210", 3), "x35543");
});

test("shiftFingering takes the shorter circular direction when possible", () => {
  // Am up 3 or down 9 land on the same chord; the shorter step (+3) is used
  assert.equal(shiftFingering("x02210", 3), shiftFingering("x02210", -9));
});

test("shiftFingering never produces a negative fret", () => {
  const r = shiftFingering("x02210", -1); // Am down 1 semitone -> open string would go to -1
  assert.ok(!/-/.test(r));
});

test("shiftFingering falls back to the long way around when the short direction would fret a string below 0", () => {
  // G (320003) down 1 semitone can't be played by un-fretting an open
  // string, so the shape moves up 11 semitones instead — correct (still the
  // same chord), just far up the neck. Accepted limitation: tier 1 (the
  // curated table) covers every root for major/minor/7/m7/dim7, so this
  // path only ever fires for the rarer qualities that have gaps in the
  // curated table, and it never returns a wrong chord, only an awkward one.
  assert.equal(shiftFingering("320003", -1), "edbbbe");
});

test("shiftFingering returns null when no direction keeps every fret within 0-15", () => {
  // Dadd9 (x54230, guitar's real curated shape) down 1 semitone: the short
  // direction takes the open string (fret 0) to -1; the long way around
  // pushes the fret-5 string to 16, past a single hex digit. Neither
  // direction is representable, so there is no valid shift.
  assert.equal(shiftFingering("x54230", -1), null);
});

test("fingerFor prefers the curated exact match over shifting", () => {
  const r = fingerFor("Am", 3, "x02210", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "Cm", fingering: "x35543" });
});

test("fingerFor falls back to shifting the song's own shape when no curated match exists", () => {
  // "D" isn't in this tiny fixture table at all, so tier 2 must fire
  const r = fingerFor("D", 1, "xx0232", CHORDS_DATA.FINGERINGS.guitar);
  assert.equal(r.name, "D#");
});

test("fingerFor at offset 0 returns the original untouched", () => {
  const r = fingerFor("Cm#", 0, "x46654", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "Cm#", fingering: "x46654" });
});

test("fingerFor passes through a null fingering when no valid shift exists and no curated match covers the target", () => {
  // "Dadd9" transposed down 1 semitone targets "C#add9", not in this tiny
  // fixture table, so tier 2 fires and (per the shiftFingering test above)
  // returns null — callers (Task 3) must handle this, never display it as-is
  const r = fingerFor("Dadd9", -1, "x54230", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "C#add9", fingering: null });
});

test("transposedLabel renders the normalized+transposed name", () => {
  assert.equal(transposedLabel("Cm#", 0), "Cm#"); // offset 0: untouched
  // Cm# normalizes to C#m; C#m up 1 semitone is Dm, not "D"
  assert.equal(transposedLabel("Cm#", 1), "Dm");
});
