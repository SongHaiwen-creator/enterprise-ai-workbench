import { spawnSync } from "node:child_process";
import { cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, symlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontend = path.join(root, "frontend");
const site = path.join(root, ".cache", "public-homepage", "source");
const basePath = process.env.PUBLIC_HOMEPAGE_BASE_PATH ?? "/enterprise-ai-workbench";
const repositoryUrl = "https://github.com/SongHaiwen-creator/enterprise-ai-workbench";
if (basePath !== "" && !/^\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(basePath)) {
  throw new Error("PUBLIC_HOMEPAGE_BASE_PATH must be empty or a path without a trailing slash.");
}
if (!existsSync(path.join(frontend, "node_modules", "next", "dist", "bin", "next"))) {
  throw new Error("Install the locked frontend dependencies before exporting the homepage.");
}

// Assemble only the public page and its presentation components. Protected
// routes, API helpers, environment files and backend code are never copied.
for (const relative of ["app/layout.tsx", "app/globals.css", "app/components/ui-icon.tsx", "app/components/landing-preview.tsx", "public/images/hero-knowledge.png", "tsconfig.json", "pnpm-lock.yaml"]) {
  const destination = path.join(site, relative);
  mkdirSync(path.dirname(destination), { recursive: true });
  cpSync(path.join(frontend, relative), destination);
}
const replacements = [
  ['import Link from "next/link";', 'import type { AnchorHTMLAttributes } from "react";\nfunction Link(props: AnchorHTMLAttributes<HTMLAnchorElement>) { return <a {...props} />; }'],
  ['href="/"', `href="${basePath}/"`],
  ['href="/app">进入平台 <Icon', 'href="#features">查看演示 <Icon'],
  ['href="/app">开始使用 <Icon', 'href="#features">体验交互示例 <Icon'],
  ['href="/app">进入平台体验 <Icon', `href="${repositoryUrl}">查看项目实现 <Icon`],
  ['href="/app">进入企业 AI 工作台 <Icon', `href="${repositoryUrl}">查看项目与运行指南 <Icon`],
  ['src="/images/hero-knowledge.png"', `src="${basePath}/images/hero-knowledge.png"`],
  ['真实操作需要登录平台，并遵循现有权限和审批流程。', '实际工作台遵循角色权限与人工审批流程，可通过项目中的运行指南了解使用方式。'],
];
let homepage = readFileSync(path.join(frontend, "app", "page.tsx"), "utf8");
for (const [before, after] of replacements) {
  if (!homepage.includes(before)) throw new Error(`Homepage source changed; review the public adaptation: ${before}`);
  homepage = homepage.replaceAll(before, after);
}
if (homepage.includes('href="/app"')) throw new Error("The public homepage must not link to the protected app.");
writeFileSync(path.join(site, "app", "page.tsx"), homepage);
const manifest = JSON.parse(readFileSync(path.join(frontend, "package.json"), "utf8"));
manifest.name = "enterprise-ai-workbench-public-homepage";
manifest.scripts = { build: "next build --webpack" };
writeFileSync(path.join(site, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(path.join(site, "next.config.mjs"), `export default ${JSON.stringify({ output: "export", basePath, images: { unoptimized: true } })};\n`);
const modules = path.join(site, "node_modules");
if (!existsSync(modules)) symlinkSync(path.join(frontend, "node_modules"), modules, process.platform === "win32" ? "junction" : "dir");
const build = spawnSync(process.execPath, [path.join(frontend, "node_modules", "next", "dist", "bin", "next"), "build", "--webpack"], {
  cwd: site,
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  stdio: "inherit",
});
if (build.error) throw build.error;
if (build.status !== 0) process.exit(build.status ?? 1);

const output = path.join(site, "out");
writeFileSync(path.join(output, ".nojekyll"), "");
const html = readFileSync(path.join(output, "index.html"), "utf8");
if (existsSync(path.join(output, "app")) || existsSync(path.join(output, "app.html"))) throw new Error("Protected app route found in public output.");
const localAssets = [...html.matchAll(/(?:src|href)="([^"#]+)"/g)].map((match) => match[1]).filter((value) => value.startsWith(`${basePath}/`) && /\.(?:js|css|png)$/.test(value));
for (const asset of localAssets) {
  if (!existsSync(path.join(output, asset.slice(basePath.length)))) throw new Error(`Missing public asset: ${asset}`);
}
let files = 0;
function inspect(directory) {
  for (const name of readdirSync(directory)) {
    const filename = path.join(directory, name);
    const stat = lstatSync(filename);
    if (stat.isDirectory()) inspect(filename);
    else {
      if (!stat.isFile()) throw new Error("Static output contains a link or special file.");
      if (name.startsWith(".env")) throw new Error("Environment file found in public output.");
      if (/\.(?:html|js|txt)$/.test(name) && /http:\/\/localhost:8000|\/api\/auth\/login/.test(readFileSync(filename, "utf8"))) throw new Error("Backend connection found in public output.");
      files += 1;
    }
  }
}
inspect(output);
console.log(JSON.stringify({ output, base_path: basePath, files, verified_local_assets: localAssets.length, protected_routes: 0 }));
