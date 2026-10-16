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

- 添加：输入 UID 或空间链接（`space.bilibili.com/xxx`），支持一次粘贴多个
- 暂停 / 启用、删除、备注；修改先暂存，点「保存并更新」后作为一次提交写入 `ups.json`
- 保存后会自动触发 Actions 重新生成 RSS（约 3–5 分钟），也可以点「立即更新」
- 显示每个 UP 的抓取状态、最新投稿，以及 B 站登录 Cookie 是否已失效

不设置 Token 时是只读模式。保存修改需要一个 Fine-grained Token：

1. 打开 <https://github.com/settings/personal-access-tokens/new>
2. Repository access 选 **Only select repositories** → `bilibilirss`
3. Repository permissions：**Contents** 和 **Actions** 都选 Read and write

Token 只保存在浏览器里，只发送给 `api.github.com`。注意 localStorage 按域名隔离，`s4mwhite.github.io` 下的其他 Pages 项目也能读到它；介意的话在设置时不勾选「记住」，关闭页面后即失效。

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

管理页顶部和 Actions 运行摘要会提示失效。更新方法：浏览器登录 B 站 → 开发者工具 → Application → Cookies → `bilibili.com`，复制 `SESSDATA`、`bili_jct`、`buvid3` 的值，到仓库 Settings → Secrets and variables → Actions 中更新同名 Secrets。
