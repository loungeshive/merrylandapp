import type { Metadata, Viewport } from "next";
import "./globals.css";
import PwaInstallPrompt from "./PwaInstallPrompt";

export const metadata: Metadata = {
  title: "Merryland | Food Menu & Ordering",
  description: "Browse the Merryland menu, build your order, and check out.",
  applicationName: "Merryland Kitchen & Bar",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Merryland",
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32", type: "image/x-icon" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/merryland-icon.svg", type: "image/svg+xml" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#8e2639",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {children}
        <PwaInstallPrompt />
      </body>
    </html>
  );
}
