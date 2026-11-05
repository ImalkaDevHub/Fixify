"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, MailCheck, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { authApi } from "@/lib/api";
import { errorText } from "@/lib/hooks";
import { loginSchema, registerSchema, resetSchema, type LoginValues, type RegisterValues, type ResetValues } from "@/lib/schemas";
import { Logo } from "@/components/brand";
import { Button, ButtonLink } from "@/components/ui/button";
import { Alert, Card, FieldError, Input, Label, Reveal } from "@/components/ui/primitives";

function AuthFrame({ title, subtitle, children, footer }: { title: string; subtitle: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="ambient relative flex min-h-screen items-center justify-center px-4 py-12">
      <div className="grid-backdrop pointer-events-none absolute inset-0" aria-hidden />
      <Reveal className="relative w-full max-w-[420px]">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <Card className="p-7">
          <h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-[13.5px] text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </Card>
        {footer && <div className="mt-5 text-center text-[13px] text-muted">{footer}</div>}
      </Reveal>
    </div>
  );
}

/** Only same-site paths are accepted as a post-login destination (no open redirects). */
function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? value : "/dashboard";
}

function tokenFromHash(): string | null {
  if (typeof window === "undefined") return null;
  const match = window.location.hash.match(/token=([^&]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const user = await authApi.login(values.email, values.password);
      queryClient.setQueryData(["me"], user);
      router.replace(safeNext(params.get("next")));
    } catch (reason) {
      setError(errorText(reason, "Could not sign in."));
    }
  });
  return (
    <AuthFrame
      title="Welcome back"
      subtitle="Sign in to review scans, findings, and proposed fixes."
      footer={<>New to Fixify? <Link className="text-violet-soft hover:text-ink" href="/register">Create an account</Link></>}
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!form.formState.errors.email} {...form.register("email")} />
          <FieldError message={form.formState.errors.email?.message} />
        </div>
        <div>
          <Label htmlFor="password" hint={<Link href="/forgot-password" className="text-violet-soft hover:text-ink">Forgot password?</Link>}>Password</Label>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!form.formState.errors.password} {...form.register("password")} />
          <FieldError message={form.formState.errors.password?.message} />
        </div>
        <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>
          Sign in <ArrowRight className="h-4 w-4" />
        </Button>
      </form>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({ resolver: zodResolver(registerSchema), defaultValues: { display_name: "", email: "", password: "" } });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const user = await authApi.register(values);
      queryClient.setQueryData(["me"], user);
      router.replace("/dashboard");
    } catch (reason) {
      setError(errorText(reason, "Could not create the account."));
    }
  });
  const errors = form.formState.errors;
  return (
    <AuthFrame
      title="Create your account"
      subtitle="Start testing websites in a real browser. Free to try, no card needed."
      footer={<>Already have an account? <Link className="text-violet-soft hover:text-ink" href="/login">Sign in</Link></>}
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <div>
          <Label htmlFor="display_name">Name</Label>
          <Input id="display_name" autoComplete="name" aria-invalid={!!errors.display_name} {...form.register("display_name")} />
          <FieldError message={errors.display_name?.message} />
        </div>
        <div>
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...form.register("email")} />
          <FieldError message={errors.email?.message} />
        </div>
        <div>
          <Label htmlFor="password" hint="10+ characters">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" aria-invalid={!!errors.password} {...form.register("password")} />
          <FieldError message={errors.password?.message} />
        </div>
        <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>
          Create account
        </Button>
        <p className="flex items-start gap-2 text-[12px] text-subtle">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" /> Passwords are hashed with Argon2id. Only scan websites you are authorized to test.
        </p>
      </form>
    </AuthFrame>
  );
}

export function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<{ email: string }>({ resolver: zodResolver(loginSchema.pick({ email: true })), defaultValues: { email: "" } });
  const submit = form.handleSubmit(async ({ email }) => {
    setError(null);
    try {
      setSent((await authApi.forgotPassword(email)).message);
    } catch (reason) {
      setError(errorText(reason));
    }
  });
  return (
    <AuthFrame title="Reset your password" subtitle="We'll email you a single-use link that expires in 30 minutes." footer={<Link className="text-violet-soft hover:text-ink" href="/login">Back to sign in</Link>}>
      {sent ? (
        <Alert tone="success" title="Check your inbox">{sent}</Alert>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          {error && <Alert tone="error">{error}</Alert>}
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
            <FieldError message={form.formState.errors.email?.message} />
          </div>
          <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>Send reset link</Button>
        </form>
      )}
    </AuthFrame>
  );
}

export function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  useEffect(() => setToken(tokenFromHash()), []);
  const form = useForm<ResetValues>({ resolver: zodResolver(resetSchema), defaultValues: { password: "", confirm: "" } });
  const submit = form.handleSubmit(async ({ password }) => {
    if (!token) return;
    setError(null);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      window.history.replaceState(null, "", "/reset-password");
      setTimeout(() => router.replace("/login"), 1800);
    } catch (reason) {
      setError(errorText(reason));
    }
  });
  return (
    <AuthFrame title="Choose a new password" subtitle="All other sessions are signed out when you change it.">
      {done ? (
        <Alert tone="success" title="Password changed">Redirecting you to sign in…</Alert>
      ) : !token ? (
        <Alert tone="warning" title="This link is incomplete">Open the reset link from your email, or <Link href="/forgot-password" className="underline">request a new one</Link>.</Alert>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          {error && <Alert tone="error">{error}</Alert>}
          <div>
            <Label htmlFor="password">New password</Label>
            <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
            <FieldError message={form.formState.errors.password?.message} />
          </div>
          <div>
            <Label htmlFor="confirm">Confirm password</Label>
            <Input id="confirm" type="password" autoComplete="new-password" {...form.register("confirm")} />
            <FieldError message={form.formState.errors.confirm?.message} />
          </div>
          <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>Change password</Button>
        </form>
      )}
    </AuthFrame>
  );
}

export function VerifyEmailPage() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<"working" | "done" | "error" | "missing">("working");
  const [error, setError] = useState("");
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = tokenFromHash();
    if (!token) {
      setState("missing");
      return;
    }
    authApi
      .verifyEmail(token)
      .then((user) => {
        queryClient.setQueryData(["me"], (current: unknown) => (current ? user : current));
        setState("done");
        window.history.replaceState(null, "", "/verify-email");
      })
      .catch((reason) => {
        setError(errorText(reason));
        setState("error");
      });
  }, [queryClient]);
  return (
    <AuthFrame title="Email verification" subtitle="Confirming that this address belongs to you.">
      {state === "working" && <p className="text-[13px] text-muted">Verifying…</p>}
      {state === "done" && (
        <div className="space-y-4">
          <Alert tone="success" title="Email verified">You can now scan websites, run AI analysis, and connect GitHub.</Alert>
          <ButtonLink href="/dashboard" className="w-full" size="lg">
            <CheckCircle2 className="h-4 w-4" /> Go to dashboard
          </ButtonLink>
        </div>
      )}
      {state === "error" && <Alert tone="error" title="Verification failed">{error} Sign in and use “Resend link” to get a new one.</Alert>}
      {state === "missing" && (
        <Alert tone="info" title="Open the link from your email">
          <span className="flex items-center gap-1.5"><MailCheck className="h-4 w-4" /> The verification link contains a one-time code.</span>
        </Alert>
      )}
    </AuthFrame>
  );
}
