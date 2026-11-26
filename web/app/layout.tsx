import type { Metadata, Viewport } from "next";
import { PwaRegister } from "../components/pwa-register";
import "./globals.css";
export const metadata: Metadata = {
  title: "AMARKAL Platform — US Business OS",
  description:
    "Run any US business across 39 NAICS industries: operations, clients, staff, finance, and AI automation.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "AMARKAL Platform",
    statusBarStyle: "default",
  },
  robots: { index: false, follow: false },
};
export const viewport: Viewport = {
  themeColor: "#1f1a17",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
