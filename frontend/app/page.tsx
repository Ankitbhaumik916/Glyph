import Link from "next/link";

import HeroActions from "@/components/HeroActions";
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
              {/* Light variant: the brand sits on the dark video plate here. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="mark" src="/brand/mark-light.png" alt="" aria-hidden="true" />
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
              <span
                className="tag l c sx"
                style={{ "--x": 66, "--y": 48.7, "--sx": 0.8973 } as React.CSSProperties}
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
                {/* Dark variant: this badge is a near-white disc. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/brand/mark-dark.png" alt="" aria-hidden="true" />
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

            <HeroActions />
          </div>
        </div>
      </div>

      <HeroMotion />
    </div>
  );
}
