import asyncio
import time
from bilibili_api import user, Credential
from feedgen.feed import FeedGenerator

# ================= 配置区 =================
# 虽然获取投稿是公开数据，但带上凭证可以避免被 B 站风控拦截
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")

# 你想要订阅的 UP 主 UID (支持多个，这里先写一个示例)
TARGET_UP_UID = 3546376524794441  # 替换为你想要订阅的UP主UID


# =========================================

async def get_up_videos_rss():
    # 1. 初始化凭证
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)

    # 2. 实例化目标 UP 主
    u = user.User(uid=TARGET_UP_UID, credential=credential)

    # 获取 UP 主基本信息（为了拿到名字做标题）
    info = await u.get_relation_info()
    up_name = info.get('user_info', {}).get('uname', f'UP主_{TARGET_UP_UID}')

    # 3. 创建 RSS 生成器
    fg = FeedGenerator()
    fg.id(f'https://space.bilibili.com/{TARGET_UP_UID}')
    fg.title(f'{up_name} 的 Bilibili 投稿')
    fg.link(href=f'https://space.bilibili.com/{TARGET_UP_UID}', rel='alternate')
    fg.description(f'订阅 {up_name} 的最新视频投稿')
    fg.language('zh-CN')

    print(f"正在获取 {up_name} 的投稿列表...")

    try:
        # 获取该 UP 主的投稿视频列表 (默认第一页)
        res = await u.get_videos()
        v_list = res.get('list', {}).get('vlist', [])

        if not v_list:
            print("未能获取到投稿列表，请检查 UID 是否正确或账号是否有视频。")
            return

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
            # 封面图 + 简介
            fe.description(f'<img src="{pic}" /><br/>{description}')
            # 转换时间
            fe.published(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time)) + ' +0800')

        # 4. 保存文件 (以 UID 命名，方便区分)
        filename = f'bili_up_{TARGET_UP_UID}.xml'
        fg.rss_file(filename, pretty=True)
        print(f"✅ 成功！RSS 已生成: {filename}")

    except Exception as e:
        print(f"❌ 运行出错: {e}")


if __name__ == '__main__':
    asyncio.run(get_up_videos_rss())
