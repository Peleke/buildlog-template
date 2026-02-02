#!/usr/bin/env node

/**
 * buildlog npm wrapper
 *
 * Thin shim that finds and invokes the Python buildlog CLI.
 * Resolution order:
 *   1. `buildlog` on PATH (pip install / pipx / system)
 *   2. `uvx buildlog` (auto-downloads, no install needed)
 *   3. `python3 -m buildlog` / `python -m buildlog`
 *
 * All arguments and stdio are passed through transparently.
 */

import { spawn, execFileSync } from "node:child_process";

const args = process.argv.slice(2);

/**
 * Check if a command exists on PATH.
 */
function commandExists(cmd) {
  try {
    execFileSync(process.platform === "win32" ? "where" : "which", [cmd], {
      stdio: "ignore",
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Spawn a child process with full stdio passthrough.
 * Returns a promise that resolves with the exit code.
 */
function run(cmd, cmdArgs) {
  return new Promise((resolve) => {
    const child = spawn(cmd, cmdArgs, {
      stdio: "inherit",
      env: process.env,
    });

    child.on("error", () => resolve(null));
    child.on("close", (code) => resolve(code));
  });
}

async function main() {
  // Strategy 1: buildlog on PATH
  if (commandExists("buildlog")) {
    const code = await run("buildlog", args);
    if (code !== null) process.exit(code);
  }

  // Strategy 2: uvx buildlog (auto-downloads from PyPI)
  if (commandExists("uvx")) {
    const code = await run("uvx", ["buildlog", ...args]);
    if (code !== null) process.exit(code);
  }

  // Strategy 3: python -m buildlog
  for (const python of ["python3", "python"]) {
    if (commandExists(python)) {
      const code = await run(python, ["-m", "buildlog", ...args]);
      if (code !== null) process.exit(code);
    }
  }

  // Nothing worked
  console.error(`buildlog: Python CLI not found.

Install buildlog (pick one):
  pip install buildlog
  uv tool install buildlog
  pipx install buildlog

Or install Python: https://www.python.org/downloads/

The npm package is a thin wrapper around the Python CLI.
Python is required to run buildlog.`);
  process.exit(127);
}

main();
