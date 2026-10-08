import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const backend = "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5177,
    strictPort: true,
    proxy: {
      "/api": {
        target: backend,
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, req) => {
            // Local development only: normalize an origin from this Vite host.
            // Leave any other origin untouched so backend CORS still rejects it.
            if (req.headers.origin === `http://${req.headers.host}`) {
              proxyReq.setHeader("Origin", backend);
            }
          });
        },
      },
    },
  },
  build: { sourcemap: true },
});
