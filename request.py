import asyncio
import time
import os  # <-- 必须加上这个，否则 os.getenv 会报错
from bilibili_api import user, Credential, select_client
from feedgen.feed import FeedGenerator

# 确保选择请求库
select_client("httpx")

# ================= 配置区 =================
# 从 GitHub Secrets 中读取，保护隐私
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")
TARGET_UP_UID = 3546376524794441
# =========================================

async def get_up_videos_rss():
    # 实例化凭证
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    # 实例化用户类
    u = user.User(uid=TARGET_UP_UID, credential=credential)

    try:
        # 获取用户基本信息
        info = await u.get_user_info()
        up_name = info.get('name', f'UP主_{TARGET_UP_UID}')
        
        # 初始化 RSS 生成器
        fg = FeedGenerator()
        fg.id(f'https://space.bilibili.com/{TARGET_UP_UID}')
        fg.title(f'{up_name} 的最新投稿')
        fg.link(href=f'https://space.bilibili.com/{TARGET_UP_UID}', rel='alternate')
        fg.description(f'B站 UP 主 {up_name} 的视频投稿 RSS')
        fg.language('zh-CN')

        print(f"正在获取 {up_name} 的投稿列表...")

        # 获取投稿
        res = await u.get_videos(ps=30) 
        v_list = res.get('list', {}).get('vlist', [])

        if not v_list:
            print("未能获取到投稿列表，请确认 UID 是否正确。")
            return

        # ========================================================
        # 【核心修正】按发布时间(created)从新到旧排序
        # 这样无论 B 站接口怎么变，XML 第一条永远是最新的
        # ========================================================
        v_list.sort(key=lambda x: x.get('created', 0), reverse=True)
        # ========================================================

        for v in v_list:
            title = v.get('title')
            bvid = v.get('bvid')
            pic = v.get('pic')
            description = v.get('description', '')
            created_time = v.get('created', int(time.time()))

            link = f"https://www.bilibili.com/video/{bvid}"

            fe = fg.add_entry()
            fe.id(link)
            fe.title(title)
            fe.link(href=link)
            fe.description(f'<img src="{pic}" /><br/>{description}')
            
            # 转换时间为 RSS 标准格式
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time)) + ' +0800'
            fe.published(formatted_time)
            fe.updated(formatted_time)

        filename = f'bili_up_{TARGET_UP_UID}.xml'
        fg.rss_file(filename, pretty=True)
        print(f"✅ 成功！文件已生成: {filename}")

    except Exception as e:
        print(f"❌ 运行出错: {e}")

if __name__ == '__main__':
    asyncio.run(get_up_videos_rss())
