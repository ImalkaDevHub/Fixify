import assert from "node:assert/strict";
import { test } from "node:test";
import { formatDuration, hostname, humanize, initials, parseTimestamp, safeInternalLink, timeAgo } from "../lib/utils.ts";

test("notification links must stay on this site", () => {
  assert.equal(safeInternalLink("/fixes/123"), "/fixes/123");
  for (const bad of ["https://evil.example/x", "//evil.example", "javascript:alert(1)", "", null, undefined]) {
    assert.equal(safeInternalLink(bad), null, String(bad));
  }
});

test("formatting helpers", () => {
  assert.equal(formatDuration(null), "—");
  assert.equal(formatDuration(240), "240 ms");
  assert.equal(formatDuration(6500), "6.5 s");
  assert.equal(formatDuration(125_000), "2 min 5 s");
  assert.equal(hostname("https://shop.example.com/a?b"), "shop.example.com");
  assert.equal(hostname("not a url"), "not a url");
  assert.equal(initials("Ada Lovelace"), "AL");
  assert.equal(initials("e2e"), "E2");
  assert.equal(humanize("missing_meta_description"), "Missing meta description");
});

test("timestamps without a zone are UTC", () => {
  assert.equal(parseTimestamp("2026-11-05T01:18:00").toISOString(), "2026-11-05T01:18:00.000Z");
  assert.equal(parseTimestamp("2026-11-05T01:18:00+05:30").toISOString(), "2026-11-04T19:48:00.000Z");
  assert.equal(parseTimestamp("2026-11-05T01:18:00Z").toISOString(), "2026-11-05T01:18:00.000Z");
  const recent = new Date(Date.now() - 30_000).toISOString().replace("Z", "");
  assert.equal(timeAgo(recent), "just now");
});
