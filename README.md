# 德国三平台价格追踪 V2

完整独立版本：GitHub Actions 每小时抓取，GitHub Pages 显示数据，Cloudflare Worker 管理商品。**抓取失败时不伪造价格**。支持最多 100 件商品、MediaMarkt / Amazon.de / OTTO.de、7/30/90 天曲线、目标价格标记、错误诊断。

## 一、部署 GitHub 仓库（最重要）

1. 先把现有 `zacklu0831/germany-price-tracker` 仓库下载 ZIP 备份，保留旧数据。**本版本的文件会覆盖同名文件。**
2. 将本压缩包解压，**上传压缩包里面的文件和文件夹**到 GitHub 仓库 `main` 分支的根目录，不要再套一层 `germany-price-tracker-v2` 文件夹。必须包含 `.github/workflows/price-tracker.yml`、`src/tracker.py`、`docs/index.html`、`docs/admin.html`、`worker/worker.js`、`products.json` 等。Windows 资源管理器可能隐藏 `.github`，注意检查。
3. 在仓库 **Settings → Actions → General → Workflow permissions**，选择 **Read and write permissions**，保存。
4. 在仓库 **Settings → Pages → Build and deployment → Source**，选择 **GitHub Actions**，不要选 Deploy from a branch。
5. 打开 **Actions → Germany Price Tracker → Run workflow**，选择 `main` 并运行。流程会抓取、写入 `docs/data/` 并部署 Pages。
6. 页面地址：`https://zacklu0831.github.io/germany-price-tracker/`。查看 Actions 的 **Collect prices** 步骤了解实际抓取状态。即使全失败，也会把失败原因写入网页诊断表。

## 二、部署 Cloudflare Worker（管理商品）

1. 打开 Cloudflare → Workers & Pages → 你原来的 `germany-price-tracker` → Edit code。
2. **备份旧 Worker 代码**，然后将 `worker/worker.js` **完整替换**，Deploy。
3. 在 Worker **Settings → Variables and Secrets** 中检查：

| 变量 | 值/要求 |
|---|---|
| `GITHUB_OWNER` | `zacklu0831` |
| `GITHUB_REPO` | `germany-price-tracker`（只写仓库名） |
| `ALLOWED_GITHUB_LOGIN` | `ZackLu0831` |
| `PAGES_ORIGIN` | `https://zacklu0831.github.io/germany-price-tracker`（末尾不加斜杠） |
| `GITHUB_REPO_TOKEN` | GitHub fine-grained PAT，限定此仓库，Contents: Read and write，**Secret** |
| `GITHUB_CLIENT_ID` | 现有 GitHub OAuth App 的 Client ID |
| `GITHUB_CLIENT_SECRET` | 对应 OAuth App Client Secret，**Secret** |
| `SESSION_SECRET` | 随机至少 32 字符，**Secret**；换掉会使旧登录失效 |

4. OAuth App 的 **Authorization callback URL** 应为：`https://germany-price-tracker.zachlu0831.workers.dev/auth/callback`（如果 Worker 实际域名不同，请按实际域名填写）。
5. 打开：`https://germany-price-tracker.zachlu0831.workers.dev/admin.html`，GitHub 登录。**商品保存到 GitHub 后会触发自动抓取**。

> 注意：本版本的 `PAGES_ORIGIN` 是包含 `/germany-price-tracker` 的完整站点路径，用来从 GitHub Pages 获取管理页面；不是只写 github.io 主域名。

## 三、检查是否成功

- **保存商品**：管理后台显示“已保存到 GitHub”，仓库根目录 `products.json` 同步更新。
- **自动运行**：GitHub Actions 中 `Germany Price Tracker` 的 `Collect prices` 有 `OK` 或 `FAIL` 具体原因。
- **同步显示**：自动任务会复制 `products.json` 到 `docs/data/products.json`，并更新 `docs/data/latest.json` 和 `docs/data/history.json`，然后主动部署 Pages。这样避免网页仍显示旧商品。
- **数据持久化**：价格历史存在 GitHub 仓库 `docs/data/history.json`，保留最多 365 天（网页切换 7/30/90 天）。
- **失败提示**：如果全部链接都抓取失败，GitHub Actions 最终标红，但仍会提交错误诊断并尝试更新网站。

## 四、重要限制

- Amazon、MediaMarkt、OTTO 可能反爬虫、要求 JavaScript 或改变 HTML，**本程序不能保证三个平台每小时都能取得价格**。它不会绕过验证码或伪造价格。需要时可换成商家授权 API 或合规价格数据供应商。
- 同一个商品的三个 URL 必须对应**同一型号、颜色、规格**。系统不会把 Watch Fit 4 与 Watch GT 6 误认为同款；请自己核实链接。
- GitHub Actions 的定时任务为**大约每小时**，GitHub 可能延迟甚至跳过繁忙时段；不是精确到分钟的 SLA。
- 本版本只在网页显示是否达到目标价格，**没有手机推送功能**。
- 商品名称和商家链接会存放在公开 GitHub 仓库；不要把个人信息、账号密码或私密购买链接写进商品字段。

## 文件结构

```
.github/workflows/price-tracker.yml  # 定时/手动/配置变更触发、部署 Pages
src/tracker.py                       # 抓取、异常日志、历史记录
requirements.txt                     # Python 依赖
products.json                        # GitHub 唯一商品配置源
worker/worker.js                     # Cloudflare OAuth 登录和 GitHub 写入
 docs/index.html                     # 监控网页
 docs/admin.html                     # 商品管理后台
 docs/dashboard.js                   # 数据展示
 docs/style.css                      # 页面样式
 docs/data/products.json             # 自动同步的商品快照
 docs/data/latest.json               # 最近采集结果及错误
 docs/data/history.json              # 成功采集的历史价格
```
