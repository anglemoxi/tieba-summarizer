"""
API 抓取器 - 直接调用贴吧内部 JSON API
比 HTML 解析更快速、更可靠
"""

import json
import logging
import re
import time
import random
from pathlib import Path

import requests

from config import REQUEST_TIMEOUT, MIN_DELAY, MAX_DELAY, MAX_RETRIES
from .base import BaseFetcher

logger = logging.getLogger(__name__)

COOKIE_FILE = Path(__file__).parent.parent / ".tieba_cookies.json"


class ApiFetcher(BaseFetcher):
    """基于贴吧 JSON API 的抓取器"""

    API_URL = "https://tieba.baidu.com/c/f/pb/page_pc"

    def __init__(self, tid: str, cookie_file: str = "", max_pages: int = 0):
        super().__init__(tid, cookie_file, max_pages)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"https://tieba.baidu.com/p/{self.tid}",
        })

        # 加载 Cookie
        self._load_cookies(session)

        return session

    def _load_cookies(self, session: requests.Session):
        """加载 Cookie"""
        # 优先使用 .tieba_cookies.json
        cookie_path = Path(self.cookie_file) if self.cookie_file else COOKIE_FILE

        if cookie_path.exists():
            try:
                with open(cookie_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)

                for c in cookies:
                    session.cookies.set(
                        c.get("name", ""),
                        c.get("value", ""),
                        domain=c.get("domain", ""),
                        path=c.get("path", "/"),
                    )
                logger.info(f"已加载 {len(cookies)} 条 API Cookie: {cookie_path}")
            except Exception as e:
                logger.warning(f"API Cookie 加载失败: {e}")

    def fetch_page(self, page_num: int = 1) -> dict:
        """
        调用 API 抓取单页，返回解析后的 JSON 数据

        Args:
            page_num: 页码（从1开始）

        Returns:
            API 响应的 JSON 字典
        """
        params = {
            "tid": self.tid,
            "pn": page_num,
            "see_lz": "1",  # 只看楼主
            "_": str(int(time.time() * 1000)),
        }

        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    time.sleep(random.uniform(2, 5))

                resp = self.session.get(
                    self.API_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()

                data = resp.json()

                # 检查 API 错误
                error_code = data.get("error_code", "")
                error_msg = data.get("error_msg", "")
                if error_code and str(error_code) != "0":
                    logger.error(f"API 错误 [{error_code}]: {error_msg}")
                    if "验证" in str(error_msg) or "verify" in str(error_msg).lower():
                        raise RuntimeError("需要重新验证，请使用 --visible --force-browser 重新获取 Cookie")
                    raise RuntimeError(f"API 返回错误: {error_msg}")

                return data

            except requests.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"API 请求重试 {attempt + 1}/{MAX_RETRIES}: {e}")
                else:
                    raise
            except json.JSONDecodeError as e:
                logger.error(f"API 返回非 JSON 数据: {e}")
                raise

    @staticmethod
    def parse_post(post_data: dict, user_map: dict) -> dict | None:
        """解析单条帖子数据"""
        if not post_data:
            return None

        # 解析作者
        author_id = post_data.get("author_id", "")
        author = user_map.get(str(author_id), "")

        # 解析内容（可能是字符串或列表）
        content_raw = post_data.get("content", "")
        content = ApiFetcher._parse_content(content_raw)

        # 解析时间
        time_val = post_data.get("time", 0)
        if isinstance(time_val, (int, float)) and time_val > 1000000000:
            from datetime import datetime
            time_str = datetime.fromtimestamp(time_val).strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(time_val)

        return {
            "author": author,
            "author_id": str(author_id),
            "content": content,
            "floor": post_data.get("floor", 0),
            "time_str": time_str,
            "timestamp": time_val,
            "post_id": post_data.get("id", ""),
        }

    @staticmethod
    def _parse_content(content) -> str:
        """解析帖子内容（支持字符串和列表格式）"""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for seg in content:
                if isinstance(seg, dict):
                    seg_type = seg.get("type", 0)
                    text = seg.get("text", "")

                    if seg_type == 0:  # 普通文本
                        parts.append(text)
                    elif seg_type == 2:  # 表情
                        emoji_text = seg.get("text", "")
                        if emoji_text:
                            parts.append(f"[{emoji_text}]")
                        else:
                            parts.append("[表情]")
                    elif seg_type == 3:  # 图片
                        parts.append("[图片]")
                    elif seg_type == 4:  # @ 提及
                        parts.append(f"@{text}")
                    elif seg_type == 1:  # 链接
                        link = seg.get("link", text)
                        parts.append(f"{text}({link})")
                    else:
                        parts.append(text)
                elif isinstance(seg, str):
                    parts.append(seg)

            return "".join(parts)

        return str(content)

    def fetch_all(self) -> list[dict]:
        """
        抓取所有页面的 API 数据

        Returns:
            每页的 JSON 数据列表
        """
        all_data = []

        # 抓第一页
        logger.info("通过 API 抓取第 1 页...")
        first_page = self.fetch_page(1)
        all_data.append(first_page)

        # 获取总页数
        total_pages = first_page.get("page", {}).get("total_page", 1)
        logger.info(f"API 返回总页数: {total_pages}")

        if self.max_pages > 0:
            total_pages = min(total_pages, self.max_pages)
            logger.info(f"已限制最大页数为: {total_pages}")

        # 抓剩余页
        for page_num in range(2, total_pages + 1):
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            try:
                data = self.fetch_page(page_num)
                all_data.append(data)
                logger.info(f"API 进度: {page_num}/{total_pages}")
            except Exception as e:
                logger.error(f"第 {page_num} 页 API 抓取失败: {e}")
                continue

        return all_data

    @staticmethod
    def extract_thread_info(api_data_list: list[dict]) -> dict:
        """从 API 数据中提取帖子信息"""
        if not api_data_list:
            return {}

        first = api_data_list[0]

        # 帖子标题
        thread = first.get("thread", {})
        title = thread.get("title", "")

        # 贴吧名
        forum = first.get("forum", {})
        forum_name = forum.get("name", "")

        # 构建用户映射（user_id -> user_name）
        all_users = {}
        for data in api_data_list:
            for user in data.get("user_list", []):
                uid = str(user.get("id", ""))
                uname = user.get("user_name", user.get("name", ""))
                if uid and uname:
                    all_users[uid] = uname

        # 楼主：thread.author 或 thread.author_id 查 user_list
        author = ""
        author_id = ""
        if isinstance(thread.get("author"), dict):
            author = thread["author"].get("user_name", thread["author"].get("name", ""))
            author_id = str(thread["author"].get("id", ""))
        elif "author_id" in thread:
            author_id = str(thread["author_id"])
            author = all_users.get(author_id, "")

        if not author and thread.get("author"):
            author = str(thread["author"])

        # 解析所有帖子
        all_posts = []
        for data in api_data_list:
            for post_data in data.get("post_list", []):
                post = ApiFetcher.parse_post(post_data, all_users)
                if post:
                    all_posts.append(post)

        # 过滤楼主帖子
        owner_posts = []
        for p in all_posts:
            if p["author"] == author or p["author_id"] == author_id:
                owner_posts.append(p)

        # 如果没有通过 author 匹配，用 floor=1 作为楼主
        if not owner_posts and all_posts:
            author = all_posts[0]["author"]
            author_id = all_posts[0]["author_id"]
            owner_posts = [p for p in all_posts if p["author_id"] == author_id]

        # 时间排序
        owner_posts.sort(key=lambda p: p.get("timestamp", 0) or 0)

        return {
            "title": title,
            "forum_name": forum_name,
            "author": author,
            "author_id": author_id,
            "total_pages": len(api_data_list),
            "total_posts": len(owner_posts),
            "posts": owner_posts,
        }
