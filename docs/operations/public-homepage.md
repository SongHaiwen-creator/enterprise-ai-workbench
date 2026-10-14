# 公开产品首页

访问地址：[企业 AI 工作台](https://songhaiwen-creator.github.io/enterprise-ai-workbench/)。

## 目标与范围

将已交付的 Feature 017 产品首页发布为匿名访客可访问的静态展示页，保留中文视觉、插画、六个模块的交互示例、引用展开、场景切换、流程演示和 FAQ。

托管使用当前公开仓库的 GitHub Pages。源码与日常开发保持在既有分支流程中，静态产物使用独立的 `docs/public-homepage-deploy` 发布分支；不向 `main` 直接推送或自动合并。

公开版本将首页的工作台登录入口改为页面演示或 GitHub 项目链接，导航使用普通锚点，避免静态站点触发应用路由预加载。它只导出根页面和静态资源，不包含 `/app`、API 客户端、后端、数据库或环境配置。生产登录和完整平台部署不在本次范围内。

## 构建契约

从仓库根目录执行：

```sh
pnpm --dir frontend install --frozen-lockfile
node scripts/build-public-homepage.mjs
```

构建脚本从当前 `frontend` 复制最小展示源码，在被 Git 忽略的 `.cache/public-homepage/source` 中配置 Next.js 静态导出，复用已经安装的锁定依赖。既有前端配置、路由、登录方式、权限策略和运行依赖不变。

产物目录：`.cache/public-homepage/source/out`。默认路径前缀为 `/enterprise-ai-workbench`，匹配 GitHub 项目站点；自定义根域托管可将环境变量 `PUBLIC_HOMEPAGE_BASE_PATH` 设为空字符串。图片使用静态资源，所有示例交互在浏览器内执行。

脚本遇到首页 CTA 结构变化时会停止，要求人工检查适配，避免悄悄发布失效入口。导出后会检查首页资源存在、不包含受保护路由、无本地后端连接、无环境文件和符号链接。

## 发布与更新

首次发布前核对仓库是否已经配置 Pages，保留已有设置；本次只在确认没有现有站点时创建。

1. 从最新已合并的功能代码构建并检查静态产物。
2. 在独立发布 checkout 中复制 `out` 的全部文件，包括 `.nojekyll`，并用常规提交推送到 `docs/public-homepage-deploy`。此分支只保留公开静态产物。
3. GitHub Pages 选择 **Deploy from a branch**，来源 `docs/public-homepage-deploy`、目录 `/`，采用 HTTPS。
4. 等待 Pages 构建成功，并验证公开首页、图片、样式、脚本及交互。

后续更新使用同一发布分支的当前历史，生成新提交并普通推送，不强制覆盖历史。仅首页导出脚本或展示页面变更时需要重新构建。

无需域名或数据库配置。平台工作空间、认证、RBAC 与业务执行仍由既有 Workbench 所有，不交给静态托管服务。

## 验收与验证

- 匿名浏览器可以通过 HTTPS 打开首页。
- 桌面和移动端布局正确，无横向溢出。
- 六个示例模块可交互，引用与日志详情可以展开，FAQ 可打开。
- 页面导航、插画与所有静态资源路径正确。
- 没有指向本地服务、未部署的工作台或失效内部页面的链接。
- 发布分支不含 `.env`、账号、API Key、数据库凭据、业务数据或受保护应用路由。

实现验证包括独立静态构建、构建产物检查、前端现有回归、lint/build、浏览器检查和 Git diff 自审。此次不执行数据库迁移、数据库重建或真实模型调用。

GitHub Pages 的托管和 API 契约依据[官方发布说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)与[Pages REST API](https://docs.github.com/en/rest/pages/pages)。

## 首次发布与验证记录

2026-10-12 完成首次发布，2026-10-14（Asia/Shanghai）完成线上匿名复核。
基线为已合并的 `main` `8e346406cc59cb2e1dbfe61bc8d5c85d8451e932`；
产物提交为 `527da96ce3ad488cd358a254e753270dfd280d9e`。

| 检查 | 结果 |
|---|---|
| 独立静态构建及 TypeScript | 通过，仅 `/` 与静态错误页 |
| 产物检查 | 35 个静态文件，11 个首页资源引用均存在；没有工作台路由、环境文件或本地后端连接 |
| 本地浏览器 | 1440×1000、390×844；六个模块交互、引用、日志详情、FAQ 和图片通过，无横向溢出 |
| 完整前端回归 | 9 个 Node API 测试、261 个 Vitest 测试通过，无跳过 |
| 既有前端 lint / build | 通过，原 `/` 与 `/app` 仍正常构建 |
| Pages 部署 | [构建与部署记录](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/actions/runs/38221815353)成功；状态 built、public=true、https_enforced=true |
| 线上 HTTP | 无凭据 HTTPS 请求返回 200，包含预期页面标题 |
| 线上浏览器 | 匿名上下文；桌面/移动端与六个示例交互通过，0 页面错误、0 请求失败、0 API 请求 |

截图与验收辅助脚本保留在本工作树被忽略的 `.cache/public-homepage/`，未加入公开产物。
临时预览服务已关闭。未执行数据库操作或 Provider 调用。

初次使用 Sites 连接器时遭遇传输错误及 HTTP 429，无法完成站点注册核验，随后采用
GitHub Pages。没有返回可用的 Sites 项目 ID；后续若切回 Sites，应先查询既有站点状态，
不要重复创建身份不明的站点。
