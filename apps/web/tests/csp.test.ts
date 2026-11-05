import assert from "node:assert/strict";
import { test } from "node:test";
import { buildCsp, newNonce } from "../lib/csp.ts";

function directive(csp: string, name: string): string {
  return csp.split("; ").find((part) => part.startsWith(`${name} `)) ?? "";
}

test("production scripts need the nonce: no unsafe-inline, no unsafe-eval", () => {
  const csp = buildCsp("abc123", false);
  const scripts = directive(csp, "script-src");
  assert.match(scripts, /'nonce-abc123'/);
  assert.match(scripts, /'strict-dynamic'/);
  assert.doesNotMatch(scripts, /unsafe-inline/);
  assert.doesNotMatch(scripts, /unsafe-eval/);
  assert.equal(directive(csp, "object-src"), "object-src 'none'");
  assert.equal(directive(csp, "frame-ancestors"), "frame-ancestors 'none'");
  assert.equal(directive(csp, "connect-src"), "connect-src 'self'");
});

test("development adds only what the dev server needs", () => {
  const csp = buildCsp("n", true);
  assert.match(directive(csp, "script-src"), /'unsafe-eval'/);
  assert.doesNotMatch(directive(csp, "script-src"), /unsafe-inline/);
  assert.match(directive(csp, "connect-src"), /ws:/);
});

test("nonces are random and base64", () => {
  const seen = new Set(Array.from({ length: 50 }, () => newNonce()));
  assert.equal(seen.size, 50);
  for (const nonce of seen) assert.match(nonce, /^[A-Za-z0-9+/]{22}==$/);
});
