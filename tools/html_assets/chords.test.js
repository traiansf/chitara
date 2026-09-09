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
  FINGERINGS: { guitar: {}, ukulele: {} },
};
const src = fs.readFileSync(path.join(__dirname, "chords.js"), "utf8");
new Function("module", "exports", src)(module, module.exports);
const { normalizeToken, transposeNote, transposeName } = module.exports;

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
