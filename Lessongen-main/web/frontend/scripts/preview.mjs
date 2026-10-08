import { preview } from "vite";
import process from "node:process";

const server = await preview({
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
});

let closing = false;
async function shutdown() {
  if (closing) return;
  closing = true;
  // Playwright has already stopped sending requests at this point. Do not wait
  // indefinitely for framework handles that can linger on Windows.
  void server.close();
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
