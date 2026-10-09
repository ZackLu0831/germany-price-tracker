# 德国三平台商品价格监控（MediaMarkt / Amazon.de / OTTO.de）

## 配置商品
修改 `products.json`，每个商品包含 `id`、`name`、`target_price` 和 `links`，`links` 可填写三个商家的 HTTPS 商品页面 URL，留空代表不监控。可增加任意数量的商品对象；每个商品 ID 必须唯一且只能用英文字母、数字、下划线、横线。示例已经加入 Huawei Watch GT 7 的 MediaMarkt 链接。

## 部署
1. 创建 GitHub 仓库（GitHub Pages 免费使用公开仓库）。将本压缩包内 `mm-tracker` 文件夹的**内容**上传至仓库根目录，确保 `.github/workflows/monitor.yml` 存在。
2. Settings → Actions → General → Workflow permissions 选择 Read and write permissions。
3. Actions → Monitor German shop prices → Run workflow 手动运行一次。
4. Settings → Pages → Deploy from a branch → main /docs → Save。随后访问 GitHub 提供的 Pages 地址。
5. 每小时约第 17 分钟会触发一次（GitHub 可能延迟或跳过）。在 `products.json` 中修改或新增商品后提交即可。

## 数据与限制
每次运行将有效价格写入 `data/prices.sqlite3` 和 `docs/prices.csv`，状态写入 `docs/status.json`。GitHub Pages 提供按商品的三平台价格曲线与 CSV 下载。历史从开始运行后累积，不能回溯。商品价格提取基于 JSON-LD/HTML meta，不保证 MediaMarkt、Amazon、OTTO 每个页面都可用；反爬虫、地区、登录、Cookie、优惠券、配送费和第三方卖家会影响价格。特别是 Amazon/OTTO 可能提供多个卖家/商品状态：**当前通用提取器无法保证提取的是全新自营价格**，正式决策前请与商品页人工核对。不要绕过访问限制。

## 本地测试
`pip install -r requirements.txt` 然后 `python tracker.py`。

## 100 商品与时间区间
最多 100 个商品组，每组可配置 MediaMarkt、Amazon、OTTO 三条链接，共最多 300 条。网页提供过去 7、30、90 天切换，分别计算各平台的最低、最高、平均价格以及所选区间内首末记录的涨跌额和涨跌幅。区间内无数据时不推测价格。所有历史数据继续保留。

**规模提醒**：300 个链接每小时抓取，当前每链接请求最长 25 秒并暂停 2 秒，极端情况下运行时间较长，GitHub Actions 免费额度、仓库体积及站点访问限制均可能成为瓶颈。不要保证 300 条链接能每小时全部成功。公开 GitHub Pages 会公开监控清单和价格历史。

### Amazon 自营 Buy Box 限制
Amazon.de 仅记录主 Buy Box 中明确标注 Amazon 自营销售的报价；FBA 第三方、无法确认卖家、翻新商品不计入价格曲线。抓取器采用保守策略，Amazon 页面结构变化时可能出现 `seller_unverified` / `amazon_buybox_missing`，不会回退到页面其他报价。此解析器仅通过模拟 HTML 单元测试，尚未在 Amazon.de 实际网页验证；不保证可穿透反爬虫或覆盖所有页面布局。
