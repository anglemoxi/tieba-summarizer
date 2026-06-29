"""
配置管理模块 - 环境变量加载、常量定义
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv(Path(__file__).parent / ".env")

# --- API 配置 ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# --- 抓取配置 ---
REQUEST_TIMEOUT = 30  # HTTP 请求超时（秒）
MIN_DELAY = 1.0       # 请求最小间隔（秒）
MAX_DELAY = 3.0       # 请求最大间隔（秒）
MAX_RETRIES = 3       # 最大重试次数
DEFAULT_MAX_PAGES = 0  # 默认最大页数，0 表示不限制

# --- 浏览器回退配置 ---
BROWSER_HEADLESS = True       # Playwright 默认无头模式
BROWSER_WAIT_TIME = 3         # 页面加载等待时间（秒）
BROWSER_SCROLL_DELAY = 1.5    # 滚动间隔（秒）

# --- 输出配置 ---
DEFAULT_OUTPUT_DIR = Path.cwd() / "output"

# --- HTTP Headers ---
HEADERS_MOBILE = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

HEADERS_DESKTOP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# --- 贴吧 URL 模式 ---
TIEBA_PATTERNS = [
    # PC端: https://tieba.baidu.com/p/1234567890
    r"tieba\.baidu\.com/p/(\d+)",
    # 移动端: https://tieba.baidu.com/mo/q/...&kz=1234567890
    r"tieba\.baidu\.com/.*[?&]kz=(\d+)",
    # 带see_lz的: https://tieba.baidu.com/p/1234567890?see_lz=1
    r"tieba\.baidu\.com/p/(\d+)\?.*see_lz",
]
