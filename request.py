import asyncio
import time
import os
from email.utils import formatdate
from bilibili_api import user, Credential, select_client
from feedgen.feed import FeedGenerator

select_client("httpx")

# ================= 配置区 =================
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")
TARGET_UP_UID = 3546376524794441 
# =========================================

async def get_up_videos_rss():
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    u = user.User(uid=TARGET_UP_UID, credential=credential)

    try:
        # 1. 获取 UP 主信息
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{TARGET_UP_UID}')
        
        fg = FeedGenerator()
        # 2. 注入 RSSHub 必备的 Atom 命名空间
        fg.load_extension('semantic') 
        
        fg.id(f'https://space.bilibili.com/{TARGET_UP_UID}')
        fg.title(f'{up_name} 的 Bilibili 投稿')
        # RSSHub 风格的作者声明
        fg.author({'name': up_name})
        fg.link(href=f'https://space.bilibili.com/{TARGET_UP_UID}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的最新视频投稿')
        fg.language('zh-CN')
        fg.lastBuildDate(formatdate(localtime=True))

        # 3. 获取投稿并排序
        res = await u.get_videos(ps=30) 
        v_list = res.get('list', {}).get('vlist', [])
        if not v_list:
            print("未获取到视频列表")
            return
        
        # 严格倒序（新在前）
        v_list.sort(key=lambda x: x.get('created', 0), reverse=True)

        for v in v_list:
            bvid = v.get('bvid')
            created_time = v.get('created', int(time.time()))
            video_link = f"https://www.bilibili.com/video/{bvid}"

            fe = fg.add_entry()
            # RSSHub 风格的 ID 和 GUID
            fe.id(video_link)
            fe.guid(video_link, isPermaLink=True)
            fe.title(v.get('title'))
            fe.link(href=video_link)
            
            # 4. RSSHub 风格的内容描述 (加入视频详情)
            # 包含封面图和简介，强制不缓存图片
            img_url = v.get("pic")
            if img_url and not img_url.startswith('http'):
                img_url = 'https:' + img_url
            
            content = f'<img src="{img_url}" referrerpolicy="no-referrer" /><br/>'
            content += f'简介: {v.get("description", "无")}<br/>'
            content += f'时长: {v.get("length", "未知")}'
            
            fe.description(content)
            # 使用 RFC 822 时间格式
            fe.pubDate(formatdate(created_time, localtime=True))

        # 5. 生成文件
        filename = f'bili_up_{TARGET_UP_UID}.xml'
        # RSSHub 生成的是非常紧凑的 XML，我们也保持 pretty=True 方便观察
        fg.rss_file(filename, pretty=True)
        print(f"✅ 已生成对标 RSSHub 的文件: {filename}")

    except Exception as e:
        print(f"❌ 运行异常: {e}")

if __name__ == '__main__':
    asyncio.run(get_up_videos_rss())
