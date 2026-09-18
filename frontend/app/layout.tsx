import type { Metadata } from "next";
import "react-image-crop/dist/ReactCrop.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Glyph - Signature Verification",
  description:
    "Glyph compares a test signature against a known-genuine reference using a Siamese "
    + "network. Research prototype.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
