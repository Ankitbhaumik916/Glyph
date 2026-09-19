import Link from "next/link";

/**
 * Header for the working pages (/verify, /admin).
 *
 * Deliberately NOT fixed: the landing page's floating pill overlapped content
 * once these pages started scrolling. This one scrolls away with the page.
 */
export default function AppHeader({ current }: { current: "verify" | "admin" }) {
  return (
    <header className="border-b border-white/10 bg-ink-soft/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 text-sm font-semibold text-white">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/mark-light.png" alt="" aria-hidden="true" className="h-7 w-7" />
          Glyph
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          <Link
            href="/verify"
            className={`rounded-full px-3 py-1.5 transition-colors ${
              current === "verify" ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            Tester
          </Link>
          <Link
            href="/admin"
            className={`rounded-full px-3 py-1.5 transition-colors ${
              current === "admin" ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            Reviews
          </Link>
        </nav>
      </div>
    </header>
  );
}
