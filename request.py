import asyncio
import glob
import json
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import formatdate, parsedate_to_datetime
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
# RSS 的公开地址。迁到 Cloudflare 后由工作流从 Secrets 传入（随机路径，不含用户名）；
# 没设置时沿用原来的 GitHub Pages 地址
FEED_BASE_URL = (os.getenv("FEED_BASE_URL") or "https://s4mwhite.github.io/bilibilirss").rstrip("/")
# 仓库设为私有后，才把订阅地址写进 status.json 给管理后台显示，公开期间不能泄露
PUBLISH_FEED_BASE = os.getenv("PUBLISH_FEED_BASE") == "true"

# UP 主清单不再写在代码里：用管理页 (admin/) 或直接编辑 ups.json
UPS_FILE = "ups.json"
STATUS_FILE = "status.json"        # 每次运行的抓取结果，管理页读取它显示状态
OPML_FILE = "subscriptions.opml"
ALL_FEED_FILE = "all.xml"          # 所有 UP 合并成一个源，Folo 订阅一次即可

VIDEOS_PER_UP = 30
ALL_FEED_LIMIT = 200
RETRY_DELAYS = [8, 20]             # 412 风控是随机拦截，等一会儿重试大多能过
SECOND_PASS_COOLDOWN = 30          # 第一轮结束后，对失败的 UP 再试一轮前的冷却
INFO_REFRESH_DAYS = 7              # 昵称/头像缓存的刷新周期，减少一半请求
RUN_BUDGET = 20 * 60               # 超过这个时长不再重试，保证在 Actions 30 分钟超时前写完文件
# =========================================

RUN_STARTED = time.monotonic()


def over_budget():
    return time.monotonic() - RUN_STARTED > RUN_BUDGET


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def feed_path(uid):
    return f"bili_up_{uid}.xml"


def https_url(url):
    """强制图片走 https"""
    if not url:
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('http://'):
        return url.replace('http://', 'https://', 1)
    return url


def short_error(e):
    """B 站 412 的异常信息里带整页 HTML，只保留前面的说明"""
    lines = str(e).strip().splitlines()
    first = re.split(r"\s*-\s*<", lines[0])[0] if lines else ""
    return (first or type(e).__name__)[:160]


def load_ups():
    """读取 ups.json，按 UID 去重"""
    with open(UPS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    ups, seen = [], set()
    for item in data.get("ups", []):
        try:
            uid = int(item["uid"])
        except (KeyError, TypeError, ValueError):
            log(f"⚠️ ups.json 中有无效条目，已跳过: {item}")
            continue
        if uid in seen:
            log(f"⚠️ UID {uid} 重复，已跳过")
            continue
        seen.add(uid)
        ups.append({
            "uid": uid,
            "name": (item.get("name") or "").strip(),
            "enabled": item.get("enabled", True) is not False,
        })
    return ups


def load_status():
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f).get("ups", {})
    except (OSError, ValueError):
        return {}


def name_from_feed(uid):
    """从已有的 XML 频道标题里取昵称，作为兜底"""
    try:
        with open(feed_path(uid), encoding="utf-8") as f:
            m = re.search(r"<title>(.*?) 的 Bilibili 投稿</title>", f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def info_is_stale(entry):
    if not entry.get("name") or not entry.get("face") or not entry.get("info_at"):
        return True
    try:
        fetched = datetime.strptime(entry["info_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - fetched > timedelta(days=INFO_REFRESH_DAYS)


async def with_retry(make_call, label, delays=RETRY_DELAYS):
    for attempt in range(len(delays) + 1):
        try:
            return await make_call()
        except Exception as e:
            if attempt == len(delays) or over_budget():
                raise
            wait = delays[attempt] + random.uniform(0, 3)
            log(f"   ↻ {label} 失败（{short_error(e)}），{wait:.1f}s 后重试...")
            await asyncio.sleep(wait)


def write_up_feed(uid, up_name, v_list):
    fg = FeedGenerator()
    # 核心优化 1：Feed ID 增加时间戳，强制阅读器穿透缓存识别为“新更新”
    fg.id(f'https://space.bilibili.com/{uid}?update={int(time.time())}')
    fg.title(f'{up_name} 的 Bilibili 投稿')
    fg.link(href=f'https://space.bilibili.com/{uid}', rel='alternate')
    fg.description(f'B站 UP 主 {up_name} 的最新视频投稿')
    fg.language('zh-CN')
    fg.lastBuildDate(formatdate(localtime=True))

    for v in v_list:
        bvid = v.get('bvid')
        created_time = v.get('created', int(time.time()))
        video_link = f"https://www.bilibili.com/video/{bvid}"

        fe = fg.add_entry(order='append')
        fe.id(video_link)
        fe.title(v.get('title'))
        fe.link(href=video_link)

        # 核心优化 2：强制所有图片走 https 并处理 B 站防盗链
        img_url = https_url(v.get("pic", ""))

        # 使用更标准的 HTML 结构，确保 Folo 解析简介更清晰
        content = f'<img src="{img_url}" referrerpolicy="no-referrer" style="max-width:100%" /><br/><br/>'
        content += f'<b>视频简介:</b> {v.get("description", "无")}<br/>'
        content += f'<b>视频时长:</b> {v.get("length", "未知")}'

        fe.description(content)
        fe.pubDate(formatdate(created_time, localtime=True))

    fg.rss_file(feed_path(uid), pretty=True)


async def process_up(up, credential, prev):
    """抓取单个 UP 主并生成 RSS，返回该 UP 在 status.json 中的新状态"""
    uid = up["uid"]
    entry = dict(prev)
    u = user.User(uid=uid, credential=credential)
    log(f"开始抓取 UID: {uid} ...")
    try:
        res = await with_retry(lambda: u.get_videos(ps=VIDEOS_PER_UP), f"UID {uid} 投稿列表")
        v_list = ((res or {}).get('list') or {}).get('vlist') or []
        v_list.sort(key=lambda x: x.get('created', 0), reverse=True)

        # 投稿列表里自带昵称（联合投稿的作者可能是别人，所以要核对 mid）
        name = entry.get("name")
        own = next((v for v in v_list if str(v.get('mid')) == str(uid) and v.get('author')), None)
        if own:
            name = own['author']

        # 头像和昵称只隔几天刷新一次，平时省掉这个请求
        if info_is_stale({**entry, "name": name}):
            await asyncio.sleep(random.uniform(1, 2))
            try:
                info = await with_retry(lambda: u.get_user_info(), f"UID {uid} 用户信息", delays=RETRY_DELAYS[:1])
                name = info.get('name') or name
                entry["face"] = https_url(info.get('face')) or entry.get("face")
                entry["info_at"] = now_iso()
            except Exception as e:
                log(f"   ⚠️ UID {uid} 用户信息获取失败，不影响 RSS: {short_error(e)}")

        name = name or up["name"] or name_from_feed(uid) or f'UP主_{uid}'
        write_up_feed(uid, name, v_list)

        latest = v_list[0] if v_list else None
        entry.update({
            "name": name,
            "ok": True,
            "last_ok_at": now_iso(),
            "last_error": None,
            "fail_streak": 0,
            "video_count": len(v_list),
            "latest": {
                "title": latest.get("title"),
                "bvid": latest.get("bvid"),
                "created": latest.get("created"),
            } if latest else None,
        })
        if v_list:
            log(f"✅ 文件生成成功: {feed_path(uid)}")
        else:
            log(f"⚠️ {name} 暂无投稿，已生成空 RSS。")
    except Exception as e:
        log(f"❌ UID {uid} 处理出错: {short_error(e)}")
        entry.update({
            "ok": False,
            "last_error": short_error(e),
            "last_error_at": now_iso(),
            "fail_streak": entry.get("fail_streak", 0) + 1,
        })
    return entry


def display_name(up, status):
    return status.get(str(up["uid"]), {}).get("name") or up["name"] or name_from_feed(up["uid"]) or f'UP主_{up["uid"]}'


def read_feed_items(uid):
    """读回已生成的单 UP XML（包括这次抓取失败、沿用上次结果的）"""
    try:
        root = ET.parse(feed_path(uid)).getroot()
    except (OSError, ET.ParseError):
        return []
    items = []
    for it in root.iter('item'):
        try:
            published = parsedate_to_datetime(it.findtext('pubDate'))
        except (TypeError, ValueError):
            continue
        items.append({
            "title": it.findtext('title') or "",
            "link": it.findtext('link') or "",
            "guid": it.findtext('guid') or it.findtext('link') or "",
            "description": it.findtext('description') or "",
            "published": published,
        })
    return items


def generate_all_feed(ups, status):
    log("正在生成合并源 all.xml ...")
    entries = []
    for up in ups:
        name = display_name(up, status)
        for item in read_feed_items(up["uid"]):
            entries.append((name, item))
    entries.sort(key=lambda x: x[1]["published"], reverse=True)

    fg = FeedGenerator()
    fg.load_extension('dc')
    fg.id(f'{FEED_BASE_URL}/{ALL_FEED_FILE}')
    fg.title('Bilibili 订阅合集')
    fg.link(href='https://www.bilibili.com/', rel='alternate')
    fg.description(f'{len(ups)} 位 B站 UP 主的最新投稿合集')
    fg.language('zh-CN')
    fg.lastBuildDate(formatdate(localtime=True))

    for name, item in entries[:ALL_FEED_LIMIT]:
        fe = fg.add_entry(order='append')
        fe.id(item["guid"])
        fe.title(f'【{name}】{item["title"]}')
        fe.link(href=item["link"])
        fe.description(item["description"])
        fe.pubDate(item["published"])
        fe.dc.dc_creator(name)

    fg.rss_file(ALL_FEED_FILE, pretty=True)
    log(f"✅ all.xml 已生成，共 {min(len(entries), ALL_FEED_LIMIT)} 条")


def generate_opml(ups, status):
    """生成 OPML 清单，链接带随机参数解决阅读器 404 缓存"""
    log("正在生成最终 OPML 清单...")
    timestamp = int(time.time())
    opml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head><title>我的 Bilibili 订阅清单</title></head>
    <body><outline text="Bilibili 投稿">"""

    opml_body = ""
    for up in ups:
        # 本轮抓取失败但之前生成过 XML 的 UP 也保留在清单里
        if not os.path.exists(feed_path(up["uid"])):
            continue
        # 核心优化 3：在链接后附带动态版本号，彻底解决 Folo 记忆旧 404 状态的问题
        xml_url = f"{FEED_BASE_URL}/{feed_path(up['uid'])}?v={timestamp}"
        html_url = f"https://space.bilibili.com/{up['uid']}"
        # 字符转义防止 OPML 格式崩溃
        safe_title = (display_name(up, status).replace('&', '&amp;').replace('<', '&lt;')
                      .replace('>', '&gt;').replace('"', '&quot;'))
        opml_body += f'\n            <outline type="rss" text="{safe_title}" title="{safe_title}" xmlUrl="{xml_url}" htmlUrl="{html_url}"/>'

    with open(OPML_FILE, "w", encoding="utf-8") as f:
        f.write(opml_header + opml_body + "\n        </outline></body></opml>")
    log(f"🚀 OPML 已就绪，已注入更新指纹: {timestamp}")


def remove_orphan_feeds(ups):
    """从 ups.json 删除的 UP，对应的 XML 一并删除（暂停的保留）"""
    keep = {feed_path(up["uid"]) for up in ups}
    for path in glob.glob("bili_up_*.xml"):
        if path not in keep:
            os.remove(path)
            log(f"🗑️ 已删除不再订阅的 {path}")


def write_status(ups, status, run):
    data = {
        "updated_at": now_iso(),
        "run": run,
        "ups": {str(up["uid"]): status[str(up["uid"])] for up in ups if str(up["uid"]) in status},
    }
    if PUBLISH_FEED_BASE:
        data["feed_base"] = FEED_BASE_URL
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_step_summary(ups, status, run):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    login = {True: "✅ 有效", False: "❌ 已失效，请更新 Secrets", None: "⚠️ 检查失败"}[run["login_ok"]]
    lines = [f"### 成功 {run['ok']} / 失败 {run['failed']}（共 {run['total']} 个启用的 UP）", "", f"登录状态：{login}", ""]
    failed = [up for up in ups if up["enabled"] and status.get(str(up["uid"]), {}).get("ok") is False]
    if failed:
        lines += ["| UP | UID | 连续失败 | 错误 |", "| --- | --- | --- | --- |"]
        for up in failed:
            s = status[str(up["uid"])]
            lines.append(f"| {display_name(up, status)} | {up['uid']} | {s.get('fail_streak', 0)} | {s.get('last_error', '')} |")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main():
    log("--- 脚本启动 (全量增强版) ---")
    if not SESSDATA:
        log("❌ 严重错误: 环境变量 SESSDATA 未设置！")
        sys.exit(1)

    started_at = now_iso()
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)

    # Cookie 过期后接口仍能匿名访问，但 412 风控会明显变多，所以单独检查一次
    login_ok = None
    try:
        login_ok = await credential.check_valid()
    except Exception as e:
        log(f"🔑 登录状态检查失败: {short_error(e)}")
    if login_ok:
        log("🔑 登录状态: 有效")
    elif login_ok is False:
        log("🔑 登录状态: 已失效，请重新登录 B 站并更新 SESSDATA / BILI_JCT / BUVID3 三个 Secrets")
        if os.getenv("GITHUB_ACTIONS"):
            log("::warning::B 站 Cookie 已失效，请更新仓库 Secrets（SESSDATA / BILI_JCT / BUVID3）")

    ups = load_ups()
    status = load_status()
    enabled = [up for up in ups if up["enabled"]]
    log(f"共 {len(ups)} 个 UP，启用 {len(enabled)} 个")

    # 第二轮基于运行前的状态计算，连续失败次数按“运行”而不是按“轮”累加
    prev_status = dict(status)
    pending = enabled
    for round_no in (1, 2):
        if round_no == 2:
            # 第一轮全军覆没多半是 Cookie 失效，不必再试
            if not pending or len(pending) == len(enabled):
                break
            if over_budget():
                log(f"⏱️ 已运行超过 {RUN_BUDGET // 60} 分钟，跳过第二轮，{len(pending)} 个失败的 UP 沿用上次结果")
                break
            log(f"--- 第二轮：{len(pending)} 个 UP 失败，冷却 {SECOND_PASS_COOLDOWN}s 后重试 ---")
            await asyncio.sleep(SECOND_PASS_COOLDOWN)
        failed = []
        for index, up in enumerate(pending):
            key = str(up["uid"])
            status[key] = await process_up(up, credential, prev_status.get(key, {}))
            if not status[key]["ok"]:
                failed.append(up)

            # 串行减速，保护账号安全
            if index < len(pending) - 1:
                wait_time = random.uniform(2, 4)
                log(f"☕ 减速中，等待 {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)
        pending = failed

    remove_orphan_feeds(ups)
    generate_all_feed(enabled, status)
    generate_opml(enabled, status)

    run = {
        "started_at": started_at,
        "finished_at": now_iso(),
        "total": len(enabled),
        "ok": len(enabled) - len(pending),
        "failed": len(pending),
        "login_ok": login_ok,
    }
    if os.getenv("GITHUB_RUN_ID"):
        run["url"] = f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
    write_status(ups, status, run)
    write_step_summary(ups, status, run)
    log(f"--- 所有任务执行完毕：成功 {run['ok']}，失败 {run['failed']} ---")

    # 一个都没抓到（通常是 Cookie 过期）时让 Actions 标红，GitHub 会发邮件提醒
    if enabled and run["ok"] == 0:
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
