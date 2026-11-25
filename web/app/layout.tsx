import type { Metadata, Viewport } from "next";
import { PwaRegister } from "../components/pwa-register";
import "./globals.css";
export const metadata: Metadata = {
  title: "GORGONA — Book & Manage Your Business",
  description: "Choose your service, specialist and time.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "GORGONA",
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
