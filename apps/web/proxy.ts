import { NextResponse, type NextRequest } from "next/server";
import { buildCsp, newNonce } from "./lib/csp";

// Optimistic routing only. The `fixify_session` cookie carries no credential; every API call is
// authorized by FastAPI, so a forged cookie only reaches pages that then show "signed out".
const APP_PREFIXES = ["/dashboard", "/projects", "/scans", "/findings", "/fixes", "/github", "/analytics", "/notifications", "/settings"];
const AUTH_PAGES = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = request.cookies.has("fixify_session");
  if (!signedIn && APP_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  if (signedIn && AUTH_PAGES.includes(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Per-request nonce: Next.js reads it from the request's CSP header while rendering and adds
  // it to every framework script (pages are rendered per request; see app/layout.tsx).
  const nonce = newNonce();
  const csp = buildCsp(nonce, process.env.NODE_ENV === "development");
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
