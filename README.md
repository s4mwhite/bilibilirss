# Bilibili RSS

用 GitHub Actions 定时抓取 B 站 UP 主的投稿，生成 RSS，通过 GitHub Pages 提供给 Folo 等阅读器订阅。

## 订阅地址

| 用途 | 地址 |
| --- | --- |
| 合并源（所有 UP 一个源，推荐） | `https://s4mwhite.github.io/bilibilirss/all.xml` |
| 单个 UP | `https://s4mwhite.github.io/bilibilirss/bili_up_<UID>.xml` |
| OPML 批量导入 | `https://s4mwhite.github.io/bilibilirss/subscriptions.opml` |

订阅合并源后，在管理页增删 UP 会自动反映到 Folo，不用再去 Folo 里单独添加。

## 管理页

地址：<https://s4mwhite.github.io/bilibilirss/admin/>

分三个标签页：

- **订阅**：输入 UID 或空间链接添加（支持一次粘贴多个）；暂停 / 启用、删除、备注。修改先暂存，点「保存并更新」后作为一次提交写入 `ups.json`，并自动触发 Actions 重新生成 RSS
- **Cookie**：查看 B 站登录是否有效；粘贴整段 Cookie 自动识别，在浏览器里加密后写入仓库 Secrets
- **运行记录**：最近 10 次运行的结果和耗时，最近一次抓取失败的 UP 及原因

不设置 Token 时是只读模式。保存修改需要一个 Fine-grained Token：

1. 打开 <https://github.com/settings/personal-access-tokens/new>，建议设置过期时间
2. Repository access 选 **Only select repositories** → `bilibilirss`
3. Repository permissions：**Contents** 和 **Actions** 都选 Read and write
4. （可选）**Secrets** 选 Read and write，用于在管理页更新 Cookie。该权限只能覆盖 Secrets，读不出原值

首次设置时还要设一个解锁密码，之后每次打开页面输入密码解锁。

### 安全

管理页是公开的静态页面，任何人都能打开，但没有 Token 只能看、不能改；页面上能看到的内容（UP 清单、抓取状态）本来就是公开的——仓库公开，RSS 也必须公开才能被 Folo 订阅。Cookie 存在 Secrets 里，从不发给页面。

真正需要保护的是 Token，所以：

- **Token 用密码加密保存**：PBKDF2-SHA256（60 万次迭代）派生密钥 + AES-GCM 加密，浏览器里只存密文，解锁后的明文只在内存里。密码无法找回，忘了就点「忘记密码 / 更换 Token」重新设置
- **自动锁定**：连续 30 分钟没有操作自动锁定，也可以随时点「锁定」
- **限制数据去向**：页面的内容安全策略（CSP）只允许连接自身和 `api.github.com`，脚本只允许从 jsDelivr 加载（libsodium，锁定版本并校验 SRI），即使有恶意脚本混进来也没法把 Token 发到别处
- **禁止嵌入**：页面拒绝在 iframe 中运行，防止被其他网站伪装诱导点击

残余风险：`s4mwhite.github.io` 下的其他 Pages 项目和本页同源。如果它们被植入恶意代码，理论上可以在你解锁期间读到内存里的 Token。降低风险的做法：用强密码、给 Token 设过期时间；设备丢失或怀疑泄露时，到 GitHub 设置里撤销这个 Token。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `ups.json` | UP 主清单，管理页或手动编辑；`enabled: false` 为暂停（保留 XML，不再抓取） |
| `request.py` | 抓取脚本 |
| `status.json` | 每次运行的抓取结果（脚本生成，管理页读取） |
| `bili_up_*.xml` / `all.xml` / `subscriptions.opml` | 生成的 RSS 和清单 |

从 `ups.json` 删除的 UP，对应的 XML 会在下次运行时删除。

## Cookie 过期

抓取依赖仓库 Secrets 里的 `SESSDATA`、`BILI_JCT`、`BUVID3`。B 站 Cookie 大约半年失效一次，失效后接口仍可匿名访问，但 412 风控会明显变多。

管理页顶部和 Actions 运行摘要会提示失效。更新方法：

1. 浏览器登录 B 站，打开开发者工具 → Network，点开任意一个 `bilibili.com` 的请求，复制请求头里整段 `Cookie`
2. 在管理页点「更新 Cookie」粘贴，会自动识别 `SESSDATA`、`bili_jct`、`buvid3`，保存后默认立即运行一次验证

值在浏览器里用仓库公钥加密（libsodium sealed box，从 jsDelivr 加载，锁定版本并校验 SRI）后才发给 GitHub。不想给 Token 加 Secrets 权限的话，也可以到仓库 Settings → Secrets and variables → Actions 手动更新同名 Secrets。
