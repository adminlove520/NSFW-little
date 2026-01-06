import os
import sqlite3
import yaml
import json
import asyncio
import requests
import random
from datetime import datetime
from playwright.async_api import async_playwright

__version__ = "0.1.0"

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
        print(f"Error: {config['discord']['webhook_url_env']} is not set.")
        return

    # 随机颜色
    random_color = random.randint(0, 0xFFFFFF)

    embed = {
        "title": item['title'],
        "url": item['link'],
        "color": random_color,
        "image": {"url": item['image']},
        "footer": {"text": f"From {item['site_name']} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
    }

    payload = {
        "username": config['discord']['username'],
        "avatar_url": config['discord']['avatar_url'],
        "embeds": [embed]
    }

    response = requests.post(webhook_url, json=payload)
    if response.status_code == 204:
        print(f"Successfully pushed: {item['title']}")
    else:
        print(f"Failed to push: {response.status_code}, {response.text}")

# 发送启动通知
def send_startup_notification(config):
    webhook_url = os.environ.get(config['discord']['webhook_url_env'])
    if not webhook_url:
        return

    embed = {
        "title": "🚀 NSFW Monitor Started",
        "description": f"Version `{__version__}` is now checking for updates...",
        "color": random.randint(0, 0xFFFFFF),
        "footer": {"text": f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
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
    await page.goto(site_config['url'], timeout=60000)
    
    if site_config.get('is_spa'):
        await page.wait_for_load_state('networkidle')
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

    items_data = []
    # 获取列表项
    items = await page.query_selector_all(site_config['item_list_selector'])
    
    for item in items:
        try:
            # 提取标题
            title_el = await item.query_selector(site_config['title_selector'])
            title = await title_el.inner_text() if title_el else "No Title"
            
            # 提取链接
            link_el = await item.query_selector(site_config['link_selector'])
            link = await link_el.get_attribute('href') if link_el else ""
            if link and not link.startswith('http'):
                from urllib.parse import urljoin
                link = urljoin(site_config['url'], link)
            
            # 提取图片
            img_el = await item.query_selector(site_config['image_selector'])
            image = ""
            if img_el:
                if site_config['name'] == 'nshens':
                    # 处理 Vuetify 的 background-image
                    style = await img_el.get_attribute('style')
                    if 'background-image' in style:
                        import re
                        match = re.search(r'url\("(.*?)"\)', style)
                        if match:
                            image = match.group(1)
                else:
                    image = await img_el.get_attribute('src')
            
            if link:
                items_data.append({
                    'site_name': site_config['name'],
                    'title': title.strip(),
                    'link': link,
                    'image': image
                })
        except Exception as e:
            print(f"Error parsing item: {e}")
            
    return items_data

async def main():
    config = load_config()
    db_path = config['database']['db_path']
    init_db(db_path)

    # 发送启动通知
    send_startup_notification(config)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
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
