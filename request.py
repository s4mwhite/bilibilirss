import asyncio
import time
import json
import os
import random
import sys
from email.utils import formatdate
from bilibili_api import user, Credential, select_client
from feedgen.feed import FeedGenerator

# 强制即时打印日志
def log(msg):
    print(msg)
    sys.stdout.flush()

select_client("httpx")

# ================= 配置区 =================
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")
GITHUB_USERNAME = "s4mwhite"
REPO_NAME = "bilibilirss"

# 关注列表统一存放在 ups.json，由网页管理界面维护。
# 此处保留一份兜底列表：仅当 ups.json 缺失或损坏时使用。
FALLBACK_UP_UIDS = [
    3546376524794441,
    515691800,
    517331248,
    502970,
    3546594741848906,
    16414997,
    629208914,
    546189,
    487511093,
    1809567655,
    412719797,
    470346704,
    21869937,
    256724889,
    2035453562,
    102438649,
    508215481,
    7212583,
    375241551,
    5294454,
    1847661,
    297786973,
    14804670,
    362588980,
    893053,
    88461692,
    125526,
    7349,
    10462362,
    1238329219,
    482439223,
    342233922,
    346563107,
]
UPS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ups.json")
# =========================================


def load_ups():
    """从 ups.json 读取关注列表，去重并保持原有顺序。

    返回 [{"uid": int, "name": str, "note": str}, ...]。
    文件缺失/损坏时回退到 FALLBACK_UP_UIDS，保证定时任务不断。
    """
    try:
        with open(UPS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = []
        seen = set()
        for item in data:
            try:
                uid = int(str(item.get("uid", "")).strip())
            except (ValueError, TypeError, AttributeError):
                continue
            if uid <= 0 or uid in seen:
                continue
            seen.add(uid)
            entries.append({
                "uid": uid,
                "name": str(item.get("name", "") or ""),
                "note": str(item.get("note", "") or ""),
            })
        if entries:
            log(f"📋 已从 ups.json 载入 {len(entries)} 个关注 UP 主")
            return entries
        log("⚠️ ups.json 为空，回退到内置列表")
    except FileNotFoundError:
        log("⚠️ 未找到 ups.json，回退到内置列表")
    except (json.JSONDecodeError, OSError) as e:
        log(f"⚠️ ups.json 读取失败 ({e})，回退到内置列表")
    return [{"uid": uid, "name": "", "note": ""} for uid in dict.fromkeys(FALLBACK_UP_UIDS)]


def sync_names_back(fetched):
    """把本次成功抓取到的最新 UP 昵称写回 ups.json。

    让管理界面无需手动维护昵称；只有发生变化时才写文件，
    避免每次定时任务都产生无意义的 git diff。
    fetched: {uid: name}
    """
    if not fetched or not os.path.exists(UPS_JSON_PATH):
        return
    try:
        with open(UPS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    changed = False
    for item in data:
        try:
            uid = int(str(item.get("uid", "")).strip())
        except (ValueError, TypeError, AttributeError):
            continue
        new_name = fetched.get(uid)
        if new_name and item.get("name") != new_name:
            item["name"] = new_name
            changed = True
    if changed:
        with open(UPS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        log("📝 UP 主昵称已同步回 ups.json")
    else:
        log("📝 昵称无变化，ups.json 无需更新")

async def generate_rss_for_up(uid, credential):
    """生成单个 UP 主的 RSS，带强制刷新机制"""
    u = user.User(uid=uid, credential=credential)
    try:
        log(f"开始抓取 UID: {uid} ...")
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{uid}')

        fg = FeedGenerator()
        # 核心优化 1：Feed ID 增加时间戳，强制阅读器穿透缓存识别为“新更新”
        fg.id(f'https://space.bilibili.com/{uid}?update={int(time.time())}')
        fg.title(f'{up_name} 的 Bilibili 投稿')
        fg.link(href=f'https://space.bilibili.com/{uid}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的最新视频投稿')
        fg.language('zh-CN')
        fg.lastBuildDate(formatdate(localtime=True))

        # 抓取最近 30 条视频
        res = await u.get_videos(ps=30)
        v_list = res.get('list', {}).get('vlist', [])

        if not v_list:
            log(f"⚠️ {up_name} 暂无投稿。")
            return {"title": up_name, "uid": uid, "success": True}

        v_list.sort(key=lambda x: x.get('created', 0), reverse=True)

        for v in v_list:
            bvid = v.get('bvid')
            created_time = v.get('created', int(time.time()))
            video_link = f"https://www.bilibili.com/video/{bvid}"

            fe = fg.add_entry()
            fe.id(video_link)
            fe.title(v.get('title'))
            fe.link(href=video_link)

            # 核心优化 2：强制所有图片走 https 并处理 B 站防盗链
            img_url = v.get("pic", "")
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('http://'):
                    img_url = img_url.replace('http://', 'https://')

            # 使用更标准的 HTML 结构，确保 Folo 解析简介更清晰
            content = f'<img src="{img_url}" referrerpolicy="no-referrer" style="max-width:100%" /><br/><br/>'
            content += f'<b>视频简介:</b> {v.get("description", "无")}<br/>'
            content += f'<b>视频时长:</b> {v.get("length", "未知")}'

            fe.description(content)
            fe.pubDate(formatdate(created_time, localtime=True))

        filename = f'bili_up_{uid}.xml'
        fg.rss_file(filename, pretty=True)
        log(f"✅ 文件生成成功: {filename}")
        return {"title": up_name, "uid": uid, "success": True}

    except Exception as e:
        log(f"❌ UID {uid} 处理出错: {str(e)}")
        return None

def generate_opml(up_info_list):
    """生成 OPML 清单，链接带随机参数解决阅读器 404 缓存"""
    log("正在生成最终 OPML 清单...")
    timestamp = int(time.time())
    opml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head><title>我的 Bilibili 订阅清单</title></head>
    <body><outline text="Bilibili 投稿">"""

    opml_body = ""
    for up in up_info_list:
        if up and up.get("success"):
            # 核心优化 3：在链接后附带动态版本号，彻底解决 Folo 记忆旧 404 状态的问题
            xml_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/bili_up_{up['uid']}.xml?v={timestamp}"
            html_url = f"https://space.bilibili.com/{up['uid']}"
            # 字符转义防止 OPML 格式崩溃
            safe_title = up["title"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            opml_body += f'\n            <outline type="rss" text="{safe_title}" title="{safe_title}" xmlUrl="{xml_url}" htmlUrl="{html_url}"/>'

    with open("subscriptions.opml", "w", encoding="utf-8") as f:
        f.write(opml_header + opml_body + "\n        </outline></body></opml>")
    log(f"🚀 OPML 已就绪，已注入更新指纹: {timestamp}")

async def main():
    log("--- 脚本启动 (全量增强版) ---")
    if not SESSDATA:
        log("❌ 严重错误: 环境变量 SESSDATA 未设置！")
        return

    entries = load_ups()
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    up_info_list = []
    fetched_names = {}

    for index, entry in enumerate(entries):
        uid = entry["uid"]
        info = await generate_rss_for_up(uid, credential)
        if info:
            up_info_list.append(info)
            fetched_names[uid] = info["title"]

        # 串行减速，保护账号安全
        if index < len(entries) - 1:
            wait_time = random.uniform(2, 4)
            log(f"☕ 减速中，等待 {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)

    generate_opml(up_info_list)
    sync_names_back(fetched_names)
    log("--- 所有任务执行完毕 ---")

if __name__ == '__main__':
    asyncio.run(main())
