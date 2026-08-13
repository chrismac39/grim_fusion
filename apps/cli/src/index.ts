import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { spawnSync, type SpawnSyncReturns } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

import {
  applyPaletteOverrides,
  colorizeItem,
  defaultPalette,
  loadPaletteOverridesFromFile,
} from "@grim-fusion/color-engine";
import type { BuildProfile, ItemRecord } from "@grim-fusion/core-model";
import { parseBuildProfileText, scoreSemanticStatIds } from "@grim-fusion/scoring-engine";
import { composeTag } from "@grim-fusion/tag-composer";

type CliArgs = {
  command:
    | "example"
    | "run"
    | "run-with-gleaner"
    | "session"
    | "apply-plan";
  profilePath?: string;
  profileDir?: string;
  palettePath?: string;
  itemsPath?: string;
  outPath?: string;
  python?: string;
  grimDawnPath?: string;
  planName?: string;
  forceApply?: boolean;
};

type PythonRuntime = {
  command: string;
  baseArgs: string[];
  display: string;
};

type BuildPlan = {
  name: string;
  grimDawnPath: string;
  profilePath?: string;
  profileDir?: string;
  paletteMode: "default" | "custom";
  palettePath?: string;
  itemsPath: string;
  gleanerRoot: string;
  python: string;
  updatedAt: string;
  generation?: {
    generatedAt: string;
    profilePathResolved: string;
    profileHash: string;
    itemsPathResolved: string;
    itemsHash: string;
    paletteMode: "default" | "custom";
    palettePathResolved?: string;
    paletteHash?: string;
    fusionTextHash: string;
    steamBuildId: string;
    patchVersions: string;
  };
};

type FusionOutput = {
  profile: {
    name: string;
    masteries: [string, string];
    profilePath: string;
  };
  palette: {
    palettePath: string | null;
    rarity: {
      common: string;
      magical: string;
      rare: string;
      epic?: string;
      legendary?: string;
    };
  };
  items: Array<{
    id: string;
    name: string;
    grade: string;
    weightedMatch: number;
    effectiveScore: number;
    matchedStatIds: string[];
    displayTag: string;
  }>;
};

const CLI_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(CLI_DIR, "..", "..", "..");
const PLANS_DIR = path.join(REPO_ROOT, "artifacts", "plans");
const VENDORED_GLEANER_ROOT = path.join(REPO_ROOT, "vendor", "grim_gleaner");
const GLEANER_PROFILES_ROOT = path.join(
  VENDORED_GLEANER_ROOT,
  "artifacts",
  "profiles"
);
const FUSION_PLAN_KEY = "grim_fusion_plan";
const DEFAULT_GD_PATH =
  process.env.GRIM_DAWN_INSTALL_PATH ??
  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Grim Dawn";

function resolveUserPath(inputPath: string): string {
  const trimmed = inputPath.trim();
  const unquoted =
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
      ? trimmed.slice(1, -1)
      : trimmed;

  if (path.isAbsolute(unquoted)) {
    return unquoted;
  }

  const fromCwd = path.resolve(process.cwd(), unquoted);
  try {
    statSync(fromCwd);
    return fromCwd;
  } catch {
    return path.resolve(REPO_ROOT, unquoted);
  }
}

function parseArgs(argv: string[]): CliArgs {
  if (argv.length === 0 || argv.includes("--example")) {
    return { command: "example" };
  }

  const [command, ...rest] = argv;
  if (
    command !== "run" &&
    command !== "run-with-gleaner" &&
    command !== "session" &&
    command !== "apply-plan"
  ) {
    throw new Error(
      `Unknown command '${command}'. Use 'run', 'run-with-gleaner', 'session', or 'apply-plan'.`
    );
  }

  const out: CliArgs = {
    command,
  };

  for (let i = 0; i < rest.length; i += 1) {
    const token = rest[i];
    if (token === "--force-apply") {
      out.forceApply = true;
      continue;
    }

    const value = rest[i + 1];
    if (!token.startsWith("--")) {
      continue;
    }
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${token}`);
    }

    switch (token) {
      case "--profile":
        out.profilePath = value;
        break;
      case "--profile-dir":
        out.profileDir = value;
        break;
      case "--palette":
        out.palettePath = value;
        break;
      case "--items":
        out.itemsPath = value;
        break;
      case "--out":
        out.outPath = value;
        break;
      case "--python":
        out.python = value;
        break;
      case "--grim-dawn-path":
        out.grimDawnPath = value;
        break;
      case "--plan-name":
        out.planName = value;
        break;
      default:
        throw new Error(`Unknown option '${token}'`);
    }

    i += 1;
  }

  return out;
}

function runCommand(
  command: string,
  args: string[],
  cwd?: string
): SpawnSyncReturns<string> {
  return spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: "pipe",
  });
}

function commandOk(result: SpawnSyncReturns<string>): boolean {
  return (result.status ?? 1) === 0;
}

function detectPythonRuntime(pythonOverride?: string): PythonRuntime {
  if (pythonOverride) {
    const looksLikePath = /[\\/]/.test(pythonOverride) || /\.exe$/i.test(pythonOverride);
    const command = looksLikePath
      ? resolveUserPath(pythonOverride)
      : pythonOverride.trim();
    return {
      command,
      baseArgs: [],
      display: command,
    };
  }

  const py313 = runCommand("py", ["-3.13", "--version"]);
  if (commandOk(py313)) {
    return {
      command: "py",
      baseArgs: ["-3.13"],
      display: "py -3.13",
    };
  }

  const python313 = runCommand("python3.13", ["--version"]);
  if (commandOk(python313)) {
    return {
      command: "python3.13",
      baseArgs: [],
      display: "python3.13",
    };
  }

  const python = runCommand("python", ["--version"]);
  if (commandOk(python) && /Python\s+3\.13\./.test(`${python.stdout}${python.stderr}`)) {
    return {
      command: "python",
      baseArgs: [],
      display: "python",
    };
  }

  throw new Error(
    [
      "Could not find Python 3.13 runtime.",
      "Run npm install from grim_fusion root to bootstrap dependencies,",
      "or pass --python <path-to-python-3.13>.",
    ].join("\n")
  );
}

function hashText(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function hashFile(filePath: string): string {
  return hashText(readFileSync(filePath, "utf8"));
}

function planNamesEqual(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

function findPlanByName(plans: BuildPlan[], planName: string): BuildPlan | undefined {
  return plans.find((plan) => planNamesEqual(plan.name, planName));
}

function formatStalenessWarnings(plan: BuildPlan): string[] {
  if (!plan.generation) {
    return [
      "Plan has no generation metadata yet.",
      "Regenerate this plan to capture db hash and patch/build tracking.",
    ];
  }

  const warnings: string[] = [];
  const currentSteamBuildId = inferSteamBuildId(plan.grimDawnPath);
  const currentPatchVersions = inferPatchVersions(
    path.join(plan.grimDawnPath, "settings", "text_en")
  );

  if (currentSteamBuildId !== plan.generation.steamBuildId) {
    warnings.push(
      `Steam build changed: plan=${plan.generation.steamBuildId}, current=${currentSteamBuildId}`
    );
  }
  if (currentPatchVersions !== plan.generation.patchVersions) {
    warnings.push(
      `Patch markers changed: plan=${plan.generation.patchVersions}, current=${currentPatchVersions}`
    );
  }

  if (!existsSync(plan.generation.profilePathResolved)) {
    warnings.push(`Profile source missing: ${plan.generation.profilePathResolved}`);
  } else {
    const currentProfileHash = hashFile(plan.generation.profilePathResolved);
    if (currentProfileHash !== plan.generation.profileHash) {
      warnings.push("Profile JSON changed since this plan was generated.");
    }
  }

  if (!existsSync(plan.generation.itemsPathResolved)) {
    warnings.push(`Items source missing: ${plan.generation.itemsPathResolved}`);
  } else {
    const currentItemsHash = hashFile(plan.generation.itemsPathResolved);
    if (currentItemsHash !== plan.generation.itemsHash) {
      warnings.push("Items data changed since this plan was generated.");
    }
  }

  if (
    plan.generation.paletteMode === "custom" &&
    plan.generation.palettePathResolved
  ) {
    if (!existsSync(plan.generation.palettePathResolved)) {
      warnings.push(
        `Palette source missing: ${plan.generation.palettePathResolved}`
      );
    } else if (plan.generation.paletteHash) {
      const currentPaletteHash = hashFile(plan.generation.palettePathResolved);
      if (currentPaletteHash !== plan.generation.paletteHash) {
        warnings.push("Palette file changed since this plan was generated.");
      }
    }
  }

  return warnings;
}

function ensureToolsAndDependencies(
  gleanerRoot: string,
  runtime: PythonRuntime
): void {
  if (!existsSync(gleanerRoot)) {
    throw new Error(
      [
        `Vendored grim_gleaner path not found: ${gleanerRoot}`,
        "Ensure vendor/grim_gleaner exists in this repository.",
      ].join("\n")
    );
  }

  const pysideOk = runCommand(runtime.command, [
    ...runtime.baseArgs,
    "-c",
    "import PySide6",
  ]);
  if (!commandOk(pysideOk)) {
    throw new Error(
      [
        "PySide6 is not installed for the selected Python runtime.",
        "Run npm install (or npm run setup:deps) from grim_fusion root.",
        `Runtime checked: ${runtime.display}`,
      ].join("\n")
    );
  }

  const gleanerImportOk = runCommand(
    runtime.command,
    [...runtime.baseArgs, "-c", "import gd_affix_relevance"],
    gleanerRoot
  );
  if (!commandOk(gleanerImportOk)) {
    throw new Error(
      [
        "Vendored grim_gleaner import failed.",
        "Run npm install (or npm run setup:deps) from grim_fusion root.",
        `Runtime checked: ${runtime.display}`,
      ].join("\n")
    );
  }
}

function resolveProfilePath(args: CliArgs): string {
  if (args.profilePath) {
    return resolveUserPath(args.profilePath);
  }

  if (!args.profileDir) {
    throw new Error("Provide --profile <file> or --profile-dir <dir>");
  }

  const dir = resolveUserPath(args.profileDir);
  const candidates = readdirSync(dir)
    .filter((name) => name.toLowerCase().endsWith(".json"))
    .map((name) => {
      const fullPath = path.join(dir, name);
      return {
        fullPath,
        mtimeMs: statSync(fullPath).mtimeMs,
      };
    })
    .sort((a, b) => b.mtimeMs - a.mtimeMs);

  if (candidates.length === 0) {
    throw new Error(`No JSON profiles found in ${dir}`);
  }

  return candidates[0].fullPath;
}

function buildFusionOutput(args: CliArgs): FusionOutput {
  if (!args.itemsPath) {
    throw new Error("Missing required option --items <file>");
  }

  const profilePath = resolveProfilePath(args);
  const itemsPath = resolveUserPath(args.itemsPath);
  const profileText = readFileSync(profilePath, "utf8");
  const profile = parseBuildProfileText(profileText);
  const items = JSON.parse(readFileSync(itemsPath, "utf8")) as ItemRecord[];

  const palette = args.palettePath
    ? applyPaletteOverrides(defaultPalette, loadPaletteOverridesFromFile(resolveUserPath(args.palettePath)))
    : defaultPalette;

  const output: FusionOutput = {
    profile: {
      name: profile.name,
      masteries: profile.masteries,
      profilePath,
    },
    palette: {
      palettePath: args.palettePath ? resolveUserPath(args.palettePath) : null,
      rarity: palette.rarity,
    },
    items: items.map((item) => {
      const relevance = scoreSemanticStatIds(
        item.stats.map((stat) => stat.key),
        profile
      );
      const composed = composeTag(colorizeItem(item, palette), {
        item,
        score: relevance.weightedMatch,
        grade: relevance.grade,
      });
      return {
        id: item.id,
        name: item.name,
        grade: relevance.grade,
        weightedMatch: relevance.weightedMatch,
        effectiveScore: Number(relevance.effectiveScore.toFixed(4)),
        matchedStatIds: relevance.matchedStatIds,
        displayTag: composed.displayText,
      };
    }),
  };

  return output;
}

function runFusion(args: CliArgs): void {
  const output = buildFusionOutput(args);
  const json = `${JSON.stringify(output, null, 2)}\n`;
  if (args.outPath) {
    const outPath = resolveUserPath(args.outPath);
    writeFileSync(outPath, json, "utf8");
    console.log(`Wrote fusion output to ${outPath}`);
    return;
  }

  process.stdout.write(json);
}

function launchGleanerUi(args: CliArgs): void {
  const gleanerRoot = VENDORED_GLEANER_ROOT;
  const runtime = detectPythonRuntime(args.python);
  const configuredGrimDawnPath = resolveUserPath(
    args.grimDawnPath || DEFAULT_GD_PATH
  );
  const env = {
    ...process.env,
    GRIM_DAWN_INSTALL_PATH:
      process.env.GRIM_DAWN_INSTALL_PATH || configuredGrimDawnPath,
    PYTHONPATH: [path.join(gleanerRoot, "src"), process.env.PYTHONPATH ?? ""]
      .filter(Boolean)
      .join(process.platform === "win32" ? ";" : ":"),
  };

  console.log(`Launching grim_gleaner UI from ${gleanerRoot} using ${runtime.display}...`);
  const result = spawnSync(
    runtime.command,
    [...runtime.baseArgs, "-m", "gd_affix_relevance.ui.app"],
    {
    cwd: gleanerRoot,
    env,
    stdio: "inherit",
    }
  );

  if (result.error) {
    throw result.error;
  }
  if ((result.status ?? 1) !== 0) {
    throw new Error(`grim_gleaner UI exited with code ${result.status}`);
  }
}

function runWithGleaner(args: CliArgs): void {
  const grimDawnPath = resolveUserPath(args.grimDawnPath || DEFAULT_GD_PATH);
  const fusionOutput = buildFusionOutput(args);
  const deployed = deployToGrimDawn(
    fusionOutput,
    grimDawnPath,
    args.forceApply ?? false
  );

  console.log(
    deployed.deployed
      ? `Applied gdse-style fusion colorization to ${deployed.targetFile}`
      : `Fusion colorization unchanged. Existing text kept at ${deployed.targetFile}`
  );

  if (args.outPath) {
    const outPath = resolveUserPath(args.outPath);
    writeFileSync(outPath, `${JSON.stringify(fusionOutput, null, 2)}\n`, "utf8");
    console.log(`Wrote fusion output to ${outPath}`);
  }

  launchGleanerUi({
    ...args,
    grimDawnPath,
  });
}

function ensureTextEnFolder(grimDawnPath: string): string {
  const settingsDir = path.join(grimDawnPath, "settings");
  const textEn = path.join(settingsDir, "text_en");
  mkdirSync(textEn, { recursive: true });
  return textEn;
}

function localMinuteStamp(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

function inferSteamBuildId(grimDawnPath: string): string {
  const steamAppsDir = path.resolve(grimDawnPath, "..", "..");
  const manifest = path.join(steamAppsDir, "appmanifest_219990.acf");
  if (!existsSync(manifest)) {
    return "unknown";
  }
  const text = readFileSync(manifest, "utf8");
  const match = text.match(/"buildid"\s+"(\d+)"/);
  return match?.[1] ?? "unknown";
}

function inferPatchVersions(textEnDir: string): string {
  if (!existsSync(textEnDir)) {
    return "unknown";
  }
  const versions = new Set<string>();
  for (const file of readdirSync(textEnDir)) {
    if (!file.toLowerCase().endsWith(".txt")) {
      continue;
    }
    const full = path.join(textEnDir, file);
    const text = readFileSync(full, "utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (/^#(Patch|Hotfix|Update)\b/i.test(line)) {
        versions.add(line.replace(/^#\s*/u, ""));
      }
    }
  }
  if (versions.size === 0) {
    return "unknown";
  }
  return [...versions].sort().join("|");
}

function renderFusionTagText(output: FusionOutput): string {
  const lines = [
    "#Generated by grim_fusion",
    `#Profile: ${output.profile.name}`,
    `#Masteries: ${output.profile.masteries.join(",")}`,
    "",
    ...output.items.map((item) => `tagFusion${item.id}=${item.displayTag}`),
  ];
  return `${lines.join("\n")}\n`;
}

function appendHashHistory(
  grimDawnPath: string,
  hash: string,
  patchVersions: string,
  steamBuildId: string
): void {
  const historyFile = path.join(grimDawnPath, "settings", "gdse-db-hash.txt");
  const prior = existsSync(historyFile) ? readFileSync(historyFile, "utf8") : "";
  const line = `${localMinuteStamp()} hash=${hash} steam_build_id=${steamBuildId} patch_versions=${patchVersions}`;
  writeFileSync(historyFile, `${prior}${line}\n`, "utf8");
}

function latestRecordedHash(grimDawnPath: string): string | null {
  const historyFile = path.join(grimDawnPath, "settings", "gdse-db-hash.txt");
  if (!existsSync(historyFile)) {
    return null;
  }
  const lines = readFileSync(historyFile, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return null;
  }
  const last = lines[lines.length - 1];
  const match = last.match(/\bhash=([a-f0-9]{64})\b/i);
  return match?.[1] ?? null;
}

function deployToGrimDawn(
  output: FusionOutput,
  grimDawnPath: string,
  forceApply = false
): {
  deployed: boolean;
  targetFile: string;
  hash: string;
  steamBuildId: string;
  patchVersions: string;
} {
  if (!existsSync(grimDawnPath)) {
    throw new Error(`Grim Dawn path does not exist: ${grimDawnPath}`);
  }

  const textEn = ensureTextEnFolder(grimDawnPath);
  const targetFile = path.join(textEn, "tags_fusion_generated.txt");
  const tagText = renderFusionTagText(output);
  const hash = hashText(tagText);
  const lastHash = latestRecordedHash(grimDawnPath);
  const steamBuildId = inferSteamBuildId(grimDawnPath);
  const patchVersions = inferPatchVersions(textEn);

  if (!forceApply && lastHash === hash) {
    console.log("No data change since last applied hash. Skipping file write.");
    return {
      deployed: false,
      targetFile,
      hash,
      steamBuildId,
      patchVersions,
    };
  }

  if (existsSync(targetFile)) {
    const backupDir = path.join(textEn, "backups");
    mkdirSync(backupDir, { recursive: true });
    const backupFile = path.join(
      backupDir,
      `tags_fusion_generated.${localMinuteStamp().replace(/[ :]/g, "-")}.bak.txt`
    );
    writeFileSync(backupFile, readFileSync(targetFile, "utf8"), "utf8");
  }

  writeFileSync(targetFile, tagText, "utf8");
  appendHashHistory(
    grimDawnPath,
    hash,
    patchVersions,
    steamBuildId
  );
  return { deployed: true, targetFile, hash, steamBuildId, patchVersions };
}

function buildGenerationMetadata(
  plan: BuildPlan,
  deployed: { hash: string; steamBuildId: string; patchVersions: string }
): NonNullable<BuildPlan["generation"]> {
  const profilePathResolved = resolveProfilePath({
    command: "run",
    profilePath: plan.profilePath,
    profileDir: plan.profileDir,
  });
  const itemsPathResolved = resolveUserPath(plan.itemsPath);
  const palettePathResolved =
    plan.paletteMode === "custom" && plan.palettePath
      ? resolveUserPath(plan.palettePath)
      : undefined;

  return {
    generatedAt: new Date().toISOString(),
    profilePathResolved,
    profileHash: hashFile(profilePathResolved),
    itemsPathResolved,
    itemsHash: hashFile(itemsPathResolved),
    paletteMode: plan.paletteMode,
    palettePathResolved,
    paletteHash: palettePathResolved ? hashFile(palettePathResolved) : undefined,
    fusionTextHash: deployed.hash,
    steamBuildId: deployed.steamBuildId,
    patchVersions: deployed.patchVersions,
  };
}

function slugify(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "plan";
}

function collectJsonFiles(root: string): string[] {
  if (!existsSync(root)) {
    return [];
  }

  const out: string[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) {
      continue;
    }
    for (const entry of readdirSync(current)) {
      const full = path.join(current, entry);
      const stats = statSync(full);
      if (stats.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (stats.isFile() && entry.toLowerCase().endsWith(".json")) {
        out.push(full);
      }
    }
  }

  return out;
}

function resolvePlanProfilePath(plan: BuildPlan): string {
  return resolveProfilePath({
    command: "run",
    profilePath: plan.profilePath,
    profileDir: plan.profileDir,
  });
}

function parseEmbeddedPlan(
  profilePath: string,
  payload: Record<string, unknown>
): BuildPlan | undefined {
  const embedded = payload[FUSION_PLAN_KEY];
  if (!embedded || typeof embedded !== "object" || Array.isArray(embedded)) {
    return undefined;
  }

  const plan = embedded as Partial<BuildPlan>;
  const profileName =
    typeof payload.name === "string" && payload.name.trim().length > 0
      ? payload.name
      : path.basename(profilePath, path.extname(profilePath));

  const paletteMode = plan.paletteMode === "custom" ? "custom" : "default";
  const itemsPath =
    typeof plan.itemsPath === "string" && plan.itemsPath.trim().length > 0
      ? plan.itemsPath
      : path.join(REPO_ROOT, "fixtures", "shared", "items.json");

  return {
    name:
      typeof plan.name === "string" && plan.name.trim().length > 0
        ? plan.name
        : profileName,
    grimDawnPath:
      typeof plan.grimDawnPath === "string" && plan.grimDawnPath.trim().length > 0
        ? plan.grimDawnPath
        : DEFAULT_GD_PATH,
    profilePath,
    profileDir:
      typeof plan.profileDir === "string" && plan.profileDir.trim().length > 0
        ? plan.profileDir
        : undefined,
    paletteMode,
    palettePath:
      paletteMode === "custom" &&
      typeof plan.palettePath === "string" &&
      plan.palettePath.trim().length > 0
        ? plan.palettePath
        : undefined,
    itemsPath,
    gleanerRoot:
      typeof plan.gleanerRoot === "string" && plan.gleanerRoot.trim().length > 0
        ? plan.gleanerRoot
        : VENDORED_GLEANER_ROOT,
    python:
      typeof plan.python === "string" && plan.python.trim().length > 0
        ? plan.python
        : "py -3.13",
    updatedAt:
      typeof plan.updatedAt === "string" && plan.updatedAt.trim().length > 0
        ? plan.updatedAt
        : new Date(0).toISOString(),
    generation:
      plan.generation && typeof plan.generation === "object"
        ? (plan.generation as BuildPlan["generation"])
        : undefined,
  };
}

function readEmbeddedPlan(profilePath: string): BuildPlan | undefined {
  try {
    const payload = JSON.parse(readFileSync(profilePath, "utf8")) as Record<
      string,
      unknown
    >;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return undefined;
    }
    return parseEmbeddedPlan(profilePath, payload);
  } catch {
    return undefined;
  }
}

function saveEmbeddedPlan(plan: BuildPlan): string {
  const profilePath = resolvePlanProfilePath(plan);
  const payload = JSON.parse(readFileSync(profilePath, "utf8")) as Record<
    string,
    unknown
  >;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Profile file is not a JSON object: ${profilePath}`);
  }

  const normalized: BuildPlan = {
    ...plan,
    profilePath,
    profileDir: undefined,
  };

  payload[FUSION_PLAN_KEY] = {
    name: normalized.name,
    grimDawnPath: normalized.grimDawnPath,
    paletteMode: normalized.paletteMode,
    palettePath: normalized.palettePath,
    itemsPath: normalized.itemsPath,
    gleanerRoot: normalized.gleanerRoot,
    python: normalized.python,
    updatedAt: normalized.updatedAt,
    generation: normalized.generation,
  };

  writeFileSync(profilePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return profilePath;
}

function readPlan(file: string): BuildPlan {
  const parsed = JSON.parse(readFileSync(file, "utf8")) as BuildPlan;
  return parsed;
}

function loadPlans(): BuildPlan[] {
  const embeddedPlans = collectJsonFiles(GLEANER_PROFILES_ROOT)
    .map((file) => readEmbeddedPlan(file))
    .filter((plan): plan is BuildPlan => Boolean(plan));

  if (embeddedPlans.length > 0) {
    return embeddedPlans.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  if (!existsSync(PLANS_DIR)) {
    return [];
  }
  return readdirSync(PLANS_DIR)
    .filter((f) => f.toLowerCase().endsWith(".json"))
    .map((f) => readPlan(path.join(PLANS_DIR, f)))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function savePlan(plan: BuildPlan): string {
  try {
    return saveEmbeddedPlan(plan);
  } catch (error) {
    mkdirSync(PLANS_DIR, { recursive: true });
    const file = path.join(PLANS_DIR, `${slugify(plan.name)}.json`);
    writeFileSync(file, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
    if (error instanceof Error) {
      console.warn(
        `Fell back to artifacts plan storage for '${plan.name}': ${error.message}`
      );
    }
    return file;
  }
}

async function choosePlanInteractively(
  rl: ReturnType<typeof createInterface>,
  plans: BuildPlan[]
): Promise<BuildPlan> {
  if (plans.length === 0) {
    throw new Error("No saved plans found.");
  }

  console.log("Available plans:");
  plans.forEach((p, idx) => {
    console.log(`  ${idx + 1}. ${p.name} (${p.updatedAt})`);
  });

  const selectionRaw = await ask(rl, `Choose plan [${plans.length}]: `);
  const index = Number.parseInt(selectionRaw || String(plans.length), 10) - 1;
  return plans[index] ?? plans[plans.length - 1];
}

function applyPlan(
  plan: BuildPlan,
  forceApply = false
): { deployed: boolean; targetFile: string; hash: string } {
  const profilePathResolved = resolvePlanProfilePath(plan);
  const planForApply: BuildPlan = {
    ...plan,
    profilePath: profilePathResolved,
    profileDir: undefined,
  };

  const warnings = formatStalenessWarnings(plan);
  if (warnings.length > 0) {
    console.log("Regeneration recommended before apply:");
    warnings.forEach((warning) => console.log(`  - ${warning}`));
  }

  const fusionArgs: CliArgs = {
    command: "run",
    profilePath: planForApply.profilePath,
    profileDir: undefined,
    palettePath:
      planForApply.paletteMode === "custom" ? planForApply.palettePath : undefined,
    itemsPath: planForApply.itemsPath,
    grimDawnPath: planForApply.grimDawnPath,
    forceApply,
  };

  const fusionOutput = buildFusionOutput(fusionArgs);
  const deployed = deployToGrimDawn(
    fusionOutput,
    planForApply.grimDawnPath,
    forceApply
  );

  const refreshedPlan: BuildPlan = {
    ...planForApply,
    updatedAt: new Date().toISOString(),
    generation: buildGenerationMetadata(planForApply, deployed),
  };
  savePlan(refreshedPlan);

  return {
    deployed: deployed.deployed,
    targetFile: deployed.targetFile,
    hash: deployed.hash,
  };
}

async function runApplyPlan(args: CliArgs): Promise<void> {
  const plans = loadPlans();
  if (plans.length === 0) {
    throw new Error(
      "No saved plans found. Run 'session' first to create at least one plan."
    );
  }

  const plan = args.planName
    ? findPlanByName(plans, args.planName)
    : undefined;

  let selected: BuildPlan;
  if (plan) {
    selected = plan;
  } else if (args.planName) {
    throw new Error(`No plan named '${args.planName}' found.`);
  } else {
    const rl = createInterface({ input, output });
    try {
      selected = await choosePlanInteractively(rl, plans);
    } finally {
      rl.close();
    }
  }

  const result = applyPlan(selected, args.forceApply ?? false);
  console.log(
    result.deployed
      ? `Applied fusion text to ${result.targetFile}`
      : `Plan unchanged. Existing text kept at ${result.targetFile}`
  );
}

async function ask(rl: ReturnType<typeof createInterface>, question: string): Promise<string> {
  return (await rl.question(question)).trim();
}

async function askYesNo(
  rl: ReturnType<typeof createInterface>,
  question: string,
  defaultYes = true
): Promise<boolean> {
  const suffix = defaultYes ? " [Y/n]: " : " [y/N]: ";
  const answer = (await ask(rl, `${question}${suffix}`)).toLowerCase();
  if (!answer) {
    return defaultYes;
  }
  return answer === "y" || answer === "yes";
}

async function askExistingDirectory(
  rl: ReturnType<typeof createInterface>,
  question: string,
  defaultPath: string
): Promise<string> {
  while (true) {
    const answer = await ask(rl, question);
    const normalizedAnswer = answer.trim().toLowerCase();
    const candidate =
      answer.length === 0 || normalizedAnswer === "y" || normalizedAnswer === "yes"
        ? resolveUserPath(defaultPath)
        : resolveUserPath(answer);
    try {
      if (statSync(candidate).isDirectory()) {
        return candidate;
      }
    } catch {
      // fall through to retry message
    }
    console.log(`Directory not found: ${candidate}`);
  }
}

async function askExistingJsonFile(
  rl: ReturnType<typeof createInterface>,
  question: string,
  defaultPath: string
): Promise<string> {
  while (true) {
    const answer = await ask(rl, question);
    const normalizedAnswer = answer.trim().toLowerCase();
    const candidate =
      answer.length === 0 || normalizedAnswer === "y" || normalizedAnswer === "yes"
        ? resolveUserPath(defaultPath)
        : resolveUserPath(answer);
    try {
      if (statSync(candidate).isFile() && candidate.toLowerCase().endsWith(".json")) {
        return candidate;
      }
      if (statSync(candidate).isFile()) {
        console.log(`File is not JSON: ${candidate}`);
        continue;
      }
    } catch {
      // fall through to retry message
    }
    console.log(`JSON file not found: ${candidate}`);
  }
}

async function runGuidedSession(args: CliArgs): Promise<void> {
  const rl = createInterface({ input, output });
  try {
    console.log("grim_fusion guided session");

    const configuredGrimDawnPath = resolveUserPath(
      args.grimDawnPath || DEFAULT_GD_PATH
    );
    let grimDawnPath = configuredGrimDawnPath;
    if (existsSync(configuredGrimDawnPath)) {
      console.log(`1) Grim Dawn install path: ${configuredGrimDawnPath}`);
    } else {
      const grimDawnPathAnswer = await ask(
        rl,
        `1) Grim Dawn install path not found at ${configuredGrimDawnPath}. Enter path: `
      );
      grimDawnPath = resolveUserPath(grimDawnPathAnswer);
    }

    const gleanerRoot = VENDORED_GLEANER_ROOT;
    const runtime = detectPythonRuntime(args.python);

    console.log("Checking tools and dependencies...");
    ensureToolsAndDependencies(gleanerRoot, runtime);
    console.log("Tools look good.");

    console.log("2) Profile source for pre-Gleaner gdse-style colorization");
    console.log("   Press Enter at path prompts to use defaults.");
    const profileModePath = await ask(
      rl,
      "Profile JSON path (leave blank to auto-pick newest in a directory): "
    );
    const profileDirDefault = path.join(gleanerRoot, "artifacts", "profiles", "examples");
    const profileDir =
      profileModePath.length === 0
        ? await askExistingDirectory(
            rl,
            `Profile directory [${profileDirDefault}]: `,
            profileDirDefault
          )
        : undefined;
    const profilePath =
      profileModePath.length > 0 ? resolveUserPath(profileModePath) : undefined;

    console.log("3) Palette selection (gdse style)");
    const useDefaultPalette = await askYesNo(rl, "Use default gdse palette?", true);
    const palettePath = useDefaultPalette
      ? undefined
      : resolveUserPath(await ask(rl, "Custom palette file path: "));

    const itemsDefault = args.itemsPath ?? path.join("fixtures", "shared", "items.json");
    const itemsPath = await askExistingJsonFile(
      rl,
      `Items JSON path [${itemsDefault}]: `,
      itemsDefault
    );

    console.log(
      "4) Running gdse-style fusion generation/apply before launching grim_gleaner UI."
    );
    runWithGleaner({
      ...args,
      command: "run-with-gleaner",
      grimDawnPath,
      python: args.python,
      profilePath,
      profileDir,
      palettePath,
      itemsPath,
      forceApply: args.forceApply,
    });

    const suggestedPlanName =
      (args.planName ??
        (await ask(rl, "5) Name this build plan (example: Cold Wereraven): "))) ||
      "My Build Plan";

    const plan: BuildPlan = {
      name: suggestedPlanName,
      grimDawnPath,
      profilePath: resolveProfilePath({
        command: "run",
        profilePath,
        profileDir,
      }),
      profileDir: undefined,
      paletteMode: useDefaultPalette ? "default" : "custom",
      palettePath,
      itemsPath,
      gleanerRoot,
      python: runtime.display,
      updatedAt: new Date().toISOString(),
    };
    const planFile = savePlan(plan);
    console.log(`Saved plan: ${planFile}`);

    const plans = loadPlans();
    console.log("6) Select the plan to play for this session:");
    const selected = await choosePlanInteractively(rl, plans);
    const deploy = applyPlan(selected, args.forceApply ?? true);

    console.log(
      deploy.deployed
        ? `Applied fusion text to ${deploy.targetFile}`
        : `Plan unchanged. Existing text kept at ${deploy.targetFile}`
    );
    console.log("Launch Grim Dawn and play using this profile plan.");
  } finally {
    rl.close();
  }
}

function runExample(): void {
  const profile: BuildProfile = {
    name: "example-fire-arcanist",
    weights: {
      fire_damage_percent: 4,
      cast_speed_percent: 3,
      offensive_ability: 2,
      vitality_damage_percent: 0,
    },
    masteries: ["playerclass01", "playerclass02"],
    skillWeights: {
      "records/skills/playerclass01/flamestrike1.dbr": 3,
    },
    excludedConversionSources: {},
    resistanceCapEnabled: false,
    resistanceCapWeights: {},
  };

  const item: ItemRecord = {
    id: "sample-item-001",
    name: "Blazeseer Signet",
    rarity: "legendary",
    stats: [
      { key: "fire_damage_percent", value: 52 },
      { key: "cast_speed_percent", value: 8 },
      { key: "offensive_ability", value: 74 },
    ],
  };

  const colorized = colorizeItem(item, defaultPalette);
  const scored = scoreSemanticStatIds(
    item.stats.map((stat) => stat.key),
    profile
  );
  const composed = composeTag(colorized, {
    item,
    score: scored.weightedMatch,
    grade: scored.grade,
  });

  console.log("Profile:", profile.name);
  console.log("Item:", item.name);
  console.log("Score:", scored.weightedMatch, "Grade:", scored.grade);
  console.log("Tag output:", composed.displayText);
}

function printUsage(): void {
  console.log("grim-fusion usage:");
  console.log("  npm run dev -- --example");
  console.log("  npm run dev -- session [--grim-dawn-path <path>] [--items <items.json>] [--plan-name <name>] [--force-apply]");
  console.log("  npm run dev -- apply-plan [--plan-name <name>] [--force-apply]");
  console.log("  npm run dev -- run --profile <profile.json> --items <items.json> [--palette <gdse-palette.txt>] [--out <output.json>]");
  console.log("  npm run dev -- run --profile-dir <dir> --items <items.json> [--palette <gdse-palette.txt>] [--out <output.json>]");
  console.log("  npm run dev -- run-with-gleaner --profile <profile.json> --items <items.json> [--palette <gdse-palette.txt>] [--grim-dawn-path <path>] [--out <output.json>] [--force-apply]");
  console.log("  npm run dev -- run-with-gleaner --profile-dir <dir-with-profile-json> --items <items.json> [--palette <gdse-palette.txt>] [--grim-dawn-path <path>] [--out <output.json>] [--force-apply]");
}

async function main(): Promise<void> {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.command === "example") {
      runExample();
      return;
    }
    if (args.command === "session") {
      await runGuidedSession(args);
      return;
    }
    if (args.command === "apply-plan") {
      await runApplyPlan(args);
      return;
    }
    if (args.command === "run-with-gleaner") {
      runWithGleaner(args);
      return;
    }
    runFusion(args);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    printUsage();
    process.exitCode = 1;
  }
}

void main();
