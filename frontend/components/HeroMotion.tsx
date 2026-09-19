"use client";

import { useEffect } from "react";

const EXPO = "cubic-bezier(.16,1,.3,1)";
const SOFT = "cubic-bezier(.22,.7,.25,1)";
const GLASS = "cubic-bezier(.2,.75,.28,1)";

/**
 * Entrance timeline, burger menu and video preference sync for the landing.
 *
 * The background plate is the stage and never animates; only the foreground
 * performs. Pre-states live behind `html.pre`, which an inline script adds
 * before first paint, and this timeline removes once everything has landed -
 * so the resting frame is the authored CSS, untouched. With no JS or with
 * reduced motion the class is never added and the page renders finished.
 */
export default function HeroMotion() {
  useEffect(() => {
    const doc = document.documentElement;
    // Client-side navigation back to "/" skips the inline script; arm it here
    // so the entrance still plays, unless the visitor asked for less motion.
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!doc.classList.contains("pre") && !reduced && "animate" in Element.prototype) {
      doc.classList.add("pre");
    }

    const running: Animation[] = [];
    const s = window.matchMedia("(max-width: 640px)").matches ? 0.86 : 1;

    const play = (
      el: Element | null | undefined,
      frames: Keyframe[],
      dur: number,
      delay: number,
      easing: string,
    ) => {
      if (!el) return;
      running.push(
        el.animate(frames, { duration: dur * s, delay: delay * s, easing, fill: "both" }),
      );
    };
    const q = (sel: string) => document.querySelector(sel);
    const qa = (sel: string) => Array.from(document.querySelectorAll(sel));

    const rise = (el: Element | null | undefined, delay: number, dur: number) =>
      play(
        el,
        [
          { clipPath: "inset(100% 0 -14% 0)", translate: "0 .16em" },
          { clipPath: "inset(-18% 0 -14% 0)", translate: "0 0" },
        ],
        dur,
        delay,
        EXPO,
      );
    const lift = (el: Element | null | undefined, delay: number, dist = ".7em", dur = 560) =>
      play(el, [{ opacity: 0, translate: `0 ${dist}` }, { opacity: 1, translate: "0 0" }], dur, delay, SOFT);
    const settle = (
      el: Element | null | undefined,
      delay: number,
      dur = 760,
      from = 0.985,
      dist = "1.1em",
    ) =>
      play(
        el,
        [
          { opacity: 0, scale: String(from), translate: `0 ${dist}` },
          { opacity: 1, scale: "1", translate: "0 0" },
        ],
        dur,
        delay,
        GLASS,
      );

    if (doc.classList.contains("pre")) {
      const heads = qa("h1.hero .sx");
      const nums = qa(".num");
      const lbls = qa(".lbl");

      lift(q(".brand"), 60, ".55em", 600);
      settle(q(".nav"), 150, 700, 0.99, ".5em");
      settle(q(".cta"), 200, 700, 0.985, ".5em");
      settle(q(".burger"), 150, 700, 0.9, ".4em");
      lift(q(".eyebrow"), 300, ".8em", 520);
      rise(heads[0], 380, 980);
      rise(heads[1], 470, 980);
      lift(q(".tag"), 720, ".7em", 560);
      settle(q(".panel"), 800, 880, 0.982, "1.4em");
      play(q(".shield"), [{ scale: ".86" }, { scale: "1" }], 700, 1020, EXPO);
      play(q(".dot"), [{ scale: "0" }, { scale: "1" }], 520, 1080, EXPO);
      play(q(".track i"), [{ scale: "0 1" }, { scale: "1 1" }], 820, 1120, EXPO);
      rise(nums[0], 920, 860);
      rise(nums[1], 990, 860);
      lift(lbls[0], 1030, ".6em", 520);
      lift(lbls[1], 1075, ".6em", 520);
      play(q(".slash"), [{ scale: "1 0" }, { scale: "1 1" }], 700, 1010, EXPO);
      settle(q(".meet"), 1140, 820, 0.985, "1.2em");

      void Promise.all(running.map((a) => a.finished.catch(() => {}))).then(() => {
        doc.classList.remove("pre");
        running.forEach((a) => a.cancel());
        running.length = 0;
      });
    }

    // --- burger ---
    const burger = document.querySelector<HTMLButtonElement>(".burger");
    const menu = document.querySelector<HTMLElement>("#site-menu");
    const setOpen = (open: boolean) => {
      if (!burger || !menu) return;
      burger.setAttribute("aria-expanded", String(open));
      if (open) menu.setAttribute("data-open", "");
      else menu.removeAttribute("data-open");
    };
    const onBurger = (e: MouseEvent) => {
      e.stopPropagation();
      setOpen(burger?.getAttribute("aria-expanded") !== "true");
    };
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (burger?.contains(t) || menu?.contains(t)) return;
      setOpen(false);
    };
    const onMenuClick = (e: MouseEvent) => {
      if ((e.target as HTMLElement).closest("a")) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        burger?.focus();
      }
    };
    const wide = window.matchMedia("(min-aspect-ratio: 1/1)");
    const onWide = (e: MediaQueryListEvent) => {
      if (e.matches) setOpen(false);
    };
    burger?.addEventListener("click", onBurger);
    menu?.addEventListener("click", onMenuClick);
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    wide.addEventListener("change", onWide);

    // --- video: hold on frame 1 for reduced motion, and follow the preference ---
    const video = document.querySelector<HTMLVideoElement>("video.bg");
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => {
      if (!video) return;
      if (rm.matches) {
        video.pause();
        video.currentTime = 0;
      } else {
        void video.play().catch(() => {});
      }
    };
    const onVisible = () => {
      if (!document.hidden) sync();
    };
    rm.addEventListener("change", sync);
    document.addEventListener("visibilitychange", onVisible);
    video?.addEventListener("canplay", sync);
    sync();

    // The landing is a fixed, non-scrolling frame; other routes scroll normally.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      burger?.removeEventListener("click", onBurger);
      menu?.removeEventListener("click", onMenuClick);
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
      wide.removeEventListener("change", onWide);
      rm.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", onVisible);
      video?.removeEventListener("canplay", sync);
      document.body.style.overflow = prevOverflow;
      doc.classList.remove("pre");
      running.forEach((a) => a.cancel());
    };
  }, []);

  return null;
}
