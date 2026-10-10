# Bilibili RSS 订阅器 📺

把关注的 B 站 UP 主的最新投稿变成标准 RSS，通过 OPML 一键导入阅读器（如 Folo、Inoreader、FreshRSS）。

## 工作原理

```
你在网页上增删 UP 主
        │  保存（GitHub API 写回 ups.json）
        ▼
GitHub Actions 自动运行 request.py（定时每 4 小时 + ups.json 变更时）
        │  抓取每个 UP 主最新 30 条投稿
        ▼
生成 bili_up_{uid}.xml + subscriptions.opml，提交回仓库
        │  GitHub Pages 自动发布（全免费）
        ▼
阅读器订阅 OPML / 单条 RSS
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `index.html` | 🆕 网页管理界面：增删 UP 主、搜索、备注、OPML 导入、一键保存 |
| `ups.json` | 🆕 关注列表数据源：`[{uid, name, note}]`，由管理页维护，定时任务自动同步最新昵称 |
| `request.py` | RSS/OPML 生成脚本：从 `ups.json` 读取列表（文件缺失/损坏时自动回退内置列表，不断更） |
| `.github/workflows/update_rss.yml` | 定时 + 推送触发器 |
| `bili_up_*.xml` | 每个 UP 主的 RSS（自动生成，不要手改） |
| `subscriptions.opml` | 订阅清单（自动生成，导入阅读器用这一个文件） |

## 🆓 免费部署管理界面（零成本方案）

管理页是**纯静态单文件**，直接复用本仓库已有的 GitHub Pages，不需要任何服务器、不需要备案、不花一分钱。

### 步骤

1. **把本分支合并到 `main`**
   合并后 `index.html` / `ups.json` 就会随仓库发布。
2. **确认 Pages 已开启**（一般你之前已开过，开过可跳过）：
   仓库页 → `Settings` → `Pages` → `Build and deployment` →
   `Source` 选 `Deploy from a branch`，`Branch` 选 `main` / `(root)` → `Save`。
   等 1～2 分钟，访问：
   ```
   https://s4mwhite.github.io/bilibilirss/
   ```
   能看到管理界面即成功。
3. **创建一个 Token**（只做一次，用于“保存”时写回仓库）：
   - 打开 <https://github.com/settings/tokens/new>，建议选 **Fine-grained** 精细 Token；
   - `Repository access` → `Only select repositories` → 只勾选本仓库；
   - `Permissions` → `Contents` → **Read and write**，其余默认；
   - 有效期建议 90 天以上，生成后复制。
4. **在管理页填写配置并保存**：
   Owner / 仓库 / 分支默认已填好，粘贴 Token → `测试连接` → 成功后即可正常增删，
   点 `💾 保存到 GitHub`。保存后 Actions 会自动跑（约 1～5 分钟），
   可点 `▶ 去看同步进度` 跟踪。
5. **订阅**：把页面上的 OPML 地址
   `https://s4mwhite.github.io/bilibilirss/subscriptions.opml`
   导入 Folo 等阅读器即可。

### 费用

| 项 | 费用 |
|---|---|
| GitHub Pages 静态托管（含管理页 + 全部 RSS） | 免费 |
| GitHub Actions（公开仓库） | 免费（额度远超本项目用量） |
| Token / API 调用 | 免费 |

### 日常使用

- 加关注：粘 UID 或 B 站空间链接（支持批量多行），点加入 → 保存。
- 减关注：点删除 / 勾选批量删 → 保存。
- 搬家/备份：`下载备份（ups.json）`；旧 OPML 可用 `从 OPML 导入` 一次迁入。
- 改备注：列表里直接写，会随保存一起提交。

## 常见问题

- **保存时 401**：Token 无效或过期，重新生成一个填入即可。
- **保存时 404**：Owner / 仓库 / 分支填错了。
- **保存时 422**：云端文件在你编辑期间变了，点“从云端重新载入”后再改再保存。
- **本地双击打开 index.html 提示读不到数据**：浏览器安全限制，`file://` 下读不了相对文件。
  用 `python3 -m http.server` 在仓库目录起个服务再访问，或直接部署到 Pages 后使用。
- **新增的 UP 主昵称显示“待同步”**：正常，下一次 Actions 跑完会自动填上。
- **Token 安全**：Token 只存在你浏览器的 localStorage，不会提交到仓库、不经过第三方。
  建议用有效期短一点的细粒度 Token，只授权这一个仓库的 Contents 读写。

## 本地开发

```bash
pip install -r requirements.txt
python request.py          # 需要 SESSDATA / BILI_JCT / BUVID3 环境变量
python3 -m http.server 8099  # 预览管理界面 http://localhost:8099/
```
