import { spawn } from "node:child_process";
import process from "node:process";
import { fileURLToPath, URL } from "node:url";
import { preview } from "vite";

const server = await preview({
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
});

const cli = fileURLToPath(
  new URL("../node_modules/@playwright/test/cli.js", import.meta.url),
);
const frontendRoot = fileURLToPath(new URL("..", import.meta.url));
const child = spawn(process.execPath, [cli, "test", ...process.argv.slice(2)], {
  cwd: frontendRoot,
  env: { ...process.env, PLAYWRIGHT_EXTERNAL_SERVER: "1" },
  stdio: "inherit",
});

const exitCode = await new Promise((resolve, reject) => {
  child.once("error", reject);
  child.once("exit", (code, signal) => resolve(code ?? (signal ? 1 : 0)));
});

void server.close();
// Vite may retain Windows file-watcher handles after close. The browser tests
// are complete and their exit code is authoritative, so terminate deterministically.
process.exit(Number(exitCode));
