"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import AppHeader from "@/components/AppHeader";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 10; // mirrors auth.MIN_PASSWORD_LENGTH

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { logIn, register, email: signedInAs, loading } = useAuth();

  // ?mode=signup lands straight on the signup form; the toggle switches it.
  const [mode, setMode] = useState<"login" | "signup">(
    params.get("mode") === "signup" ? "signup" : "login",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const next = params.get("next") || "/verify";

  // Already signed in: nothing to do here.
  useEffect(() => {
    if (!loading && signedInAs) router.replace(next);
  }, [loading, signedInAs, next, router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const action = mode === "signup" ? register : logIn;
      await action(email.trim(), password);
      router.replace(next);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? [err.detail.message, err.detail.hint].filter(Boolean).join(" ")
          : "Something went wrong. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  const tooShort = mode === "signup" && password.length > 0 && password.length < MIN_PASSWORD_LENGTH;

  return (
    <main className="mx-auto w-full max-w-md px-4 pb-20 pt-12 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-white">
        {mode === "signup" ? "Create an account" : "Sign in"}
      </h1>
      <p className="mt-1 text-sm text-slate-400">
        {mode === "signup"
          ? "So your feedback on each comparison can be attributed to you."
          : "Welcome back."}
      </p>

      <form className="mt-8 space-y-4" onSubmit={submit}>
        <div>
          <label
            htmlFor="email"
            className="text-xs font-medium uppercase tracking-wide text-slate-400"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            className="mt-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-slate-200 focus:border-amber-400/50 focus:outline-none"
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="text-xs font-medium uppercase tracking-wide text-slate-400"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            className="mt-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-slate-200 focus:border-amber-400/50 focus:outline-none"
          />
          {mode === "signup" && (
            <p className={`mt-1.5 text-xs ${tooShort ? "text-amber-300" : "text-slate-600"}`}>
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={busy || !email.trim() || !password || tooShort}
          className="w-full rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-slate-500"
        >
          {busy ? "Working…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>

        {error && (
          <p role="alert" className="text-xs text-red-400">
            {error}
          </p>
        )}
      </form>

      <p className="mt-6 text-sm text-slate-400">
        {mode === "signup" ? "Already have an account?" : "No account yet?"}{" "}
        <button
          type="button"
          onClick={() => {
            setMode(mode === "signup" ? "login" : "signup");
            setError(null);
          }}
          className="font-medium text-white underline underline-offset-4 hover:text-amber-200"
        >
          {mode === "signup" ? "Sign in" : "Create one"}
        </button>
      </p>

      <p className="mt-10 text-xs leading-relaxed text-slate-600">
        You can compare signatures without an account.{" "}
        <Link href="/verify" className="underline underline-offset-2 hover:text-slate-400">
          Go straight to the tester
        </Link>
        .
      </p>
    </main>
  );
}

export default function LoginPage() {
  return (
    <>
      <AppHeader current="login" />
      {/* useSearchParams needs a Suspense boundary to prerender. */}
      <Suspense fallback={<main className="mx-auto max-w-md px-4 pt-12" />}>
        <LoginForm />
      </Suspense>
    </>
  );
}
