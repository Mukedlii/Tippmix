import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SZELVÉNYKIRÁLY Dashboard",
  description: "Real-time betting performance analytics",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
