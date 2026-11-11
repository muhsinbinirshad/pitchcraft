/** Static export in production (served by the Python app); API proxy in dev. */
const isDev = process.env.NODE_ENV === "development";
const backend = process.env.PITCHCRAFT_API || "http://127.0.0.1:8600";

const nextConfig = isDev
  ? { async rewrites() { return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }]; } }
  : { output: "export", trailingSlash: true, images: { unoptimized: true } };

export default nextConfig;
