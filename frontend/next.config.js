/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // 프로덕션(Vercel): NEXT_PUBLIC_API_URL로 백엔드 직접 호출 → rewrite 불필요
    if (process.env.NEXT_PUBLIC_API_URL) return [];
    const backend =
      process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
