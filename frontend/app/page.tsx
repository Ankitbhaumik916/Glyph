import Link from "next/link";

import HeroMotion from "@/components/HeroMotion";
import "./landing.css";

/** Adds the entrance pre-state before first paint; the timeline removes it. */
const PRE_SCRIPT = `(function(){var d=document.documentElement;
if(!('animate' in Element.prototype))return;
if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;
d.classList.add('pre');
setTimeout(function(){d.classList.remove('pre')},4000);})();`;

const Chevron = () => (
  <svg viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <path d="m6.6 3.6 6 5.4-6 5.4" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function Landing() {
  return (
    <div className="glyph-page">
      <script dangerouslySetInnerHTML={{ __html: PRE_SCRIPT }} />
      <div className="card">
        <video
          className="bg"
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          disablePictureInPicture
          aria-hidden="true"
          poster="/media/hero-poster.jpg"
          src="/media/hero.mp4"
        />
        <div className="tint" />

        <div className="stack">
          {/* ---------------- header ---------------- */}
          <div className="row">
            <Link className="brand l t" style={{ "--x": 68, "--y": 47 } as React.CSSProperties} href="/">
              {/* Signature stroke, drawn in one gesture - the product's own mark. */}
              <svg className="mark" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <circle cx="20" cy="20" r="18.4" stroke="#f2f6fc" strokeWidth="1.1" opacity=".55" />
                <path
                  d="M7.5 26.5c4.2-1.2 6.6-12.4 8.6-11.6 2 .8-1.4 15.4 1.6 15.1 3-.3 4.2-12.6 6.6-11.8 2.3.8.2 9.3 2.8 9 1.9-.2 3.6-2.4 5.4-4.6"
                  stroke="#f8b55c"
                  strokeWidth="1.9"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <b className="sx" style={{ "--sx": 0.894 } as React.CSSProperties}>
                Glyph
              </b>
            </Link>

            <button
              className="burger"
              type="button"
              aria-label="Open menu"
              aria-expanded="false"
              aria-controls="site-menu"
            >
              <i />
              <i />
            </button>

            <div className="menu" id="site-menu">
              <nav className="nav">
                <svg className="n-home" viewBox="0 0 20 21" fill="none" aria-hidden="true">
                  <path
                    d="M2 8.4 10 2l8 6.4V18a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z"
                    stroke="#f2f6fc"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                </svg>
                <Link className="n-explore" href="/">
                  Overview
                </Link>
                <hr className="n-div" />
                <svg className="n-grid" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <rect x="1" y="1" width="7.4" height="7.4" rx="1.7" stroke="#f2f6fc" strokeWidth="1.7" />
                  <rect x="11.6" y="1" width="7.4" height="7.4" rx="1.7" stroke="#f2f6fc" strokeWidth="1.7" />
                  <rect x="1" y="11.6" width="7.4" height="7.4" rx="1.7" stroke="#f2f6fc" strokeWidth="1.7" />
                  <rect x="11.6" y="11.6" width="7.4" height="7.4" rx="1.7" stroke="#f2f6fc" strokeWidth="1.7" />
                </svg>
                <Link className="n-product" href="/verify">
                  Tester
                </Link>
              </nav>

              <Link className="cta l t r" style={{ "--x": 58, "--y": 30 } as React.CSSProperties} href="/verify">
                <span>Test a signature</span>
                <span className="knob">
                  <Chevron />
                </span>
              </Link>
            </div>
          </div>

          {/* ---------------- hero ---------------- */}
          <div className="hero-blk">
            <p
              className="eyebrow l c sx"
              style={{ "--x": 65.7, "--y": -209.2, "--sx": 0.9293 } as React.CSSProperties}
            >
              Siamese signature verification
            </p>

            <h1 className="hero l c" style={{ "--x": 62.6, "--y": -167.3 } as React.CSSProperties}>
              <span className="sx" style={{ "--sx": 0.9431 } as React.CSSProperties}>
                Every hand leaves
              </span>
              <br />
              <span className="sx" style={{ "--sx": 0.9792 } as React.CSSProperties}>
                its own light
              </span>
            </h1>

            <div className="tagrow">
              <span className="play l c" style={{ "--x": 66, "--y": 34 } as React.CSSProperties}>
                <svg viewBox="0 0 13 14" aria-hidden="true">
                  <path d="M1.4 1.3 11.6 7 1.4 12.7z" fill="#0b1526" />
                </svg>
              </span>
              <span
                className="tag l c sx"
                style={{ "--x": 131, "--y": 48.7, "--sx": 0.8973 } as React.CSSProperties}
              >
                See exactly what the model saw.
              </span>
            </div>

            <aside className="panel l c r" style={{ "--x": 58, "--y": -165 } as React.CSSProperties}>
              <span className="p-title sx" style={{ "--sx": 0.8707 } as React.CSSProperties}>
                Threshold
              </span>
              <span className="dot" />
              <span className="shield">
                <svg viewBox="0 0 34 34" fill="none" aria-hidden="true">
                  <path
                    d="M4 23c3.6-1 5.6-10.6 7.4-9.9 1.7.7-1.2 13.1 1.4 12.9 2.5-.3 3.6-10.8 5.6-10.1 2 .7.2 7.9 2.4 7.7 1.6-.2 3-2 4.6-3.9"
                    stroke="#101c33"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <p className="p-sub sx" style={{ "--sx": 0.8899 } as React.CSSProperties}>
                Genuine at or
                <br />
                below 0.39 on
                <br />
                the distance scale
              </p>
              <div className="scale">
                <span>0</span>
                <span>0.5</span>
                <span>1.0</span>
                <span>2.0</span>
              </div>
              <div className="track">
                <i />
              </div>
            </aside>
          </div>

          {/* ---------------- stats ---------------- */}
          <div className="row">
            <div className="stats">
              <div className="stat">
                <span className="num l b sx" style={{ "--x": 64, "--y": 60.4, "--sx": 1 } as React.CSSProperties}>
                  0.39
                </span>
                <span
                  className="lbl l b sx"
                  style={{ "--x": 295, "--y": 73.2, "--sx": 0.9634 } as React.CSSProperties}
                >
                  Decision
                  <br />
                  threshold in
                  <br />
                  distance units
                </span>
              </div>
              <span className="slash l b" style={{ "--x": 418, "--y": 76 } as React.CSSProperties} />
              <div className="stat">
                <span
                  className="num l b sx"
                  style={{ "--x": 480, "--y": 60.4, "--sx": 0.9858 } as React.CSSProperties}
                >
                  20%
                </span>
                <span
                  className="lbl l b sx"
                  style={{ "--x": 716, "--y": 96.7, "--sx": 0.9209 } as React.CSSProperties}
                >
                  Comparisons
                  <br />
                  it gets wrong
                </span>
              </div>
            </div>

            <Link className="meet l b r" style={{ "--x": 59, "--y": 66 } as React.CSSProperties} href="/verify">
              <span className="thumb">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt="" style={{ objectPosition: "60% 50%" }} src="/media/hero-poster.jpg" />
              </span>
              <b>See a live result</b>
              <span className="knob">
                <Chevron />
              </span>
            </Link>
          </div>
        </div>
      </div>

      <HeroMotion />
    </div>
  );
}
