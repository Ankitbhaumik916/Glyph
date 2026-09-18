import Link from "next/link";

import Reveal from "@/components/Reveal";
import SiteNav from "@/components/SiteNav";

const STEPS = [
  {
    n: "01",
    title: "Upload two signatures",
    body: "A known-genuine reference and the one in question. Photos of paper are fine - no scanner needed.",
  },
  {
    n: "02",
    title: "Box the signature",
    body: "Drag a box so cloth, fingers and shadows stay out. Its exact size barely matters: the box is re-tightened to the ink itself.",
  },
  {
    n: "03",
    title: "Read the verdict",
    body: "A distance, a threshold, and an honest answer - including 'too close to call' when the pair sits on the boundary.",
  },
];

const FACTS = [
  { value: "0.17-0.23", label: "Equal error rate", note: "on the datasets it was trained against" },
  { value: "~1 in 5", label: "Comparisons it gets wrong", note: "in both directions, at the chosen threshold" },
  { value: "155x155", label: "What the model actually sees", note: "after binarization and stroke normalization" },
];

export default function Landing() {
  return (
    <>
      <SiteNav />

      {/* ---------- Hero ---------- */}
      <section className="relative flex min-h-[100svh] items-center justify-center overflow-hidden">
        <video
          className="absolute inset-0 h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          poster="/media/hero-poster.jpg"
          aria-hidden="true"
        >
          <source src="/media/hero.mp4" type="video/mp4" />
        </video>
        {/* Two washes: one to seat the text, one to blend into the next section. */}
        <div className="absolute inset-0 bg-ink/45" aria-hidden="true" />
        <div
          className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-b from-transparent to-ink"
          aria-hidden="true"
        />

        <div className="relative z-10 mx-auto max-w-4xl px-6 text-center">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-black/30 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-amber-200 backdrop-blur-sm">
            Signature verification
          </p>
          <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl">
            Every hand leaves
            <span className="mt-2 block font-display italic text-amber-200">its own light</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-pretty text-base text-slate-300 sm:text-lg">
            Compare a signature against a known-genuine reference, and see exactly what the
            model saw before it decided.
          </p>

          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/verify"
              className="group inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-ink transition-colors hover:bg-amber-200"
            >
              Test a signature
              <span className="grid h-6 w-6 place-items-center rounded-full bg-ink text-white transition-transform group-hover:translate-x-0.5">
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </Link>
            <a
              href="#how"
              className="rounded-full border border-white/25 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/10"
            >
              How it works
            </a>
          </div>
        </div>

        <div className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2 text-[11px] uppercase tracking-[0.25em] text-white/40">
          Scroll
        </div>
      </section>

      {/* ---------- How it works ---------- */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-24 sm:py-32">
        <Reveal>
          <p className="text-xs font-medium uppercase tracking-[0.25em] text-amber-300">How it works</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Three steps, about a minute
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <Reveal key={step.n} delay={i * 110}>
              <div className="h-full rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.06] to-transparent p-6 transition-colors hover:border-amber-400/30">
                <span className="font-display text-3xl text-amber-300/70">{step.n}</span>
                <h3 className="mt-4 text-lg font-semibold text-white">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{step.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------- What the model sees ---------- */}
      <section id="preview" className="scroll-mt-24 border-y border-white/10 bg-ink-soft">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-24 sm:py-32 lg:grid-cols-2">
          <Reveal>
            <p className="text-xs font-medium uppercase tracking-[0.25em] text-amber-300">Not a black box</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              See what the model actually saw
            </h2>
            <p className="mt-5 text-pretty leading-relaxed text-slate-400">
              Before a score means anything, the signature has to survive preprocessing:
              locating the document, evening out the lighting, separating ink from paper,
              straightening, and thinning every stroke to a constant width.
            </p>
            <p className="mt-4 text-pretty leading-relaxed text-slate-400">
              Glyph shows you that 155&times;155 image for both signatures, live, while you
              adjust the box. If it comes out as paper edges or a thumb instead of strokes,
              you know the score is meaningless - instead of trusting a confident-looking
              number built on nothing.
            </p>
            <Link
              href="/verify"
              className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-amber-300 transition-colors hover:text-amber-200"
            >
              Try it on your own signature
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </Reveal>

          <Reveal delay={140}>
            <div className="rounded-2xl border border-white/10 bg-black/40 p-5 shadow-glow">
              <div className="flex items-center justify-between text-[11px] uppercase tracking-widest text-slate-500">
                <span>Reference</span>
                <span>Test</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-4">
                {["reference", "test"].map((which) => (
                  <div
                    key={which}
                    className="aspect-square rounded-lg border border-white/10 bg-black p-3"
                  >
                    {/* Illustrative stroke, not a real signature. */}
                    <svg viewBox="0 0 120 120" className="h-full w-full" aria-hidden="true">
                      <path
                        d={
                          which === "reference"
                            ? "M12 78c14-6 18-40 26-38s-4 46 6 44 14-34 22-32 2 26 12 24 16-12 22-18"
                            : "M14 74c13-8 17-38 25-36s-3 44 7 42 13-32 21-30 3 24 13 22 15-10 20-16"
                        }
                        fill="none"
                        stroke="rgba(255,255,255,0.85)"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-slate-500">
                Binarized, deskewed, stroke-normalized - exactly the input the network scores.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------- Accuracy ---------- */}
      <section id="accuracy" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-24 sm:py-32">
        <Reveal>
          <p className="text-xs font-medium uppercase tracking-[0.25em] text-amber-300">Where it stands</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            A decision-support signal, not a verdict
          </h2>
          <p className="mt-5 max-w-2xl text-pretty leading-relaxed text-slate-400">
            Glyph is a research prototype, and it is more useful when it is honest about
            that. Roughly one comparison in five is wrong at the current operating point, in
            both directions, so a result is a prompt to look closer - never the last word.
          </p>
        </Reveal>

        <div className="mt-14 grid gap-6 sm:grid-cols-3">
          {FACTS.map((fact, i) => (
            <Reveal key={fact.label} delay={i * 110}>
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
                <p className="font-display text-3xl text-amber-200">{fact.value}</p>
                <p className="mt-3 text-sm font-semibold text-white">{fact.label}</p>
                <p className="mt-1 text-xs text-slate-500">{fact.note}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={160}>
          <div className="mt-14 flex flex-col items-start justify-between gap-6 rounded-2xl border border-amber-400/20 bg-gradient-to-r from-amber-400/10 to-transparent p-8 sm:flex-row sm:items-center">
            <div>
              <h3 className="text-xl font-semibold text-white">Try it on a pair you know</h3>
              <p className="mt-1 text-sm text-slate-400">
                No account, no sign-up. Two photos and about a minute.
              </p>
            </div>
            <Link
              href="/verify"
              className="group inline-flex shrink-0 items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-ink transition-colors hover:bg-amber-200"
            >
              Open the tester
              <span className="grid h-6 w-6 place-items-center rounded-full bg-ink text-white transition-transform group-hover:translate-x-0.5">
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </Link>
          </div>
        </Reveal>
      </section>

      <footer className="border-t border-white/10 bg-ink-soft">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-10 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>Glyph &middot; Siamese signature verification</p>
          <p className="max-w-lg text-pretty">
            Research prototype - use as a decision-support signal alongside expert review,
            not a sole determinant.
          </p>
        </div>
      </footer>
    </>
  );
}
