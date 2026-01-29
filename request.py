import asyncio
import time
import os  
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
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{TARGET_UP_UID}')
        
        fg = FeedGenerator()
        fg.id(f'https://space.bilibili.com/{TARGET_UP_UID}')
        fg.title(f'{up_name} 的最新投稿')
        fg.link(href=f'https://space.bilibili.com/{TARGET_UP_UID}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的视频投稿 RSS')
        fg.language('zh-CN')

        res = await u.get_videos(ps=30) 
        v_list = res.get('list', {}).get('vlist', [])

        if not v_list:
            return

        # 强制按发布时间从新到旧排序
        v_list.sort(key=lambda x: x.get('created', 0), reverse=True)

        for v in v_list:
            bvid = v.get('bvid')
            created_time = v.get('created', int(time.time()))
            link = f"https://www.bilibili.com/video/{bvid}"

            fe = fg.add_entry()
            # 关键：通过增加时间戳参数，强制阅读器刷新已读状态
            fe.id(f"{link}#{created_time}") 
            fe.title(v.get('title'))
            fe.link(href=link)
            fe.description(f'<img src="{v.get("pic")}" /><br/>{v.get("description", "")}')
            
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time)) + ' +0800'
            fe.published(formatted_time)
            fe.updated(formatted_time)

        filename = f'bili_up_{TARGET_UP_UID}.xml'
        # 不使用 pretty=True 可以减少被浏览器插件误解析的概率
        fg.rss_file(filename) 
        print(f"✅ 成功更新至: {filename}")

    except Exception as e:
        print(f"❌ 出错: {e}")

if __name__ == '__main__':
    asyncio.run(get_up_videos_rss())
