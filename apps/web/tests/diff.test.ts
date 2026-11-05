import assert from "node:assert/strict";
import { test } from "node:test";
import { diffLines, diffStats, toSplit } from "../lib/diff.ts";

test("identical text has no changes", () => {
  const rows = diffLines("a\nb\n", "a\nb\n", 10);
  assert.deepEqual(diffStats(rows), { added: 0, removed: 0 });
  assert.deepEqual(rows.map((r) => r.type === "equal" && [r.oldNo, r.newNo]), [[10, 10], [11, 11]]);
});

test("an inserted line is an addition with correct numbering", () => {
  const rows = diffLines("<head>\n</head>\n", "<head>\n  <title>x</title>\n</head>\n", 5);
  assert.deepEqual(rows, [
    { type: "equal", oldNo: 5, newNo: 5, text: "<head>" },
    { type: "add", newNo: 6, text: "  <title>x</title>" },
    { type: "equal", oldNo: 6, newNo: 7, text: "</head>" },
  ]);
});

test("a changed line pairs removal and addition side by side", () => {
  const split = toSplit(diffLines("const a = 1;\nkeep();\n", "const a = 2;\nkeep();\n"));
  assert.equal(split.length, 2);
  assert.deepEqual(split[0], {
    left: { no: 1, text: "const a = 1;", kind: "remove" },
    right: { no: 1, text: "const a = 2;", kind: "add" },
  });
  assert.equal(split[1].left?.kind, "equal");
});

test("uneven blocks leave blank cells instead of misaligning", () => {
  const split = toSplit(diffLines("x\n", "y\nz\n"));
  assert.equal(split.length, 2);
  assert.equal(split[1].left, null);
  assert.equal(split[1].right?.text, "z");
});

test("deleting everything is all removals", () => {
  assert.deepEqual(diffStats(diffLines("a\nb\nc", "")), { added: 1, removed: 3 });
});
