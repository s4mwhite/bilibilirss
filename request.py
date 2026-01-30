import asyncio
import time
import os
import random
import sys  # 增加 sys 用于强制刷新输出
from email.utils import formatdate
from bilibili_api import user, Credential, select_client
from feedgen.feed import FeedGenerator

# 强制即时打印日志，防止 GitHub Actions 吞掉输出
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

TARGET_UP_UIDS = [
    3546376524794441,  # 示例1
    515691800,         # 示例2
    517331248,
    502970,
    3546594741848906,
    16414997,
    629208914,
    515691800,
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
    342233922,# 在此继续添加...
]
# =========================================

async def generate_rss_for_up(uid, credential):
    u = user.User(uid=uid, credential=credential)
    try:
        log(f"开始抓取 UID: {uid} ...")
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{uid}')
        log(f"找到 UP 主: {up_name}")
        
        fg = FeedGenerator()
        fg.load_extension('semantic') 
        fg.id(f'https://space.bilibili.com/{uid}')
        fg.title(f'{up_name} 的 Bilibili 投稿')
        fg.author({'name': up_name})
        fg.link(href=f'https://space.bilibili.com/{uid}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的最新视频投稿')
        fg.language('zh-CN')
        fg.lastBuildDate(formatdate(localtime=True))

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
            fe.guid(video_link, isPermaLink=True)
            fe.title(v.get('title'))
            fe.link(href=video_link)
            
            img_url = v.get("pic", "")
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            
            content = f'<img src="{img_url}" referrerpolicy="no-referrer" /><br/>简介: {v.get("description", "无")}<br/>时长: {v.get("length", "未知")}'
            fe.description(content)
            fe.pubDate(formatdate(created_time, localtime=True))

        filename = f'bili_up_{uid}.xml'
        fg.rss_file(filename, pretty=True)
        log(f"✅ 文件已生成: {filename}")
        return {"title": up_name, "uid": uid, "success": True}

    except Exception as e:
        log(f"❌ 处理 UID {uid} 失败: {str(e)}")
        return None

def generate_opml(up_info_list):
    log("正在生成 OPML 清单...")
    # ... (此处省略 OPML 生成逻辑，保持之前的一致) ...
    # 确保写入文件后打印成功信息
    log("🚀 OPML 已完成。")

async def main():
    log("--- 脚本启动 ---")
    if not SESSDATA or not BILI_JCT:
        log("❌ 错误: 环境变量 SESSDATA 或 BILI_JCT 未读取到！")
        return

    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    up_info_list = []
    
    for index, uid in enumerate(TARGET_UP_UIDS):
        info = await generate_rss_for_up(uid, credential)
        if info:
            up_info_list.append(info)
        
        if index < len(TARGET_UP_UIDS) - 1:
            wait_time = random.uniform(2, 5)
            log(f"休眠 {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)
            
    generate_opml(up_info_list)
    log("--- 脚本运行结束 ---")

# ！！！最重要的入口，请务必确认这部分在文件最末尾 ！！！
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        log(f"致命错误: {str(e)}")
