import type { Metadata } from "next";
import { Inter_Tight, Bricolage_Grotesque, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
});

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Bidex",
  description: "Zero-downtime physical prompting — twin, camera, traces, Port, Bright Data",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body
        className={`${interTight.variable} ${bricolage.variable} ${plexMono.variable} font-sans bg-obsidian-950 text-slate-100 min-h-screen antialiased overflow-hidden selection:bg-hud-cyan selection:text-obsidian-950`}
      >
        {children}
      </body>
    </html>
  );
}
