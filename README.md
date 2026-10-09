# 德国三平台价格监控：GitHub + Cloudflare Workers

**版本：2026-10-09**。最多100件商品、每件最多三个链接；GitHub Actions 计划每小时运行，GitHub Pages 显示7/30/90天价格曲线；Cloudflare Worker 提供经 GitHub 登录的管理网页和保存接口。

## 架构与安全

- `docs/index.html`：GitHub Pages 的公开价格曲线。
- `worker/index.js` + `docs/admin.html`：Worker 同源提供管理页面（在 **Worker 地址** `/admin.html` 打开，**不要**使用 GitHub Pages 的 `/admin.html`）。
- GitHub OAuth App 仅请求 `read:user`，用于验证 GitHub 登录用户名；真正写仓库的是 Cloudflare Secret 中的细粒度 GitHub Token，仅授予目标仓库 Contents: Read and write。
- 登录会话为 AES-GCM 加密 HttpOnly/Secure/SameSite=Lax Cookie；写入请求验证 CSRF token 和仓库文件 SHA，避免覆盖其他编辑。不要把 Token 写进公开仓库或网页。
- `products.json` 公开可见；不要在商品名称或 URL 中放个人信息。

## A. 上传到 GitHub

1. 新建或使用已有 Public 仓库，建议仓库名 `germany-price-tracker`。
2. 上传 ZIP **解压后的全部文件**（包括隐藏 `.github/workflows/monitor.yml`）。不要把 ZIP 作为单个文件上传。
3. 在仓库 **Settings → Actions → General → Workflow permissions** 允许 `Read and write permissions`（工作流中也声明了 `contents: write`）。
4. **Settings → Pages → Build and deployment**：Deploy from a branch，选 `main` + `/docs`。
5. 在 **Actions → Monitor German shop prices → Run workflow** 手动运行一次。工作流会生成/更新 `data/prices.sqlite3`、`docs/prices.csv`、`docs/status.json`。
6. 仪表盘地址：`https://GITHUB_USERNAME.github.io/germany-price-tracker/`（若仓库名不同则调整路径）。

## B. 创建 GitHub OAuth App

1. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App。
2. Application name：`Germany Price Tracker Admin`。
3. Homepage URL：填你的 Worker 网址，例如 `https://germany-price-tracker-api.YOUR_SUBDOMAIN.workers.dev`。
4. Authorization callback URL：`https://germany-price-tracker-api.YOUR_SUBDOMAIN.workers.dev/auth/callback`。
5. 保存 Client ID，并生成 Client Secret。两者不要混淆。

## C. 创建 GitHub 细粒度 Token

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token。

- Resource owner：你自己的 GitHub 用户。
- Repository access：Only select repositories → 仅选择 `germany-price-tracker`。
- Repository permissions：**Contents: Read and write**，Metadata: Read（自动）。
- 设定有效期，过期后需要更新 Worker Secret。
- 复制 Token，切勿提交到 GitHub 仓库。

## D. 部署 Cloudflare Worker

1. 注册/登录 Cloudflare 免费账户；在电脑安装 Node.js 20+。
2. 打开终端，进入解压文件夹的 `worker` 子目录：

   ```bash
   cd worker
   npx wrangler login
   ```

3. 编辑 `worker/wrangler.toml` 中：

   - `GITHUB_OWNER`：你的 GitHub 用户名
   - `GITHUB_REPO`：仓库名称
   - `ALLOWED_GITHUB_LOGIN`：唯一允许管理的 GitHub 用户名
   - `PAGES_ORIGIN`：`https://你的用户名.github.io`（**不带仓库路径**）
   - `GITHUB_CLIENT_ID`：OAuth App 的 Client ID

4. 编辑 `docs/worker-config.js` 中的公开价格网页地址。
5. 在 `worker` 文件夹执行以下命令，按提示分别粘贴私密值：

   ```bash
   npx wrangler secret put GITHUB_CLIENT_SECRET
   npx wrangler secret put GITHUB_REPO_TOKEN
   npx wrangler secret put SESSION_SECRET
   ```

   `SESSION_SECRET` 使用至少32位随机字符串。首次使用前先运行一次 `npx wrangler deploy` 创建 Worker；若提示 Worker 不存在，先 deploy，再执行以上 secret 命令，最后再次 deploy。

6. 部署：

   ```bash
   npx wrangler deploy
   ```

7. 将 Worker 真实网址填写到 `docs/index.html` 中“管理商品”链接（替换 `https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev/admin.html`），提交到 GitHub。
8. 核对 GitHub OAuth App 的 Homepage/Callback URL 与部署后 Worker 的**实际**网址完全一致。若不一致，返回 OAuth App 设置修改。
9. 打开 `https://你的Worker地址/admin.html`，点击 GitHub 登录，然后添加商品、点击“保存全部修改到 GitHub”。

**注意**：Worker 使用 `docs` 文件夹作为静态资源目录，因此 Cloudflare 管理页面和 GitHub Pages 共享同一份 `docs/admin.html`，但管理操作应始终从 Worker 地址打开。iPhone Safari 对第三方 Cookie 限制较严格，此方案通过 Worker 同源管理避免该问题。

## E. 数据与限制

- GitHub Actions 的 `cron: '17 * * * *'` 是计划任务，不保证准点，Public 仓库长期无活动可能被 GitHub 停用计划任务。
- 最多300条链接，单次运行可能因请求时间、反爬限制或 GitHub Actions 配额而无法全部成功；请观察日志并考虑分批。
- Amazon 只尝试抓取主 Buy Box 且卖家明确为 Amazon 的全新商品；卖家不明、第三方、翻新均不计入历史。MediaMarkt/OTTO 自营验证仍待增强。
- 三个平台可能有反爬虫、地区、登录、优惠券或动态价格，实际抓取并未在真实页面端到端验证。请核对价格后再依赖结果。
- CSV 和 SQLite 均提交到 GitHub。高频、长年数据可能让 Git 仓库膨胀；适合小规模个人使用，300链接长期运行建议后续转到数据库存储。
- 所有价格历史从首次成功采集开始；不能自动补齐过去90天。
- Worker 写入有版本冲突保护。若保存时遇到冲突，刷新后重新编辑。

## 排错

- GitHub Actions 不出现：检查 `.github/workflows/monitor.yml` 是否在默认分支。
- Worker 登录回调失败：检查 OAuth App callback URL、Client ID、Secret、Worker 域名。
- `not_authenticated`：请从 Worker 的 `/admin.html` 登录，不要从 GitHub Pages 的 `/admin.html` 操作。
- `GitHub API 403`：检查细粒度 Token 的仓库范围、Contents 权限、是否过期。
- `GitHub API 409/422`：文件被其他操作修改，刷新页面再保存。
- 价格为空：检查 `docs/status.json` 的错误信息与 Actions 日志。
