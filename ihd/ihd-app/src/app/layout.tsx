import type { Metadata } from "next";
import { Fraunces, Figtree } from "next/font/google";
import ScreenOverlay from "@/components/ScreenOverlay";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["200", "500"],
});

const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Family Dashboard",
  description: "In-Home Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${fraunces.variable} ${figtree.variable} antialiased`}>
        {children}
        <ScreenOverlay />
      </body>
    </html>
  );
}
