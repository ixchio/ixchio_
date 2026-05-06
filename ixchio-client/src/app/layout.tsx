import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ixchio — Deep Research",
  description: "Autonomous research assistant. Multi-agent deep research with adaptive search and reflection.",
  openGraph: {
    title: "ixchio — Deep Research",
    description: "Autonomous multi-agent research assistant.",
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
      <body className={`${inter.variable} antialiased min-h-screen bg-black text-neutral-200 font-sans`}>
        {children}
      </body>
    </html>
  );
}
