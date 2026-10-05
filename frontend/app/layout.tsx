import type { Metadata } from "next";
import "./industry.css";

export const metadata: Metadata = {
  title: "RM Co-pilot",
  description: "Relationship Manager intelligence platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
