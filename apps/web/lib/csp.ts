// Content Security Policy, built per request in proxy.ts.
//
// Scripts: only those carrying this request's nonce (Next.js adds it to its own scripts and
// bundles automatically) plus what they load ('strict-dynamic'). No 'unsafe-inline' for
// scripts. 'unsafe-eval' only in development (React's dev tooling needs it).
// Styles: 'unsafe-inline' stays. Motion and Recharts set inline style attributes, which nonces
// cannot cover; style injection cannot run code.
export function buildCsp(nonce: string, isDev: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://avatars.githubusercontent.com",
    "font-src 'self'",
    `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
