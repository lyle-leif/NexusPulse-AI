import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NexusPulse AI",
  description: "What changed in your store, where, and how sure we are",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies a saved light theme before paint; dark is the default. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var d=document.documentElement;if(localStorage.getItem("np-theme")==="light")d.dataset.theme="light";if(localStorage.getItem("np-intro-seen")==="1")d.dataset.intro="seen"}catch(e){}`,
          }}
        />
      </head>
      <body className="has-bottom-nav min-h-full flex flex-col">{children}</body>
    </html>
  );
}
