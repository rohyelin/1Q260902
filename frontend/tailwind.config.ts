import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        // 영문·숫자는 Helvetica, 한글은 뒤 폰트로 자동 폴백된다
        // (브라우저는 글리프가 있는 첫 폰트를 쓴다)
        sans: [
          "Helvetica Neue",
          "Helvetica",
          "var(--font-sans)",
          "Apple SD Gothic Neo",
          "Noto Sans KR",
          "sans-serif",
        ],
        // 본문 읽기용: 영문 Helvetica + 한글 명조
        reading: [
          "Helvetica Neue",
          "Helvetica",
          "var(--font-serif-kr)",
          "Nanum Myeongjo",
          "Apple SD Gothic Neo",
          "serif",
        ],
      },
      colors: {
        brand: {
          50: "#f3f5f8",
          100: "#e4e9f0",
          200: "#c8d2de",
          300: "#a8b8cb",
          400: "#8a9eb6",
          500: "#7d92ab",
          600: "#6F86A8",
          700: "#5d7189",
          800: "#4d5f73",
        },
      },
    },
  },
  plugins: [],
};
export default config;
