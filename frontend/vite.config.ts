import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "OTD_");
  const host = env.OTD_HOST || "127.0.0.1";
  const address = host === "::1" ? "[::1]" : host;
  return {
    server: {
      host: "127.0.0.1", port: 5173, strictPort: true,
      proxy: { "/api": `http://${address}:${env.OTD_PORT || "8000"}` },
    },
  };
});
