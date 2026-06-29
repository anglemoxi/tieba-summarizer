"""
HTTP 抓取器 - 使用 requests + BeautifulSoup
"""

import re
import time
import random
import logging
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    REQUEST_TIMEOUT, MIN_DELAY, MAX_DELAY, MAX_RETRIES,
    HEADERS_MOBILE, HEADERS_DESKTOP,
)
from .base import BaseFetcher

logger = logging.getLogger(__name__)


class HttpFetcher(BaseFetcher):
    """HTTP 抓取器，优先使用移动端接口"""

    def __init__(self, tid: str, cookie_file: str = "", max_pages: int = 0):
        super().__init__(tid, cookie_file, max_pages)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建配置好的 requests.Session"""
        session = requests.Session()

        # 重试策略
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # 默认使用移动端 Headers
        session.headers.update(HEADERS_MOBILE)

        # 加载 Cookie
        if self.cookie_file and Path(self.cookie_file).exists():
            self._load_cookies(session)

        return session

    def _load_cookies(self, session: requests.Session):
        """从文件加载 Cookie，支持 Netscape 和 JSON 格式"""
        try:
            cookie_path = Path(self.cookie_file)
            content = cookie_path.read_text(encoding="utf-8").strip()

            if content.startswith("# Netscape"):
                # Netscape 格式（curl 导出）
                jar = MozillaCookieJar(str(cookie_path))
                jar.load(ignore_discard=True, ignore_expires=True)
                session.cookies.update({c.name: c.value for c in jar})
                logger.info(f"已加载 Netscape Cookie: {cookie_path}")
            elif content.startswith("{"):
                # JSON 格式
                import json
                cookies = json.loads(content)
                if isinstance(cookies, dict):
                    session.cookies.update(cookies)
                elif isinstance(cookies, list):
                    for c in cookies:
                        session.cookies.set(c["name"], c["value"])
                logger.info(f"已加载 JSON Cookie: {cookie_path}")
            else:
                # 简单 name=value 格式，每行一个
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        name, _, value = line.partition("=")
                        session.cookies.set(name.strip(), value.strip())
                logger.info(f"已加载简单格式 Cookie: {cookie_path}")
        except Exception as e:
            logger.warning(f"加载 Cookie 失败: {e}")

    def _random_delay(self):
        """随机延迟，避免被封"""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        time.sleep(delay)

    def fetch_page(self, page_num: int = 1) -> str:
        """
        抓取单页，优先尝试移动端

        Args:
            page_num: 页码（从1开始）

        Returns:
            HTML 字符串

        Raises:
            requests.RequestException: 请求失败
        """
        # 先尝试移动端（响应更小，反爬更松）
        urls_to_try = [
            f"{self.mobile_url}&pn={page_num}",
            f"{self.mobile_url}&pn={page_num * 50}",  # 移动端每页50条
            f"{self.thread_url}?pn={page_num}",
            f"{self.thread_url}?see_lz=1&pn={page_num}",
        ]

        last_error = None
        for url in urls_to_try:
            try:
                self._random_delay()
                resp = self.session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                resp.raise_for_status()

                # 检查是否被拦截
                if self._is_blocked(resp.text):
                    logger.warning(f"页面 {page_num} 疑似被拦截，尝试下一个URL...")
                    continue

                # 检查是否有有效内容
                if len(resp.text) < 500:
                    logger.warning(f"页面 {page_num} 内容过短({len(resp.text)}字节)，尝试下一个URL...")
                    continue

                logger.info(f"成功抓取第 {page_num} 页: {url}")
                return resp.text

            except requests.RequestException as e:
                last_error = e
                logger.warning(f"URL请求失败 ({url}): {e}")
                continue

        raise last_error or RuntimeError(f"所有URL尝试均失败，无法抓取第 {page_num} 页")

    def fetch_all(self) -> list[str]:
        """
        抓取所有页面

        Returns:
            每页的 HTML 字符串列表
        """
        pages = []

        # 先抓第一页，获取总页数
        first_page = self.fetch_page(1)
        pages.append(first_page)

        # 解析总页数
        from parser import TiebaParser
        total_pages = TiebaParser.get_total_pages(first_page)
        logger.info(f"检测到总页数: {total_pages}")

        # 限制最大页数
        if self.max_pages > 0:
            total_pages = min(total_pages, self.max_pages)
            logger.info(f"已限制最大页数为: {total_pages}")

        # 抓取剩余页面
        for page_num in range(2, total_pages + 1):
            try:
                html = self.fetch_page(page_num)
                pages.append(html)
                logger.info(f"进度: {page_num}/{total_pages}")
            except Exception as e:
                logger.error(f"第 {page_num} 页抓取失败: {e}")
                # 继续抓后续页面，不中断
                continue

        return pages

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """检测是否被反爬拦截"""
        block_indicators = [
            "请输入验证码",
            "captcha",
            "verify",
            "antispider",
            "访问太频繁",
            "系统检测到",
            "安全验证",
            "请输入下面",
            "您的IP",
            "被封",
        ]
        html_lower = html.lower()
        for indicator in block_indicators:
            if indicator.lower() in html_lower:
                return True
        return False
