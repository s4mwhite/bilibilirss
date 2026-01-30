import asyncio
import time
import os
import random
from email.utils import formatdate
from bilibili_api import user, Credential, select_client
from feedgen.feed import FeedGenerator

# 选择高性能请求库
select_client("httpx")

# ================= 配置区 =================
# 请确保在 GitHub Repo 的 Settings -> Secrets 中已设置好以下三个变量
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")

# 请修改为您自己的 GitHub 信息，用于生成 OPML 链接
GITHUB_USERNAME = "s4mwhite" 
REPO_NAME = "bilibilirss"

# 在这里添加您想订阅的所有 UP 主 UID
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
    """为单个 UP 主生成 RSS 文件"""
    u = user.User(uid=uid, credential=credential)
    try:
        # 获取 UP 主基本信息
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{uid}')
        print(f"正在处理: {up_name} ({uid})...")
        
        fg = FeedGenerator()
        fg.load_extension('semantic')  # 载入扩展以支持更多元数据
        
        fg.id(f'https://space.bilibili.com/{uid}')
        fg.title(f'{up_name} 的 Bilibili 投稿')
        fg.author({'name': up_name})
        fg.link(href=f'https://space.bilibili.com/{uid}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的最新视频投稿')
        fg.language('zh-CN')
        fg.lastBuildDate(formatdate(localtime=True))

        # 获取投稿列表（取最近 30 条）
        res = await u.get_videos(ps=30) 
        v_list = res.get('list', {}).get('vlist', [])
        
        if not v_list:
            print(f"⚠️  UP 主 {up_name} 暂无投稿或获取失败。")
            return {"title": up_name, "uid": uid, "success": False}

        # 严格按时间倒序排列（新视频在前）
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
            
            # 处理图片链接：补全协议头
            img_url = v.get("pic", "")
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url
            
            # 丰富描述内容
            content = f'<img src="{img_url}" referrerpolicy="no-referrer" /><br/>'
            content += f'简介: {v.get("description", "无")}<br/>'
            content += f'时长: {v.get("length", "未知")}'
            
            fe.description(content)
            # 使用标准的 RFC 822 时间格式
            fe.pubDate(formatdate(created_time, localtime=True))

        filename = f'bili_up_{uid}.xml'
        fg.rss_file(filename, pretty=True)
        print(f"✅ RSS 文件已生成: {filename}")
        return {"title": up_name, "uid": uid, "success": True}

    except Exception as e:
        print(f"❌ 处理 UID {uid} 时出现异常: {e}")
        return None

def generate_opml(up_info_list):
    """生成 OPML 订阅列表文件"""
    opml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head>
        <title>我的 Bilibili 订阅清单</title>
        <dateCreated>{formatdate(localtime=True)}</dateCreated>
    </head>
    <body>
        <outline text="Bilibili 投稿" title="Bilibili 投稿">"""
    
    opml_body = ""
    for up in up_info_list:
        if up and up.get("success"):
            xml_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/bili_up_{up['uid']}.xml"
