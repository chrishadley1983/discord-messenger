import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Kiosk: never show the dev-mode build indicator (challenge finding —
  // the "N" badge overlapped the Home nav pill in dev-mode screenshots)
  devIndicators: false,
};

export default nextConfig;
