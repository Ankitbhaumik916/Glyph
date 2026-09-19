"use client";

import { useState } from "react";

import DemoOverlay from "@/components/DemoOverlay";

/**
 * The bottom-right pill. It used to be a second link to /verify, which made it
 * a duplicate of the header CTA; now it does what its label says and runs a
 * live comparison in an overlay.
 */
export default function HeroActions() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="meet l b r"
        style={{ "--x": 59, "--y": 66 } as React.CSSProperties}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span className="thumb">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="" style={{ objectPosition: "60% 50%" }} src="/media/hero-poster.jpg" />
        </span>
        <b>See a live result</b>
        <span className="knob">
          <svg viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M6.6 3.6 12.6 9l-6 5.4" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open && <DemoOverlay onClose={() => setOpen(false)} />}
    </>
  );
}
