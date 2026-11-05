"use client";

import {
  ArrowRight,
  Brain,
  Bug,
  Camera,
  Check,
  CheckCircle2,
  Eye,
  FileWarning,
  GitBranch,
  GitPullRequest,
  Globe,
  ImageOff,
  KeyRound,
  Link2Off,
  Lock,
  Network,
  Radar,
  ScanSearch,
  ServerCrash,
  ShieldCheck,
  Sparkles,
  Terminal,
  UserCheck,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/brand";
import { SeverityBadge, SeverityBar } from "@/components/status";
import { ButtonLink } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/primitives";

function Section({ id, eyebrow, title, description, children }: { id?: string; eyebrow: string; title: ReactNode; description: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-6xl px-5 py-20 sm:py-24">
      <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }} className="mx-auto mb-12 max-w-2xl text-center">
        <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-violet-soft">{eyebrow}</p>
        <h2 className="mt-3 text-[28px] font-semibold tracking-tight sm:text-[36px]">{title}</h2>
        <p className="mt-3 text-[15px] text-muted">{description}</p>
      </motion.div>
      {children}
    </section>
  );
}

function Feature({ icon: Icon, title, children, delay = 0 }: { icon: typeof Bug; title: string; children: ReactNode; delay?: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.4, delay }}>
      <Card hover className="h-full p-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-violet/25 bg-violet/10 text-violet-soft"><Icon className="h-4 w-4" /></span>
        <h3 className="mt-4 text-[14.5px] font-semibold">{title}</h3>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{children}</p>
      </Card>
    </motion.div>
  );
}

function FilamentBackdrop() {
  const filaments = [
    "M 1050 -70 C 930 40 872 158 759 257 C 668 337 720 387 827 396 C 932 405 1010 485 1080 700",
    "M 1100 8 C 977 121 864 190 766 276 C 704 331 743 379 834 398 C 936 419 1009 506 1032 740",
    "M 1120 92 C 1014 196 913 231 790 300 C 721 339 753 389 845 404 C 936 419 987 565 1008 760",
    "M 1110 176 C 1003 250 910 268 806 323 C 747 355 776 398 856 410 C 939 423 950 582 975 770",
    "M 1090 260 C 990 305 899 312 826 349 C 775 375 793 405 865 416 C 934 426 914 590 944 775",
    "M 1080 356 C 983 366 910 351 841 377 C 804 391 811 414 876 422 C 930 429 887 608 914 775",
    "M 1070 450 C 982 423 919 394 855 399 C 822 402 823 422 883 430 C 929 436 860 627 884 775",
    "M 1060 545 C 986 487 929 440 866 423 C 837 415 832 432 887 440 C 926 446 834 648 855 775",
    "M 1040 650 C 980 546 925 485 871 447 C 848 431 841 443 890 454 C 925 462 811 669 828 775",
    "M 995 760 C 972 624 918 530 876 474 C 860 452 851 461 894 472 C 924 480 786 687 800 775",
  ];

  return (
    <svg
      className="pointer-events-none absolute inset-y-0 -right-[22%] h-full w-[100%] opacity-80 sm:-right-[12%] sm:w-[86%]"
      viewBox="0 0 1100 760"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="filament-gradient" x1="180" y1="180" x2="1050" y2="570" gradientUnits="userSpaceOnUse">
          <stop stopColor="#8b5cf6" stopOpacity="0" />
          <stop offset=".45" stopColor="#8b5cf6" stopOpacity=".45" />
          <stop offset=".78" stopColor="#818cf8" stopOpacity=".95" />
          <stop offset="1" stopColor="#67e8f9" stopOpacity=".8" />
        </linearGradient>
        <radialGradient id="filament-core">
          <stop stopColor="#fff" stopOpacity=".95" />
          <stop offset=".16" stopColor="#c4b5fd" stopOpacity=".8" />
          <stop offset=".48" stopColor="#818cf8" stopOpacity=".24" />
          <stop offset="1" stopColor="#818cf8" stopOpacity="0" />
        </radialGradient>
        <filter id="filament-blur" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="9" />
        </filter>
        <filter id="filament-halo" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="24" />
        </filter>
      </defs>

      <circle cx="850" cy="405" r="220" fill="url(#filament-core)" filter="url(#filament-halo)" opacity=".55" />
      <g stroke="url(#filament-gradient)" strokeLinecap="round">
        {filaments.map((path, index) => (
          <g key={path} className="filament-flow" style={{ animationDelay: `${index * -1.7}s` }}>
            <path d={path} strokeWidth="13" opacity=".48" filter="url(#filament-blur)" />
            <path d={path} strokeWidth={index % 3 === 0 ? 1.5 : 0.8} opacity={index % 2 === 0 ? 0.76 : 0.48} />
          </g>
        ))}
      </g>
      <circle cx="850" cy="405" r="105" fill="url(#filament-core)" opacity=".72" />
      <circle cx="850" cy="405" r="12" fill="#fff" opacity=".85" filter="url(#filament-blur)" />
    </svg>
  );
}

/** A representative, static rendering of the dashboard: illustrative content, not customer data. */
function ProductPreview() {
  const rows: { title: string; severity: "critical" | "high" | "medium" | "low"; type: string }[] = [
    { title: "Uncaught TypeError: cart.items is undefined", severity: "high", type: "Uncaught exception" },
    { title: "Script /static/js/app.4f2c.js returned HTTP 404", severity: "high", type: "HTTP error" },
    { title: "Broken link: /pricing/enterprise (404)", severity: "medium", type: "Broken link" },
    { title: "3 image(s) without alternative text", severity: "low", type: "Accessibility" },
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 28, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, delay: 0.25, ease: [0.22, 1, 0.36, 1] }} className="relative mx-auto max-w-5xl">
      <div className="absolute -inset-x-10 -top-10 bottom-0 -z-10 rounded-[40px] bg-gradient-to-b from-violet/20 via-cyan/5 to-transparent blur-3xl" aria-hidden />
      <Card className="overflow-hidden border-line/80 bg-panel/90 backdrop-blur">
        <div className="flex items-center gap-2 border-b border-line-soft px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-critical/70" /><span className="h-2.5 w-2.5 rounded-full bg-warning/70" /><span className="h-2.5 w-2.5 rounded-full bg-success/70" />
          <span className="ml-3 truncate rounded-md bg-elevated/70 px-3 py-0.5 font-mono text-[11px] text-muted">fixify.app/scans/report</span>
          <Badge className="ml-auto" tone="violet">Product preview · illustrative data</Badge>
        </div>
        <div className="grid gap-0 md:grid-cols-[1fr_300px]">
          <div className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[15px] font-semibold">shop.example.com</p>
              <Badge tone="success">Completed</Badge>
              <span className="text-[12px] text-muted">9 checks · 14.2 s · headless Chromium</span>
            </div>
            <SeverityBar className="mt-4" counts={{ critical: 0, high: 2, medium: 1, low: 1, info: 0 }} />
            <ul className="mt-4 divide-y divide-line-soft rounded-xl border border-line-soft bg-card/60">
              {rows.map((row) => (
                <li key={row.title} className="flex items-center gap-3 px-4 py-3">
                  <SeverityBadge severity={row.severity} />
                  <span className="min-w-0 flex-1 truncate text-[13px]">{row.title}</span>
                  <span className="hidden text-[11.5px] text-subtle sm:block">{row.type}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="border-t border-line-soft bg-card/40 p-5 md:border-l md:border-t-0">
            <p className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-violet-soft"><Sparkles className="h-3.5 w-3.5" /> AI analysis</p>
            <p className="mt-2 text-[13px] leading-relaxed text-ink/85">The checkout script reads <span className="font-mono text-cyan">cart.items</span> before the cart request resolves, so the page throws for first-time visitors.</p>
            <div className="mt-4 overflow-hidden rounded-lg border border-line-soft font-mono text-[11.5px]">
              <div className="bg-critical/10 px-3 py-1 text-critical/90">− const total = cart.items.length;</div>
              <div className="bg-success/10 px-3 py-1 text-success/90">+ const total = cart.items?.length ?? 0;</div>
            </div>
            <div className="mt-4 flex gap-2">
              <span className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-success/30 bg-success/10 py-1.5 text-[12px] text-success"><Check className="h-3.5 w-3.5" /> Approve</span>
              <span className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line py-1.5 text-[12px] text-muted"><X className="h-3.5 w-3.5" /> Reject</span>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

export function LandingPage() {
  return (
    <div className="ambient min-h-screen overflow-x-hidden">
      <header className="sticky top-0 z-30 border-b border-line-soft/70 bg-canvas/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-5">
          <Logo />
          <nav className="hidden items-center gap-6 text-[13.5px] text-muted md:flex" aria-label="Product">
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#scanning" className="hover:text-ink">Scanning</a>
            <a href="#ai" className="hover:text-ink">AI analysis</a>
            <a href="#github" className="hover:text-ink">GitHub</a>
            <a href="#security" className="hover:text-ink">Security</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ButtonLink href="/login" variant="ghost" size="sm">Sign in</ButtonLink>
            <ButtonLink href="/register" size="sm">Start testing</ButtonLink>
          </div>
        </div>
      </header>

      <main>
        <section className="relative flex min-h-[calc(100svh-4rem)] items-center">
          <div className="grid-backdrop pointer-events-none absolute inset-0 -z-0" aria-hidden />
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
            <div className="absolute inset-0 bg-gradient-to-r from-canvas via-canvas/90 to-transparent sm:via-canvas/75" />
            <div className="absolute inset-0 bg-gradient-to-t from-canvas/45 via-transparent to-canvas/20" />
            <FilamentBackdrop />
          </div>
          <div className="relative mx-auto w-full max-w-6xl px-5 py-20 sm:py-28">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
              <h1 className="max-w-3xl text-[40px] font-semibold leading-[1.05] tracking-tight sm:text-[64px]">
                Find Bugs.<br className="hidden sm:block" /> <span className="text-gradient">Understand Them.</span><br />Fix Them.
              </h1>
              <p className="mt-6 max-w-xl text-[16px] leading-relaxed text-muted sm:text-[17px]">
                An intelligent website testing platform that detects real-world issues, explains what went wrong, and helps your team generate human-reviewed fixes.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <ButtonLink href="/register" size="lg">Start Testing <ArrowRight className="h-4 w-4" /></ButtonLink>
                <ButtonLink href="#how" size="lg" variant="secondary">Explore Features</ButtonLink>
              </div>
            </motion.div>
          </div>
        </section>

        <section aria-label="Product preview" className="relative border-y border-line-soft/70 bg-panel/30 px-5 py-12 sm:py-16">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-violet/[0.04] via-transparent to-cyan/[0.03]" aria-hidden />
          <div className="relative">
            <ProductPreview />
          </div>
        </section>

        <Section id="how" eyebrow="How Fixify works" title="From a URL to a reviewed pull request" description="Every step produces evidence you can inspect. Nothing reaches your repository without your approval.">
          <ol className="grid gap-4 md:grid-cols-4">
            {[
              { icon: Globe, title: "Add a website", text: "Create a project for a site you are authorized to test." },
              { icon: Radar, title: "Scan in a real browser", text: "Headless Chromium loads the page and records what actually breaks." },
              { icon: Brain, title: "Understand the cause", text: "AI explains each finding from the recorded evidence, with a confidence level." },
              { icon: GitPullRequest, title: "Approve the fix", text: "Review the diff; approved fixes become pull requests on new branches." },
            ].map(({ icon: Icon, title, text }, index) => (
              <motion.li key={title} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.4, delay: index * 0.08 }}>
                <Card className="relative h-full p-5">
                  <span className="absolute right-4 top-4 font-mono text-[12px] text-subtle">0{index + 1}</span>
                  <Icon className="h-5 w-5 text-cyan" />
                  <h3 className="mt-4 text-[14.5px] font-semibold">{title}</h3>
                  <p className="mt-1.5 text-[13px] text-muted">{text}</p>
                </Card>
              </motion.li>
            ))}
          </ol>
        </Section>

        <Section id="scanning" eyebrow="Website scanning" title="Checks that catch what users actually hit" description="Rule-based, reproducible checks. Uncertain results are marked as suspected, never reported as confirmed bugs.">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Feature icon={Terminal} title="JavaScript errors">Console errors and uncaught exceptions with bounded, sanitized stack traces.</Feature>
            <Feature icon={Network} title="Failed requests" delay={0.05}>Network failures and 4xx/5xx responses, weighted by resource type and first or third party.</Feature>
            <Feature icon={Link2Off} title="Broken links" delay={0.1}>Confirmed 404/410s, suspected 5xx and DNS failures, and inconclusive results kept separate.</Feature>
            <Feature icon={ImageOff} title="Images and accessibility">Broken images, missing alternative text, heading structure, and viewport metadata.</Feature>
            <Feature icon={FileWarning} title="Mixed content and metadata" delay={0.05}>Insecure resources on HTTPS pages, missing titles, descriptions, and favicons.</Feature>
            <Feature icon={Camera} title="Screenshots and comparison" delay={0.1}>Viewport screenshots, plus new, resolved, and unchanged issues against the previous scan.</Feature>
          </div>
        </Section>

        <Section id="ai" eyebrow="AI bug analysis" title="Explanations grounded in evidence" description="The model only analyzes what the scanner recorded. If AI is not configured, Fixify says so instead of guessing.">
          <div className="grid gap-4 lg:grid-cols-3">
            <Feature icon={ScanSearch} title="Root cause and impact">A plain-language summary, the likely cause, who is affected, and why it matters.</Feature>
            <Feature icon={Bug} title="Grouped and related issues" delay={0.05}>Duplicates and findings with the same cause are linked together.</Feature>
            <Feature icon={Eye} title="Prompt-injection aware" delay={0.1}>Website and repository content is treated as untrusted data; secrets are removed before anything is sent.</Feature>
          </div>
        </Section>

        <Section id="github" eyebrow="GitHub integration" title="Your code, read safely" description="Fixify reads only the files it needs through the GitHub API. Repositories are never cloned or executed.">
          <div className="grid gap-4 md:grid-cols-3">
            <Feature icon={GitBranch} title="Connect and choose a branch">OAuth connection, repository and branch selection, and live connection status.</Feature>
            <Feature icon={KeyRound} title="Encrypted tokens" delay={0.05}>Access tokens are encrypted at rest and never reach the browser.</Feature>
            <Feature icon={Lock} title="Strict file limits" delay={0.1}>Secrets, dependencies, and build output are never read; size and file count are capped.</Feature>
          </div>
        </Section>

        <Section eyebrow="Human-reviewed fixes" title="AI proposes. You decide." description="Each proposal shows the original and proposed code, an explanation, a confidence level, and validation results.">
          <div className="grid items-center gap-8 lg:grid-cols-2">
            <ul className="space-y-4">
              {[
                ["Side-by-side diff review", "Syntax-highlighted original and proposed code with added and removed lines."],
                ["Validation before approval", "Edits must match the real file exactly; JSON, Python, markup, and brackets are checked."],
                ["Approve, reject, comment, regenerate", "Your feedback goes into the next version; earlier versions stay in the history."],
                ["Pull requests, never merges", "Approved fixes are committed to a new branch and opened as a pull request."],
              ].map(([title, text]) => (
                <li key={title} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
                  <div><p className="text-[14.5px] font-medium">{title}</p><p className="text-[13.5px] text-muted">{text}</p></div>
                </li>
              ))}
            </ul>
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-line-soft px-4 py-2.5 text-[12.5px]">
                <span className="font-mono text-ink/90">src/app/layout.tsx</span>
                <Badge tone="violet">Illustrative</Badge>
              </div>
              <div className="code-font">
                {[
                  ["  ", "<head>", ""],
                  ["−", '  <meta charset="utf-8" />', "remove"],
                  ["+", '  <meta charset="utf-8" />', "add"],
                  ["+", "  <title>Acme Store</title>", "add"],
                  ["+", '  <meta name="viewport" content="width=device-width" />', "add"],
                  ["  ", "</head>", ""],
                ].map(([sign, text, kind], index) => (
                  <div key={index} className={kind === "add" ? "bg-success/10 text-success/90" : kind === "remove" ? "bg-critical/10 text-critical/90" : "text-ink/70"}>
                    <span className="inline-block w-8 select-none text-center">{sign}</span>{text}
                  </div>
                ))}
              </div>
              <div className="flex gap-2 border-t border-line-soft p-3">
                <span className="flex items-center gap-1.5 rounded-md border border-success/30 bg-success/10 px-3 py-1 text-[12px] text-success"><UserCheck className="h-3.5 w-3.5" /> Approved by you</span>
                <span className="flex items-center gap-1.5 rounded-md border border-line px-3 py-1 text-[12px] text-muted"><GitPullRequest className="h-3.5 w-3.5" /> Pull request</span>
              </div>
            </Card>
          </div>
        </Section>

        <Section id="security" eyebrow="Security" title="Built for untrusted input" description="Fixify loads arbitrary websites and reads external repositories, so isolation and least privilege are core requirements.">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Feature icon={ShieldCheck} title="SSRF protection">Every browser connection passes an egress proxy that blocks private, internal, and metadata addresses.</Feature>
            <Feature icon={ServerCrash} title="Isolated scanner" delay={0.05}>Scans run in a separate process without database or queue credentials, with hard time limits.</Feature>
            <Feature icon={UserCheck} title="Strict ownership" delay={0.1}>Every project, scan, finding, and fix is scoped to its owner on the server.</Feature>
            <Feature icon={KeyRound} title="Redaction" delay={0.15}>Tokens, cookies, credentials, and secret-looking parameters are stripped from evidence.</Feature>
          </div>
        </Section>

        <section className="mx-auto max-w-6xl px-5 pb-24">
          <Card className="relative overflow-hidden px-6 py-14 text-center sm:px-12">
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-violet/25 via-transparent to-cyan/15" aria-hidden />
            <h2 className="text-[28px] font-semibold tracking-tight sm:text-[34px]">Find out what your users are running into.</h2>
            <p className="mx-auto mt-3 max-w-xl text-[15px] text-muted">Create an account, add a website you are authorized to test, and get your first real-browser report in under a minute.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <ButtonLink href="/register" size="lg">Start Testing <ArrowRight className="h-4 w-4" /></ButtonLink>
              <ButtonLink href="/login" size="lg" variant="secondary">Sign in</ButtonLink>
            </div>
          </Card>
        </section>
      </main>

      <footer className="border-t border-line-soft">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <p>Find bugs. Understand problems. Generate fixes. Keep humans in control.</p>
          <nav className="flex gap-4" aria-label="Footer">
            <Link href="/login" className="hover:text-ink">Sign in</Link>
            <Link href="/register" className="hover:text-ink">Create account</Link>
            <a href="#security" className="hover:text-ink">Security</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
