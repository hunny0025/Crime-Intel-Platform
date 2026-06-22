import type { Metadata } from "next";
import { fontSans, fontMono } from "./fonts";
import "./globals.css";
import { cn } from "@/lib/utils";
import Providers from "@/components/providers";

export const metadata: Metadata = {
  title: "Investigation Operating System (IOS) | Crime Intelligence Platform",
  description: "Advanced cognitive reasoning, OSINT extraction, behavioral timeline mapping, and prosecutorial compliance verification.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html 
      lang="en" 
      className={cn(
        "dark font-sans antialiased selection:bg-intel-blue-dim selection:text-text-primary",
        fontSans.variable,
        fontMono.variable
      )}
    >
      <body className="min-h-screen bg-background text-foreground font-sans">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}

