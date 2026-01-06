# NSFW Site Monitor

![Version](https://img.shields.io/badge/version-0.1.2-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

一个基于 Playwright 和 SQLite 的自动化网站内容采集与 Discord 推送系统。

## 功能特点

- **多站点支持**: 通过 `config.yaml` 灵活配置不同站点的采集规则。
- **持久化记录**: 使用 SQLite 数据库存储已推送内容，防止重复推送。
- **动态解析**: 完美支持单页应用 (SPA) 和动态加载内容。
- **美观推送**: 推送包含标题、原文链接及预览图的 Discord Embed。
- **CI/CD 集成**: 适配 GitHub Actions，支持定时运行与自动版本管理。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 本地配置
在 `config.yaml` 中配置目标站点。

### 3. 配置 GitHub Secrets
在 GitHub 仓库中添加以下环境变量：
- `DISCORD_WEBHOOK_URL`: 您的 Discord Webhook 地址。

## 目录结构
- `monitor.py`: 主程序
- `config.yaml`: 站点配置文件
- `data.db`: 推送数据存储
- `.github/workflows/`: 自动化工作流

## 更新日志
请参阅 [CHANGELOG.md](./CHANGELOG.md)。

## License
MIT
