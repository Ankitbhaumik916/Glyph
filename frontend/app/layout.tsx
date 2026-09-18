import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "react-image-crop/dist/ReactCrop.css";
import "./globals.css";

// Variable Inter: the landing design leans on intermediate weights (360, 425,
// 470, 520, 570), which only a variable face can hit.
const inter = Inter({
  subsets: ["latin"],
  display: "block",
  variable: "--font-inter",
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "Glyph — Signature Verification",
  description:
    "Compare a signature against a known-genuine reference, and see exactly what the "
    + "model saw before it decided. Research prototype.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
  themeColor: "#05070b",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: the landing's pre-paint script adds `pre` to
    // <html> before React hydrates, which is a deliberate mismatch.
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
