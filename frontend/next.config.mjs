/** @type {import('next').NextConfig} */

// Only NEXT_PUBLIC_* variables reach browser code, so a host env var named
// API_URL is invisible to the app and the client silently falls back to
// localhost. This file is evaluated before Next collects the NEXT_PUBLIC_ set,
// so promoting the value here makes either name work when configuring a
// deployment. (Setting it through the `env` config key does not work: Next's
// own NEXT_PUBLIC_ handling takes precedence and would define it as undefined.)
if (!process.env.NEXT_PUBLIC_API_URL && process.env.API_URL) {
  process.env.NEXT_PUBLIC_API_URL = process.env.API_URL;
}

if (!process.env.NEXT_PUBLIC_API_URL) {
  // Loud at build time beats a deployed page quietly calling localhost.
  console.warn(
    "\n[glyph] Neither NEXT_PUBLIC_API_URL nor API_URL is set. The app will " +
      "fall back to http://localhost:8000, which will not work once deployed.\n",
  );
}

const nextConfig = {
  reactStrictMode: true,
  // A production build writes over whatever is in the output directory. Running
  // one while `next dev` is up replaces the dev server's chunks, and it then
  // fails with "Cannot find module './331.js'" and serves an unstyled page.
  // Build into a separate directory instead:  NEXT_DIST_DIR=.next-build next build
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
