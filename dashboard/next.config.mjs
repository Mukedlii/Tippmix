/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',  // Static export (no server required)
  images: {
    unoptimized: true,  // Required for static export
  },
};

export default nextConfig;
