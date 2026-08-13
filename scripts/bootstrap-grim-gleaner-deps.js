#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");
const VENDORED_GLEANER_ROOT = path.join(REPO_ROOT, "vendor", "grim_gleaner");

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: "pipe",
    ...opts,
  });
}

function ok(result) {
  return (result.status ?? 1) === 0;
}

function log(message) {
  process.stdout.write(`[grim-fusion bootstrap] ${message}\n`);
}

function warn(message) {
  process.stderr.write(`[grim-fusion bootstrap] ${message}\n`);
}

function ensurePython313() {
  const pyCheck = run("py", ["-3.13", "--version"]);
  if (ok(pyCheck)) {
    log(`Using ${pyCheck.stdout.trim() || pyCheck.stderr.trim()}`);
    return "py";
  }

  if (process.platform !== "win32") {
    throw new Error(
      "Python 3.13 not found. Install Python 3.13 and rerun npm install."
    );
  }

  const wingetCheck = run("winget", ["--version"]);
  if (!ok(wingetCheck)) {
    throw new Error(
      "Python 3.13 not found and winget is unavailable. Install Python 3.13 manually: https://www.python.org/downloads/"
    );
  }

  log("Python 3.13 not found. Installing via winget...");
  const install = spawnSync(
    "winget",
    [
      "install",
      "--id",
      "Python.Python.3.13",
      "-e",
      "--accept-package-agreements",
      "--accept-source-agreements",
    ],
    { stdio: "inherit" }
  );
  if (!ok(install)) {
    throw new Error("winget failed to install Python 3.13.");
  }

  const verify = run("py", ["-3.13", "--version"]);
  if (!ok(verify)) {
    throw new Error("Python 3.13 installation did not verify.");
  }

  log(`Installed ${verify.stdout.trim() || verify.stderr.trim()}`);
  return "py";
}

function resolveGleanerRoot() {
  if (existsSync(VENDORED_GLEANER_ROOT)) {
    return VENDORED_GLEANER_ROOT;
  }

  throw new Error(
    "Could not find vendor/grim_gleaner. Ensure the vendored grim_gleaner folder exists in this repository."
  );
}

function pythonImportOk(pyLauncher, gleanerRoot) {
  const check = run(
    pyLauncher,
    [
      "-3.13",
      "-c",
      "import PySide6, gd_affix_relevance; print('ok')",
    ],
    { cwd: gleanerRoot }
  );
  return ok(check);
}

function installGleanerDeps(pyLauncher, gleanerRoot) {
  log(`Installing grim_gleaner deps from ${gleanerRoot}...`);

  const pipUpgrade = spawnSync(
    pyLauncher,
    ["-3.13", "-m", "pip", "install", "--upgrade", "pip"],
    { cwd: gleanerRoot, stdio: "inherit" }
  );
  if (!ok(pipUpgrade)) {
    throw new Error("Failed to upgrade pip for Python 3.13.");
  }

  const pipInstall = spawnSync(
    pyLauncher,
    ["-3.13", "-m", "pip", "install", "-e", gleanerRoot],
    { cwd: gleanerRoot, stdio: "inherit" }
  );
  if (!ok(pipInstall)) {
    throw new Error("Failed to install grim_gleaner and PySide6 dependencies.");
  }
}

function main() {
  try {
    log("Checking grim_gleaner Python dependencies...");
    const pyLauncher = ensurePython313();
    const gleanerRoot = resolveGleanerRoot();

    if (pythonImportOk(pyLauncher, gleanerRoot)) {
      log("Dependencies already satisfied (PySide6 + gd_affix_relevance).");
      return;
    }

    installGleanerDeps(pyLauncher, gleanerRoot);

    if (!pythonImportOk(pyLauncher, gleanerRoot)) {
      throw new Error("Dependency verification failed after installation.");
    }

    log("grim_gleaner dependencies are ready.");
  } catch (error) {
    warn(String(error && error.message ? error.message : error));
    process.exitCode = 1;
  }
}

main();
