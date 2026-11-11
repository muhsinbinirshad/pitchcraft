import type { Metadata, Viewport } from "next";
import { Roboto_Flex } from "next/font/google";
import { Shell } from "@/components/Shell";
import { THEME_BOOT } from "@/lib/theme";
import "./globals.css";

const roboto = Roboto_Flex({ subsets: ["latin"], variable: "--font-roboto", display: "swap" });

export const metadata: Metadata = {
  title: "Pitchcraft",
  description: "AI proposal studio that keeps your company's document style exactly",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#f8fafd", colorScheme: "light dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={roboto.variable} data-theme="light" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
