import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ixchio — Deep Research Engine",
  description: "Multi-agent deep research engine with STORM perspectives, adaptive search, and reflection loops. No signup required.",
  icons: { icon: "/logo.svg" },
  openGraph: {
    title: "ixchio — Deep Research Engine",
    description: "Free multi-agent research engine. Get comprehensive, source-backed reports on any topic.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased min-h-screen bg-white text-black font-sans`}>
        {children}
      </body>
    </html>
  );
}
