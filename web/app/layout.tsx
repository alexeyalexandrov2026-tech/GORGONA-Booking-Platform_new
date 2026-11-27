import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { PwaRegister } from "../components/pwa-register";
import "./globals.css";

const interTight = localFont({
  src: "./fonts/InterTight-Variable.woff2",
  weight: "400 700",
  variable: "--font-display",
  display: "swap",
});

const inter = localFont({
  src: "./fonts/Inter-Variable.woff2",
  weight: "400 700",
  variable: "--font-sans",
  display: "swap",
});

const geistMono = localFont({
  src: "./fonts/GeistMono-Variable.woff2",
  weight: "400 600",
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://www.amarkal-platform.com"),
  title: "AMARKAL Platform — US Business OS",
  description:
    "Run any US business across 39 NAICS industries: operations, clients, staff, finance, and AI automation.",
  manifest: "/manifest.webmanifest",
  openGraph: {
    title: "AMARKAL Platform — US Business OS across 39 industries",
    description:
      "Scheduling, clients, staff, double-entry USD finance, Stripe payouts, and governed AI automation — 0% platform commission.",
    siteName: "AMARKAL Platform",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "AMARKAL Platform — US Business OS",
    description:
      "Run any US business across 39 NAICS industries with 0% commission, direct Stripe payouts, and human-approved AI.",
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "any" },
    ],
  },
  appleWebApp: {
    capable: true,
    title: "AMARKAL Platform",
    statusBarStyle: "default",
  },
  robots: { index: false, follow: false },
};
export const viewport: Viewport = {
  themeColor: "#FBFBFD",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${interTight.variable} ${inter.variable} ${geistMono.variable}`}
    >
      <body>
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
