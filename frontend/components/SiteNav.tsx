"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/** Floating pill nav, like the reference. Gains a solid backing once scrolled. */
export default function SiteNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-50 px-4 pt-4 sm:px-6">
      <nav
        className={`pointer-events-auto mx-auto flex max-w-5xl items-center justify-between gap-4 rounded-full border px-4 py-2.5 backdrop-blur-md transition-colors sm:px-5 ${
          scrolled
            ? "border-white/10 bg-ink/80 shadow-lg shadow-black/40"
            : "border-white/10 bg-white/5"
        }`}
      >
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-amber-400/20 text-amber-300">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M3 17c4-9 7-11 8-9s-2 10 1 9 4-8 6-7" strokeLinecap="round" />
            </svg>
          </span>
          Glyph
        </Link>

        <div className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
          <a href="/#how" className="transition-colors hover:text-white">How it works</a>
          <a href="/#preview" className="transition-colors hover:text-white">What the model sees</a>
          <a href="/#accuracy" className="transition-colors hover:text-white">Accuracy</a>
        </div>

        <Link
          href="/verify"
          className="group inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-amber-200"
        >
          Test a signature
          <span className="grid h-5 w-5 place-items-center rounded-full bg-ink text-white transition-transform group-hover:translate-x-0.5">
            <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={2.5}>
              <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </Link>
      </nav>
    </header>
  );
}
