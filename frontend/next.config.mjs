/** @type {import('next').NextConfig} */
// `standalone` output is only for the Docker image (docker/frontend.Dockerfile sets NEXT_OUTPUT=standalone);
// locally `next start` does not work with it.
const nextConfig = process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" } : {};
export default nextConfig;
