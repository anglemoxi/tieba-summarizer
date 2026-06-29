# 📝 贴吧楼主帖子汇总工具

自动抓取百度贴吧指定帖子的**楼主全部发言**，整理为结构化 Markdown 文件，并可调用 Claude AI 生成内容摘要。

## ✨ 功能

- **只看楼主** — 自动过滤楼主发言，按时间排序
- **三层抓取策略** — JSON API → HTTP 解析 → 浏览器模拟，自动降级
- **AI 摘要** — 对接 Claude API，长帖自动分段摘要后合并
- **反爬对抗** — 随机延迟、自动重试、移动端 UA、Cookie 持久化
- **验证码处理** — 可见浏览器模式，手动过验证后自动保存 Cookie
- **格式化输出** — 按日期分组的时间线 Markdown，适合阅读归档

## 🏗️ 架构

```
tieba-summarizer/
├── main.py              # CLI 入口
├── config.py            # 配置管理
├── parser.py            # HTML/JSON 解析器
├── summarizer.py        # Claude AI 摘要模块
├── writer.py            # Markdown 输出模块
├── fetcher/
│   ├── base.py          # 抓取器抽象基类
│   ├── api_fetcher.py   # JSON API 抓取（首选）
│   ├── http_fetcher.py  # HTTP + BeautifulSoup 抓取
│   └── browser_fetcher.py # Playwright 浏览器抓取（兜底）
└── output/              # 输出目录
```

### 抓取策略

| 优先级 | 策略 | 速度 | 可靠性 | 需要 |
|--------|------|------|--------|------|
| 1 | JSON API | ⚡ 极快 | 高 | 有效 Cookie |
| 2 | HTTP 爬取 | 🔧 中等 | 中 | — |
| 3 | Playwright 浏览器 | 🐌 较慢 | 最高 | Chromium |

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/yourname/tieba-summarizer.git
cd tieba-summarizer
pip install -r requirements.txt
playwright install chromium
```

### 基础用法

```bash
# 抓取帖子 + AI 摘要
python main.py "https://tieba.baidu.com/p/1234567890"

# 只抓取不摘要
python main.py "https://tieba.baidu.com/p/8589589322" --no-summary

# 限制抓取页数
python main.py "https://tieba.baidu.com/p/1234567890" --max-pages 10
```

### 首次使用（过验证码）

如果 API/HTTP 方式被反爬拦截，可以用浏览器模式手动过验证：

```bash
python main.py "https://tieba.baidu.com/p/1234567890" --visible --force-browser
```

验证通过后 Cookie 会自动保存到 `.tieba_cookies.json`，后续可直接用 API 模式。

### 使用 Cookie 文件

```bash
python main.py "https://tieba.baidu.com/p/1234567890" --cookie-file cookies.txt
```

支持三种格式：Netscape（curl导出）、JSON、简单 `name=value`。

## ⚙️ 配置

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
```

```ini
# Claude API Key（用于AI摘要，可选）
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 模型选择
ANTHROPIC_MODEL=claude-sonnet-4-6
```

可调参数见 `config.py`：请求延迟、超时、重试次数等。

## 📦 依赖

| 包 | 用途 |
|----|------|
| `requests` | HTTP 请求 |
| `beautifulsoup4` + `lxml` | HTML 解析 |
| `playwright` | 浏览器自动化（可选兜底） |
| `anthropic` | Claude API 摘要 |
| `python-dotenv` | 环境变量 |

## 📄 输出示例

生成的 Markdown 文件包含：

- 📌 帖子信息表（链接、贴吧、楼主、发言数）
- 🤖 AI 摘要（主题概述、关键时间线、内容要点、总结）
- 📋 按日期分组的楼主发言时间线

## ⚠️ 注意事项

- 请遵守百度贴吧的 [robots.txt](https://tieba.baidu.com/robots.txt) 和服务条款
- 内置随机延迟避免请求过快被封
- 抓取内容仅限个人学习归档使用
- Cookie 文件 `.tieba_cookies.json` 包含登录态，**切勿上传公开**

## 📜 License

MIT
