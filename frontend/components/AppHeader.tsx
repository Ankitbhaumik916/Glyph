"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

/**
 * Header for the working pages (/verify, /admin, /login).
 *
 * Deliberately NOT fixed: the landing page's floating pill overlapped content
 * once these pages started scrolling. This one scrolls away with the page.
 *
 * The Reviews link renders only for the owner's session, and is absent from
 * the output otherwise - not disabled, not greyed, not in the DOM. That is a
 * presentation choice, though: what actually keeps review data private is the
 * owner check inside /api/reviews, which runs on every request. Nothing here
 * knows which address the owner's is; the server sends back a boolean.
 */
export default function AppHeader({
  current,
}: {
  current: "verify" | "admin" | "login";
}) {
  const { email, isAdmin, loading, logOut } = useAuth();

  const tab = (active: boolean) =>
    `rounded-full px-3 py-1.5 transition-colors ${
      active ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"
    }`;

  return (
    <header className="border-b border-white/10 bg-ink-soft/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 text-sm font-semibold text-white">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/mark-light.png" alt="" aria-hidden="true" className="h-7 w-7" />
          Glyph
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          <Link href="/verify" className={tab(current === "verify")}>
            Tester
          </Link>

          {isAdmin && (
            <Link href="/admin" className={tab(current === "admin")}>
              Reviews
            </Link>
          )}

          {/* Nothing is rendered until the stored token has been checked, so
              the Reviews link never flashes in or out on load. */}
          {loading ? null : email ? (
            <button
              type="button"
              onClick={logOut}
              className="ml-1 rounded-full px-3 py-1.5 text-slate-400 transition-colors hover:text-white"
              title={email}
            >
              Sign out
            </button>
          ) : (
            <Link href="/login" className={tab(current === "login")}>
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
