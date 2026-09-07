#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

class SessionError extends Error {}

function git(args, cwd, allowFailure = false) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch (error) {
    if (allowFailure) return null;
    const detail = error.stderr?.toString().trim() || error.message;
    throw new SessionError(`git ${args.join(" ")} 실패: ${detail}`);
  }
}
function repositoryContext(cwd = process.cwd()) {
  const common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd);
  const commonDir = path.resolve(cwd, common);
  return { commonDir, controllerRoot: path.dirname(commonDir) };
}

const context = repositoryContext();
const configPath = path.join(context.controllerRoot, ".git-session.json");
const registryPath = path.join(context.commonDir, "itda-session-registry.json");
const localWorkerPath = path.join(context.commonDir, "itda-local-worker");

function readJson(file, fallback) {
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function loadConfig() {
  const config = readJson(configPath, null);
  if (!config) throw new SessionError(`설정 파일이 없습니다: ${configPath}`);
  validateConfig(config);
  return config;
}

function validateConfig(config) {
  if (config.worktreeMode !== "per-worker-lazy") {
    throw new SessionError('worktreeMode는 "per-worker-lazy"여야 합니다.');
  }
  if (!Array.isArray(config.allowedWorkers) || config.allowedWorkers.length === 0) {
    throw new SessionError("allowedWorkers가 비어 있습니다.");
  }
  if (!config.workerSlugs || typeof config.workerSlugs !== "object") {
    throw new SessionError("workerSlugs 매핑이 없습니다.");
  }
  const seenSlugs = new Set();
  for (const worker of config.allowedWorkers) {
    const slug = config.workerSlugs[worker];
    if (!slug) throw new SessionError(`작업자 slug가 없습니다: ${worker}`);
    if (seenSlugs.has(slug)) throw new SessionError(`중복 작업자 slug: ${slug}`);
    seenSlugs.add(slug);
  }
}

function loadRegistry() {
  return readJson(registryPath, { sessions: [] });
}

function bindLocalWorker(worker) {
  if (fs.existsSync(localWorkerPath)) {
    const bound = fs.readFileSync(localWorkerPath, "utf8").trim();
    if (bound !== worker) {
      throw new SessionError(`이 clone은 ${bound} 작업자에게 배정돼 있습니다. 요청=${worker}`);
    }
    return;
  }
  fs.writeFileSync(localWorkerPath, `${worker}\n`, "utf8");
}

function saveRegistry(registry) {
  const temp = `${registryPath}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(registry, null, 2)}\n`, "utf8");
  fs.renameSync(temp, registryPath);
}

function normalizeFsPath(value) {
  const resolved = path.resolve(value);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function worktreeRoot(config) {
  return path.resolve(context.controllerRoot, config.worktreeRoot);
}

function normalizeScope(value) {
  const scope = value.replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/$/, "");
  if (!scope || scope === "." || scope.startsWith("../") || path.posix.isAbsolute(scope)) {
    throw new SessionError(`잘못된 claim 경로: ${value}`);
  }
  return scope;
}

function scopesOverlap(left, right) {
  return left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}

function parseArgs(tokens) {
  const values = { path: [] };
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (!token.startsWith("--")) throw new SessionError(`알 수 없는 인자: ${token}`);
    const key = token.slice(2);
    const value = tokens[index + 1];
    if (!value || value.startsWith("--")) throw new SessionError(`${token} 값이 필요합니다.`);
    index += 1;
    if (key === "path") values.path.push(value);
    else values[key] = value;
  }
  return values;
}

function branchExists(branch) {
  return git(["show-ref", "--verify", "--quiet", `refs/heads/${branch}`], context.controllerRoot, true) !== null;
}

function currentBranch(worktree) {
  return git(["branch", "--show-current"], worktree);
}

function isClean(worktree) {
  return git(["status", "--porcelain"], worktree) === "";
}

function ensureOriginMain(config) {
  git(["fetch", "origin", config.defaultBranch], context.controllerRoot);
  if (git(["rev-parse", "--verify", `origin/${config.defaultBranch}`], context.controllerRoot, true) === null) {
    throw new SessionError(`origin/${config.defaultBranch}을 찾을 수 없습니다.`);
  }
}

function ensureWorkerWorktree(config, worker) {
  const slug = config.workerSlugs[worker];
  if (!slug) throw new SessionError(`허용되지 않은 작업자입니다: ${worker}`);
  const worktree = path.join(worktreeRoot(config), slug);
  const workspaceBranch = `worker/${slug}/workspace`;

  if (fs.existsSync(worktree)) {
    const actualCommon = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], worktree, true);
    if (!actualCommon || normalizeFsPath(actualCommon) !== normalizeFsPath(context.commonDir)) {
      throw new SessionError(`다른 저장소 또는 일반 폴더가 worktree 경로를 차지합니다: ${worktree}`);
    }
    return { slug, worktree, workspaceBranch, created: false };
  }

  ensureOriginMain(config);
  fs.mkdirSync(path.dirname(worktree), { recursive: true });
  if (branchExists(workspaceBranch)) {
    git(["worktree", "add", worktree, workspaceBranch], context.controllerRoot);
  } else {
    git([
      "worktree",
      "add",
      worktree,
      "-b",
      workspaceBranch,
      `origin/${config.defaultBranch}`,
    ], context.controllerRoot);
  }
  return { slug, worktree, workspaceBranch, created: true };
}

function activeSessions(registry) {
  return registry.sessions.filter((session) => session.status === "active");
}

function assertNoClaimCollision(registry, worker, scopes) {
  for (const session of activeSessions(registry)) {
    if (session.worker === worker) continue;
    const collisions = scopes.filter((scope) => session.paths.some((other) => scopesOverlap(scope, other)));
    if (collisions.length) {
      throw new SessionError(
        `claim 충돌: ${session.worker}/${session.task}와 ${collisions.join(", ")}가 겹칩니다.`,
      );
    }
  }
}

function findCurrentSession(registry) {
  const root = normalizeFsPath(git(["rev-parse", "--show-toplevel"], process.cwd()));
  const branch = currentBranch(process.cwd());
  return activeSessions(registry).find(
    (session) => normalizeFsPath(session.worktree) === root && session.branch === branch,
  );
}

function commandCheckConfig() {
  const config = loadConfig();
  console.log(`[session] config OK: ${config.allowedWorkers.length} workers, ${config.worktreeMode}`);
}

function commandStatus() {
  const config = loadConfig();
  const registry = loadRegistry();
  for (const worker of config.allowedWorkers) {
    const workerPath = path.join(worktreeRoot(config), config.workerSlugs[worker]);
    if (!fs.existsSync(workerPath)) {
      console.log(`[session] ${worker}: not-created -> ${workerPath}`);
      continue;
    }
    const branch = currentBranch(workerPath);
    const dirty = !isClean(workerPath);
    const active = activeSessions(registry).find(
      (session) => normalizeFsPath(session.worktree) === normalizeFsPath(workerPath),
    );
    console.log(
      `[session] ${worker}: ${workerPath} | ${branch} | ${dirty ? "dirty" : "clean"}` +
        (active ? ` | active=${active.task}` : " | idle"),
    );
  }
}

function commandStart(tokens) {
  const config = loadConfig();
  const args = parseArgs(tokens);
  const worker = args.worker || config.defaultWorker;
  const task = args.task;
  const ai = args.ai;
  if (!config.allowedWorkers.includes(worker)) throw new SessionError(`허용되지 않은 작업자입니다: ${worker}`);
  if (!config.allowedAIs.includes(ai)) throw new SessionError(`허용되지 않은 AI입니다: ${ai}`);
  if (!task || !new RegExp(config.taskPattern, config.taskPatternFlags || "").test(task)) {
    throw new SessionError(`작업명은 ${config.taskPattern} 형식이어야 합니다.`);
  }
  if (args.path.length === 0) throw new SessionError("--path를 하나 이상 지정하십시오.");
  bindLocalWorker(worker);
  const scopes = [...new Set(args.path.map(normalizeScope))];
  const registry = loadRegistry();
  const existing = activeSessions(registry).find((session) => session.worker === worker);
  if (existing) {
    if (existing.task === task) {
      existing.updatedAt = new Date().toISOString();
      saveRegistry(registry);
      console.log(`[session] resumed: ${worker}/${task}\n[session] worktree ${existing.worktree}`);
      return;
    }
    throw new SessionError(`${worker}에게 이미 활성 작업이 있습니다: ${existing.task}`);
  }
  assertNoClaimCollision(registry, worker, scopes);
  const entry = ensureWorkerWorktree(config, worker);
  if (!isClean(entry.worktree)) throw new SessionError(`worktree가 dirty 상태입니다: ${entry.worktree}`);
  const branch = currentBranch(entry.worktree);
  if (branch !== entry.workspaceBranch) {
    throw new SessionError(`대기 브랜치가 아닙니다: ${branch}; 예상=${entry.workspaceBranch}`);
  }
  ensureOriginMain(config);
  const taskBranch = `worker/${entry.slug}/${task}`;
  if (branchExists(taskBranch)) throw new SessionError(`이미 존재하는 작업 브랜치입니다: ${taskBranch}`);
  git(["switch", "-c", taskBranch, `origin/${config.defaultBranch}`], entry.worktree);
  const now = new Date().toISOString();
  registry.sessions.push({
    worker,
    ai,
    task,
    branch: taskBranch,
    worktree: entry.worktree,
    paths: scopes,
    status: "active",
    createdAt: now,
    updatedAt: now,
  });
  saveRegistry(registry);
  console.log(`[session] started: ${worker}/${task}\n[session] worktree ${entry.worktree}\n[session] branch ${taskBranch}`);
}

function commandClaim(tokens) {
  const args = parseArgs(tokens);
  if (args.path.length === 0) throw new SessionError("--path를 하나 이상 지정하십시오.");
  const registry = loadRegistry();
  const session = findCurrentSession(registry);
  if (!session) throw new SessionError("현재 worktree와 브랜치에 활성 세션이 없습니다.");
  const additions = args.path.map(normalizeScope);
  assertNoClaimCollision(registry, session.worker, additions);
  session.paths = [...new Set([...session.paths, ...additions])];
  session.updatedAt = new Date().toISOString();
  saveRegistry(registry);
  console.log(`[session] claimed: ${session.paths.join(", ")}`);
}

function changedFiles(cwd) {
  const commands = [
    ["diff", "--name-only"],
    ["diff", "--cached", "--name-only"],
    ["ls-files", "--others", "--exclude-standard"],
  ];
  const files = new Set();
  for (const args of commands) {
    const output = git(args, cwd);
    for (const line of output.split(/\r?\n/)) if (line) files.add(line.replaceAll("\\", "/"));
  }
  return [...files];
}

function commandGuard(tokens) {
  const args = parseArgs(tokens);
  const registry = loadRegistry();
  const session = findCurrentSession(registry);
  if (!session) throw new SessionError("현재 worktree와 브랜치에 활성 세션이 없습니다.");
  const files = args.file ? [normalizeScope(args.file)] : changedFiles(process.cwd());
  const outside = files.filter(
    (file) => !session.paths.some((scope) => file === scope || file.startsWith(`${scope}/`)),
  );
  if (outside.length) throw new SessionError(`claim 밖 변경: ${outside.join(", ")}`);
  console.log(`[session] guard OK: ${files.length} file(s)`);
}

function commandHeartbeat() {
  const registry = loadRegistry();
  const session = findCurrentSession(registry);
  if (!session) throw new SessionError("현재 worktree와 브랜치에 활성 세션이 없습니다.");
  session.updatedAt = new Date().toISOString();
  saveRegistry(registry);
  console.log(`[session] heartbeat: ${session.worker}/${session.task}`);
}

function commandRelease() {
  const registry = loadRegistry();
  const session = findCurrentSession(registry);
  if (!session) throw new SessionError("현재 worktree와 브랜치에 활성 세션이 없습니다.");
  if (!isClean(process.cwd())) throw new SessionError("dirty worktree는 release할 수 없습니다.");
  session.status = "released";
  session.updatedAt = new Date().toISOString();
  saveRegistry(registry);
  console.log(`[session] released: ${session.worker}/${session.task}; worktree는 유지됩니다.`);
}

function commandCheckGuards() {
  const config = loadConfig();
  const tracked = git(["ls-files", "**/AGENTS.md", "AGENTS.md", "**/CLAUDE.md", "CLAUDE.md"], context.controllerRoot)
    .split(/\r?\n/)
    .filter(Boolean);
  if (tracked.length === 0) throw new SessionError("AGENTS.md/CLAUDE.md 가드가 아직 설치되지 않았습니다.");
  if (config.guardPairs) {
    const files = new Set(tracked);
    for (const file of tracked) {
      const pair = file.endsWith("AGENTS.md")
        ? file.replace(/AGENTS\.md$/, "CLAUDE.md")
        : file.replace(/CLAUDE\.md$/, "AGENTS.md");
      if (!files.has(pair)) throw new SessionError(`가드 쌍이 없습니다: ${file} -> ${pair}`);
    }
  }
  console.log(`[session] guards OK: ${tracked.length} file(s)`);
}

function usage() {
  console.log(`usage: node scripts/git-session-manager.mjs <command>\n\ncommands:\n  check-config\n  status\n  start --ai <ai> --worker <name> --task <slug> --path <path>\n  claim --path <path>\n  guard [--file <path>]\n  heartbeat\n  release\n  check-guards`);
}

try {
  const [command, ...tokens] = process.argv.slice(2);
  if (!command) {
    usage();
    process.exitCode = 2;
  } else {
    const commands = {
      "check-config": () => commandCheckConfig(),
      status: () => commandStatus(),
      start: () => commandStart(tokens),
      claim: () => commandClaim(tokens),
      guard: () => commandGuard(tokens),
      heartbeat: () => commandHeartbeat(),
      release: () => commandRelease(),
      "check-guards": () => commandCheckGuards(),
    };
    if (!commands[command]) throw new SessionError(`알 수 없는 명령: ${command}`);
    commands[command]();
  }
} catch (error) {
  console.error(`[session] ERROR: ${error.message}`);
  process.exitCode = 1;
}
