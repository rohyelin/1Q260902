import type { Metadata } from "next";
import { Fraunces, Source_Sans_3, Noto_Serif_KR } from "next/font/google";
import "./globals.css";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const sans = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

// 본문 읽기용 한글 명조. Fraunces/Source Sans는 latin subset만 담고 있어
// 한글이 시스템 폰트로 폴백되던 것을 대체한다.
// CJK 폰트는 subsets 대신 preload: false 를 쓴다 (용량이 커서 전체 preload 불가).
const serifKr = Noto_Serif_KR({
  weight: ["400", "600"],
  variable: "--font-serif-kr",
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "1Q Lecture Script Matcher",
  description: "한 번의 클릭으로 완성되는 필기",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="ko"
      className={`${display.variable} ${sans.variable} ${serifKr.variable}`}
    >
      <body className="min-h-screen antialiased font-sans">{children}</body>
    </html>
  );
}
