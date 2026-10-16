# Bilibili RSS

用 GitHub Actions 定时抓取 B 站 UP 主的投稿，生成 RSS，部署到 Cloudflare Pages 给 Folo 等阅读器订阅。仓库私有，只有本人使用。

## 架构

| 部分 | 位置 | 谁能访问 |
| --- | --- | --- |
| 代码、UP 清单、抓取状态 | 本仓库（私有） | 只有你 |
| RSS | Cloudflare Pages「RSS 项目」的随机路径下，根目录为空 | 知道完整地址的人（你和 Folo），不在任何地方公开链接 |
| 管理后台 | Cloudflare Pages「后台项目」，整站由 Cloudflare Access 保护 | 只有你的邮箱能登录 |

订阅地址在管理后台「订阅」页显示（工作流在仓库私有后才会把地址写进 `status.json`）。订阅合并源 `all.xml` 后，在后台增删 UP 会自动反映到 Folo。

### 需要的 Secrets

| 名称 | 说明 |
| --- | --- |
| `SESSDATA` / `BILI_JCT` / `BUVID3` | B 站 Cookie |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token，权限 Account → Cloudflare Pages → Edit |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 ID |
| `CF_FEEDS_PROJECT` / `CF_ADMIN_PROJECT` | 两个 Pages 项目名（随机，首次部署时自动创建） |
| `FEED_BASE_URL` | RSS 地址前缀：`https://<RSS 项目>.pages.dev/<随机路径>` |

没有 `CLOUDFLARE_API_TOKEN` 时工作流跳过部署，只生成并提交文件。部署逻辑见 `deploy/cloudflare.sh`。

### 后台的登录保护（Cloudflare Access）

Zero Trust → Access → Applications → Add an application → Self-hosted：

- Application domain 填后台项目的 `<项目名>.pages.dev`，再加一条 `*.<项目名>.pages.dev`（保护预览部署）
- Policy：Action 选 Allow，Include → Emails 填你自己的邮箱
- 登录方式用默认的 One-time PIN（邮箱验证码）

## 管理后台

分三个标签页：

- **订阅**：输入 UID 或空间链接添加（支持一次粘贴多个）；暂停 / 启用、删除、备注。修改先暂存，点「保存并更新」后作为一次提交写入 `ups.json`，并自动触发 Actions 重新生成 RSS
- **Cookie**：查看 B 站登录是否有效；粘贴整段 Cookie 自动识别，在浏览器里加密后写入仓库 Secrets
- **运行记录**：最近 10 次运行的结果和耗时，最近一次抓取失败的 UP 及原因

首次打开需要填写仓库名（`owner/name`）和一个 Fine-grained Token，并设一个解锁密码：

1. 打开 <https://github.com/settings/personal-access-tokens/new>，建议设置过期时间
2. Repository access 选 **Only select repositories** → 本仓库
3. Repository permissions：**Contents** 和 **Actions** 都选 Read and write
4. （可选）**Secrets** 选 Read and write，用于在后台更新 Cookie。该权限只能覆盖 Secrets，读不出原值

### 安全

- **两层登录**：先过 Cloudflare Access（邮箱验证码），再用本地密码解锁。页面源码里不包含 GitHub 用户名和仓库名，解锁前不请求任何数据
- **仓库名和 Token 用密码加密保存**：PBKDF2-SHA256（60 万次迭代）派生密钥 + AES-GCM 加密，浏览器里只存密文，解锁后的明文只在内存里。密码无法找回，忘了就点「忘记密码 / 更换 Token」重新设置
- **自动锁定**：连续 30 分钟没有操作自动锁定，锁定时把仓库名和已读取的数据一起从内存清掉
- **限制数据去向**：CSP 只允许连接 `api.github.com`，脚本只允许从 jsDelivr 加载（libsodium，锁定版本并校验 SRI）；禁止 iframe 嵌入；不发送 Referer；`noindex` 禁止搜索引擎收录
- **RSS 不暴露身份**：地址和内容里不包含 GitHub 用户名，所在站点根目录为空

建议给 Token 设过期时间；设备丢失或怀疑泄露时，到 GitHub 设置里撤销 Token，并在 Cloudflare 撤销 API Token。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `ups.json` | UP 主清单，管理后台或手动编辑；`enabled: false` 为暂停（保留 XML，不再抓取） |
| `request.py` | 抓取脚本 |
| `status.json` | 每次运行的抓取结果（脚本生成，管理后台读取） |
| `deploy/cloudflare.sh` | 部署到 Cloudflare Pages |
| `bili_up_*.xml` / `all.xml` / `subscriptions.opml` | 生成的 RSS 和清单 |

从 `ups.json` 删除的 UP，对应的 XML 会在下次运行时删除。

## Cookie 过期

抓取依赖仓库 Secrets 里的 `SESSDATA`、`BILI_JCT`、`BUVID3`。B 站 Cookie 大约半年失效一次，失效后接口仍可匿名访问，但 412 风控会明显变多。

管理后台和 Actions 运行摘要会提示失效。更新方法：

1. 浏览器登录 B 站，打开开发者工具 → Network，点开任意一个 `bilibili.com` 的请求，复制请求头里整段 `Cookie`
2. 在管理后台的「Cookie」页粘贴，会自动识别 `SESSDATA`、`bili_jct`、`buvid3`，保存后默认立即运行一次验证

值在浏览器里用仓库公钥加密（libsodium sealed box，从 jsDelivr 加载，锁定版本并校验 SRI）后才发给 GitHub。不想给 Token 加 Secrets 权限的话，也可以到仓库 Settings → Secrets and variables → Actions 手动更新同名 Secrets。
