import os
import sqlite3
import yaml
import json
import asyncio
import requests
import random
from datetime import datetime
from playwright.async_api import async_playwright

__version__ = "0.1.2"

# 加载配置
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 初始化数据库
def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT,
            url TEXT UNIQUE,
            title TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# 检查链接是否已推送
def is_new_link(db_path, url):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM history WHERE url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result is None

# 保存推送记录
def save_link(db_path, site_name, url, title):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO history (site_name, url, title) VALUES (?, ?, ?)", 
                       (site_name, url, title))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# 发送 Discord Webhook
def send_discord_webhook(config, item):
    webhook_url = os.environ.get(config['discord']['webhook_url_env'])
    if not webhook_url:
        print(f"错误: 环境变量 {config['discord']['webhook_url_env']} 未设置。")
        return

    # 数据校验，确保 Link 是绝对路径
    if not item.get('link') or not item['link'].startswith('http'):
        print(f"跳过推送: 无效或缺失的链接 '{item.get('link')}'")
        return

    # 随机颜色
    random_color = random.randint(0, 0xFFFFFF)

    embed = {
        "title": item['title'] if item.get('title') else "无标题",
        "url": item['link'],
        "color": random_color,
        "image": {"url": item['image']} if item.get('image') and item['image'].startswith('http') else None,
        "footer": {"text": f"来源: {item['site_name']} • 推送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
    }

    payload = {
        "username": config['discord']['username'],
        "avatar_url": config['discord']['avatar_url'],
        "embeds": [embed]
    }

    response = requests.post(webhook_url, json=payload)
    if response.status_code == 204:
        print(f"推送成功: {item['title']}")
    else:
        print(f"推送失败: {response.status_code}, {response.text}, Payload: {json.dumps(payload)}")

# 发送启动通知
def send_startup_notification(config):
    webhook_url = os.environ.get(config['discord']['webhook_url_env'])
    if not webhook_url:
        return

    embed = {
        "title": "🚀 NSFW 监控系统已启动",
        "description": f"版本号 `{__version__}` 正在检查更新...",
        "color": random.randint(0, 0xFFFFFF),
        "footer": {"text": f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
    }

    payload = {
        "username": config['discord']['username'],
        "avatar_url": config['discord']['avatar_url'],
        "embeds": [embed]
    }
    requests.post(webhook_url, json=payload)

# 采集单个站点
async def scrape_site(page, site_config):
    print(f"Scraping: {site_config['name']} ({site_config['url']})")
    try:
        await page.goto(site_config['url'], timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"Navigation error for {site_config['name']}: {e}")
        return []
    
    if site_config.get('is_spa'):
        await asyncio.sleep(3) # 等待 SPA 加载
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

    items_data = []
    items = await page.query_selector_all(site_config['item_list_selector'])
    
    from urllib.parse import urljoin
    
    for item in items:
        try:
            # 提取标题
            title = ""
            title_el = await item.query_selector(site_config['title_selector'])
            if title_el:
                # 优先尝试属性获取 (针对 xsnvshen)
                if site_config.get('title_attr'):
                    title = await title_el.get_attribute(site_config['title_attr'])
                if not title:
                    title = await title_el.inner_text()
            
            # 提取链接
            link_el = await item.query_selector(site_config['link_selector'])
            link = await link_el.get_attribute('href') if link_el else ""
            if link:
                link = urljoin(site_config['url'], link)
            
            # 提取图片
            img_el = await item.query_selector(site_config['image_selector'])
            image = ""
            if img_el:
                # 尝试多种图片属性 (支持懒加载)
                for attr in ['data-original', 'data-src', 'src']:
                    image = await img_el.get_attribute(attr)
                    if image and not image.endswith('.gif') and 'loading' not in image:
                        break
                
                # 特殊处理 nshens 的 background-image
                if not image and site_config['name'] == 'nshens':
                    style = await img_el.get_attribute('style')
                    if style and 'background-image' in style:
                        import re
                        match = re.search(r'url\("(.*?)"\)', style)
                        if match: image = match.group(1)
                
                if image:
                    if image.startswith('//'):
                        image = 'https:' + image
                    image = urljoin(site_config['url'], image)
            
            if link and title:
                items_data.append({
                    'site_name': site_config['name'],
                    'title': title.strip(),
                    'link': link,
                    'image': image
                })
        except Exception:
            pass
            
    return items_data

async def main():
    config = load_config()
    db_path = config['database']['db_path']
    init_db(db_path)

    # 发送启动通知
    send_startup_notification(config)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 核心：忽略 HTTPS 错误以适配 xiuren.org
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        
        # 伪装 User-Agent
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        for site_config in config['sites']:
            try:
                results = await scrape_site(page, site_config)
                for item in reversed(results): # 逆序处理，保证新内容最后推送点
                    if is_new_link(db_path, item['link']):
                        send_discord_webhook(config, item)
                        save_link(db_path, item['site_name'], item['link'], item['title'])
                    else:
                        # 如果遇到已存在的，对于某些按时间排序的站点可以提前跳过
                        pass
            except Exception as e:
                print(f"Error scraping {site_config['name']}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
