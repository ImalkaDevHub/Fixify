import { NextResponse, type NextRequest } from "next/server";

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
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
