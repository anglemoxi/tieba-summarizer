"""
帖子解析模块 - HTML解析、楼主识别、时间排序
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup, Tag


@dataclass
class Post:
    """单条帖子回复"""
    author: str           # 作者名
    content: str          # 纯文本内容
    floor: int            # 楼层号
    time_str: str         # 原始时间字符串
    timestamp: Optional[datetime] = None  # 解析后的时间对象

    def to_dict(self) -> dict:
        return {
            "author": self.author,
            "content": self.content,
            "floor": self.floor,
            "time_str": self.time_str,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class ThreadInfo:
    """帖子基本信息"""
    title: str = ""
    tid: str = ""
    author: str = ""        # 楼主名
    total_pages: int = 1
    total_posts: int = 0
    forum_name: str = ""    # 贴吧名
    posts: list = field(default_factory=list)  # 楼主的所有发言


class TiebaParser:
    """贴吧页面解析器，支持 PC 端和移动端"""

    # 常见时间格式
    TIME_PATTERNS = [
        # "2024-01-15 14:30"
        (r"(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})", "%Y-%m-%d %H:%M"),
        # "2024-01-15 14:30:00"
        (r"(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}:\d{2})", "%Y-%m-%d %H:%M:%S"),
        # "2024年01月15日 14:30"
        (r"(\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2})", "%Y年%m月%d日 %H:%M"),
        # "01月15日 14:30"
        (r"(\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2})", "%m月%d日 %H:%M"),
    ]

    @staticmethod
    def extract_tid(url: str) -> str:
        """从 URL 中提取帖子 ID"""
        from config import TIEBA_PATTERNS

        for pattern in TIEBA_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError(f"无法从 URL 中解析帖子ID: {url}")

    @classmethod
    def parse_time(cls, time_str: str) -> Optional[datetime]:
        """尝试解析各种格式的时间字符串"""
        if not time_str:
            return None
        time_str = time_str.strip()
        for pattern, fmt in cls.TIME_PATTERNS:
            match = re.search(pattern, time_str)
            if match:
                try:
                    parsed = datetime.strptime(match.group(1), fmt)
                    # 如果没有年份，用当前年份补充
                    if parsed.year == 1900:
                        parsed = parsed.replace(year=datetime.now().year)
                    return parsed
                except ValueError:
                    continue
        return None

    @classmethod
    def parse_pc_page(cls, html: str) -> list[Post]:
        """解析 PC 端帖子页面，提取所有回复"""
        soup = BeautifulSoup(html, "lxml")
        posts = []

        # PC端帖子容器: div.l_post
        post_containers = soup.select("div.l_post")
        if not post_containers:
            # 备用选择器
            post_containers = soup.select("[data-field]")

        for container in post_containers:
            post = cls._parse_pc_post(container)
            if post:
                posts.append(post)

        return posts

    @classmethod
    def _parse_pc_post(cls, container: Tag) -> Optional[Post]:
        """解析 PC 端单条回复"""
        try:
            # 提取 data-field 属性（JSON 格式的元数据）
            data_field = container.get("data-field", "")
            if data_field:
                import json
                try:
                    field = json.loads(data_field)
                    author = field.get("author", {}).get("user_name", "")
                    content_text = field.get("content", {}).get("content", "")
                except json.JSONDecodeError:
                    author = ""
                    content_text = ""
            else:
                # 回退到 DOM 解析
                author_el = container.select_one(".d_name a, .p_author_name")
                author = author_el.get_text(strip=True) if author_el else ""

                content_el = container.select_one(".d_post_content, .j_d_post_content")
                content_text = cls._clean_content(content_el) if content_el else ""

            if not author:
                return None

            # 提取楼层号
            floor_el = container.select_one(".tail-info, .p_tail")
            floor_num = 0
            if floor_el:
                floor_text = floor_el.get_text(strip=True)
                floor_match = re.search(r"(\d+)楼", floor_text)
                if floor_match:
                    floor_num = int(floor_match.group(1))

            # 提取时间
            time_el = container.select_one(".tail-info:last-child, .p_tail")
            time_str = ""
            # 更精确的时间选择器
            for el in container.select(".tail-info, .p_tail"):
                text = el.get_text(strip=True)
                if re.search(r"\d{1,2}:\d{2}", text):
                    time_str = text
                    break

            content_text = content_text or cls._clean_content(container)

            return Post(
                author=author,
                content=content_text.strip(),
                floor=floor_num,
                time_str=time_str,
                timestamp=cls.parse_time(time_str),
            )
        except Exception:
            return None

    @classmethod
    def parse_mobile_page(cls, html: str) -> list[Post]:
        """解析移动端帖子页面"""
        soup = BeautifulSoup(html, "lxml")
        posts = []

        # 移动端回复容器
        post_containers = soup.select(".lzljf, .i, div[class*='lzljf']")
        if not post_containers:
            post_containers = soup.select("div.i")

        for container in post_containers:
            post = cls._parse_mobile_post(container)
            if post:
                posts.append(post)

        return posts

    @classmethod
    def _parse_mobile_post(cls, container: Tag) -> Optional[Post]:
        """解析移动端单条回复"""
        try:
            # 作者
            author_el = container.select_one(".d_name a")
            author = author_el.get_text(strip=True) if author_el else ""

            if not author:
                # 尝试其他选择器
                user_el = container.select_one("[class*='user']")
                author = user_el.get_text(strip=True) if user_el else ""

            # 内容
            content_el = container.select_one(".d_post_content, [class*='content']")
            content_text = cls._clean_content(content_el) if content_el else ""

            # 楼层
            floor_el = container.select_one("[class*='tail']")
            floor_num = 0
            if floor_el:
                floor_match = re.search(r"(\d+)楼", floor_el.get_text(strip=True))
                if floor_match:
                    floor_num = int(floor_match.group(1))

            # 时间
            time_str = ""
            time_pattern = re.compile(r"\d{4}[-年]\d{1,2}[-月]\d{1,2}日?\s*\d{1,2}:\d{2}")
            for el in container.select("span, .tail-info"):
                text = el.get_text(strip=True)
                if time_pattern.search(text):
                    time_str = text
                    break

            if not author:
                return None

            return Post(
                author=author,
                content=content_text.strip(),
                floor=floor_num,
                time_str=time_str,
                timestamp=cls.parse_time(time_str),
            )
        except Exception:
            return None

    @staticmethod
    def _clean_content(element: Tag) -> str:
        """清理回复内容，去除HTML标签，保留文本"""
        if element is None:
            return ""

        # 移除引用块
        for quote in element.select(".d_quote, blockquote, .quote_content"):
            quote.decompose()

        # 替换图片为 [图片]
        for img in element.select("img"):
            alt = img.get("alt", "")
            if alt:
                img.replace_with(f"[图片: {alt}]")
            else:
                img.replace_with("[图片]")

        # 替换换行标签
        for br in element.select("br"):
            br.replace_with("\n")

        # 替换表情
        for emoji in element.select(".d_emoji, img[class*='emoji'], img[class*='face']"):
            emoji.replace_with(f"[表情]")

        text = element.get_text(separator="\n", strip=True)
        # 压缩多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    @classmethod
    def get_total_pages(cls, html: str) -> int:
        """从页面中提取总页数（优先检查 API 数据）"""
        soup = BeautifulSoup(html, "lxml")

        # 优先从 API 数据获取
        api_tag = soup.find("script", id=re.compile(r"__API_DATA_\d+__"))
        if api_tag:
            try:
                data = json.loads(api_tag.get_text(strip=True))
                total = data.get("page", {}).get("total_page", 0)
                if total > 0:
                    return total
            except (json.JSONDecodeError, Exception):
                pass

        # PC端: <span class="red">2</span> 在分页区域
        red_span = soup.select_one(".l_reply_num .red, .thread_theme_5 .red")
        if red_span:
            try:
                # 第二个 red 通常是总页数
                red_spans = soup.select(".red")
                for span in red_spans:
                    text = span.get_text(strip=True)
                    if text.isdigit():
                        num = int(text)
                        if num > 1:
                            return num
            except (ValueError, IndexError):
                pass

        # 移动端: 从分页链接推断
        page_links = soup.select("a[href*='pn=']")
        max_page = 1
        for link in page_links:
            match = re.search(r"pn=(\d+)", link.get("href", ""))
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)

        # 检查最后一页链接
        last_page = soup.select_one("a:contains('尾页'), a:contains('最后')")
        if last_page:
            match = re.search(r"pn=(\d+)", last_page.get("href", ""))
            if match:
                return int(match.group(1))

        return max_page

    @classmethod
    def get_thread_title(cls, html: str) -> str:
        """提取帖子标题"""
        soup = BeautifulSoup(html, "lxml")

        # PC端标题
        title_el = soup.select_one("h1.core_title_txt, .thread_theme_5 h1, h3.core_title_txt")
        if title_el:
            return title_el.get_text(strip=True)

        # 移动端标题
        title_el = soup.select_one(".thread_title, h1")
        if title_el:
            return title_el.get_text(strip=True)

        # <title> 标签
        title_tag = soup.select_one("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # 去掉后缀 "_百度贴吧"
            # 去掉后缀如 "xxx_百度贴吧" 或 "xxx【某某吧】_百度贴吧"
            title_text = re.sub(r"[_\-].*百度贴吧.*$", "", title_text).strip()
            # 也去掉 "xxx【某某吧】" 这种
            title_text = re.sub(r"【[^】]*吧】.*$", "", title_text).strip()
            return title_text

        return "未知标题"

    @classmethod
    def get_forum_name(cls, html: str) -> str:
        """提取贴吧名称"""
        soup = BeautifulSoup(html, "lxml")
        forum_el = soup.select_one(".card_title a, .ba_name a, a[class*='ba_name']")
        if forum_el:
            return forum_el.get_text(strip=True)
        return ""

    @classmethod
    def filter_author_posts(cls, posts: list[Post], author_name: str) -> list[Post]:
        """只保留指定作者的帖子"""
        return [p for p in posts if p.author == author_name]

    @classmethod
    def sort_by_time(cls, posts: list[Post]) -> list[Post]:
        """按时间排序（有 timestamp 的排前面，无 timestamp 的保持原序放后面）"""
        with_ts = [p for p in posts if p.timestamp is not None]
        without_ts = [p for p in posts if p.timestamp is None]

        with_ts.sort(key=lambda p: p.timestamp)
        # 没有时间戳的保持原有顺序（通常是原始楼层顺序）
        return with_ts + without_ts

    @classmethod
    def parse_from_api_data(cls, html: str) -> list[Post]:
        """从浏览器拦截的 API JSON 数据中提取帖子"""
        soup = BeautifulSoup(html, "lxml")
        posts = []

        for tag in soup.find_all("script", id=re.compile(r"__API_DATA_\d+__")):
            try:
                data = json.loads(tag.get_text(strip=True))
                if not isinstance(data, dict):
                    continue

                # 构建 user_id -> user_name 映射
                user_map = {}
                for user in data.get("user_list", []):
                    uid = str(user.get("id", ""))
                    uname = user.get("user_name", user.get("name", ""))
                    if uid and uname:
                        user_map[uid] = uname

                # 提取帖子列表
                post_list = data.get("post_list", [])
                for item in post_list:
                    if not isinstance(item, dict):
                        continue

                    # 作者
                    author_id = str(item.get("author_id", ""))
                    author = user_map.get(author_id, "")

                    # 内容
                    content = cls._parse_api_content(item.get("content", ""))

                    # 时间
                    time_val = item.get("time", 0)
                    if isinstance(time_val, (int, float)) and time_val > 1000000000:
                        from datetime import datetime as dt
                        time_str = dt.fromtimestamp(time_val).strftime("%Y-%m-%d %H:%M:%S")
                        timestamp = dt.fromtimestamp(time_val)
                    else:
                        time_str = str(time_val)
                        timestamp = cls.parse_time(time_str)

                    if author:
                        posts.append(Post(
                            author=author,
                            content=content.strip(),
                            floor=item.get("floor", 0),
                            time_str=time_str,
                            timestamp=timestamp,
                        ))

                logger = __import__("logging").getLogger(__name__)
                logger.info(f"从 API 数据中解析到 {len(posts)} 条帖子")
                break  # 只用第一份 API 数据

            except (json.JSONDecodeError, Exception) as e:
                logger = __import__("logging").getLogger(__name__)
                logger.debug(f"API 数据解析失败: {e}")
                continue

        return posts

    @staticmethod
    def _parse_api_content(content) -> str:
        """解析 API 返回的 content 字段（支持字符串和列表格式）"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for seg in content:
                if isinstance(seg, dict):
                    seg_type = seg.get("type", 0)
                    text = seg.get("text", "")
                    if seg_type == 0:
                        parts.append(text)
                    elif seg_type == 2:
                        parts.append(f"[{text}]" if text else "[表情]")
                    elif seg_type == 3:
                        parts.append("[图片]")
                    elif seg_type == 4:
                        parts.append(f"@{text}")
                    elif seg_type == 1:
                        link = seg.get("link", text)
                        parts.append(f"{text}({link})")
                    else:
                        parts.append(text)
                elif isinstance(seg, str):
                    parts.append(seg)
            return "".join(parts)
        return str(content)

    @classmethod
    def parse_from_extracted_data(cls, html: str) -> list[Post]:
        """从浏览器注入的 __EXTRACTED_POSTS__ script 标签提取数据"""
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", id="__EXTRACTED_POSTS__")
        if not tag:
            return []

        try:
            data = json.loads(tag.get_text(strip=True))
            posts = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                author = item.get("author", "")
                content = item.get("content", "")
                floor = item.get("floor", 0)
                time_str = item.get("time_str", "")

                # 也可能数据在 data 字段里
                inner = item.get("data", {})
                if not author and isinstance(inner, dict):
                    author = inner.get("author", {}).get("user_name", "")
                if not content and isinstance(inner, dict):
                    content = inner.get("content", {}).get("content", "")
                if not time_str and isinstance(inner, dict):
                    time_str = str(inner.get("time", ""))

                # 清理内容中的 HTML 标签
                from bs4 import BeautifulSoup as BS
                content = BS(content, "html.parser").get_text() if content else ""

                if author:
                    posts.append(Post(
                        author=author,
                        content=content.strip(),
                        floor=int(floor) if floor else 0,
                        time_str=str(time_str),
                        timestamp=cls.parse_time(str(time_str)),
                    ))

            logger = __import__("logging").getLogger(__name__)
            logger.info(f"从提取数据中解析到 {len(posts)} 条帖子")
            return posts
        except (json.JSONDecodeError, Exception) as e:
            logger = __import__("logging").getLogger(__name__)
            logger.debug(f"解析提取数据失败: {e}")
            return []

    @classmethod
    def parse_from_script_data(cls, html: str) -> list[Post]:
        """
        从 <script> 标签中提取嵌入的 JSON 帖子数据
        现代贴吧使用 React/Vue 渲染，数据通常嵌在 script 中
        """
        soup = BeautifulSoup(html, "lxml")
        posts = []

        for script in soup.find_all("script"):
            text = script.get_text(strip=True)
            if not text:
                continue

            # 尝试多种数据嵌入模式
            try:
                posts = cls._try_extract_posts_from_json(text)
                if posts:
                    logger = __import__("logging").getLogger(__name__)
                    logger.info(f"从 script 数据中提取到 {len(posts)} 条帖子")
                    return posts
            except Exception:
                continue

        return posts

    @classmethod
    def _try_extract_posts_from_json(cls, text: str) -> list[Post]:
        """尝试从 JS 文本中提取帖子 JSON 数据"""
        posts = []

        # 模式1: window.__INITIAL_STATE__ = {...}
        match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.+?});", text, re.DOTALL)
        if not match:
            # 模式2: __NEXT_DATA__ = ...
            match = re.search(r"__NEXT_DATA__\s*=\s*({.+?});", text, re.DOTALL)
        if not match:
            # 模式3: 查找包含 post_list 的大 JSON 对象
            match = re.search(r'(?s)"post_list"\s*:\s*\[.*?\]', text)
            if match:
                # 扩展匹配到完整的 JSON
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 200)
                # 尝试匹配更大的上下文
                for m in re.finditer(r'{.*?"post_list"\s*:\s*(\[.*?\]).*?}', text, re.DOTALL):
                    try:
                        raw_posts = json.loads(m.group(1))
                        return cls._json_to_posts(raw_posts)
                    except (json.JSONDecodeError, KeyError):
                        continue
                return []

        if match:
            try:
                data = json.loads(match.group(1))
                # 递归搜索帖子列表
                post_list = cls._find_post_list(data)
                if post_list:
                    return cls._json_to_posts(post_list)
            except json.JSONDecodeError:
                pass

        # 模式4: 通用搜索 - 查找所有看起来像帖子数据的 JSON 数组
        if not posts:
            posts = cls._scan_for_post_data(text)

        return posts

    @classmethod
    def _find_post_list(cls, data, max_depth: int = 5) -> list | None:
        """递归搜索 JSON 数据中的帖子列表"""
        if max_depth <= 0:
            return None

        if isinstance(data, dict):
            # 检查是否是帖子数据
            for key in ["post_list", "reply_list", "posts", "list", "data"]:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    item = data[key][0]
                    if isinstance(item, dict) and ("content" in item or "author" in item):
                        return data[key]

            # 递归搜索子对象
            for value in data.values():
                result = cls._find_post_list(value, max_depth - 1)
                if result:
                    return result

        elif isinstance(data, list) and len(data) > 0:
            # 检查列表第一项是否像帖子
            item = data[0]
            if isinstance(item, dict) and "content" in item:
                return data

        return None

    @classmethod
    def _json_to_posts(cls, post_list: list) -> list[Post]:
        """将 JSON 帖子数据转换为 Post 对象列表"""
        posts = []
        for item in post_list:
            if not isinstance(item, dict):
                continue

            # 提取作者（支持多种字段名）
            author = ""
            for key in ["author", "user_name", "name", "userName", "uname"]:
                if key in item and item[key]:
                    author = str(item[key])
                    break
            if not author:
                # 可能有嵌套的 author 对象
                author_obj = item.get("author", {})
                if isinstance(author_obj, dict):
                    author = str(
                        author_obj.get("user_name", "")
                        or author_obj.get("name", "")
                        or author_obj.get("uname", "")
                    )

            # 提取内容
            content = ""
            for key in ["content", "text", "message", "body"]:
                if key in item and item[key]:
                    content = str(item[key])
                    break

            # 提取楼层
            floor = 0
            for key in ["floor", "floor_num", "post_no", "postNo"]:
                if key in item and item[key] is not None:
                    try:
                        floor = int(item[key])
                    except (ValueError, TypeError):
                        pass
                    break

            # 提取时间
            time_str = ""
            for key in ["time", "create_time", "reply_time", "post_time"]:
                if key in item and item[key]:
                    time_str = str(item[key])
                    break

            if author:
                posts.append(Post(
                    author=author,
                    content=cls._clean_json_content(content),
                    floor=floor,
                    time_str=time_str,
                    timestamp=cls.parse_time(time_str),
                ))

        return posts

    @staticmethod
    def _clean_json_content(text: str) -> str:
        """清理 JSON 中的 HTML 标签"""
        if not text:
            return ""
        # 去除常见 HTML 标签
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#\d+;", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def _scan_for_post_data(cls, text: str) -> list[Post]:
        """通用扫描 - 在 JS 文本中找所有可能的帖子信息"""
        posts = []
        # 用正则找 author/content 配对
        # 匹配 "author": "xxx" ... "content": "xxx" 模式
        pattern = (
            r'"user_name"\s*:\s*"([^"]+)".*?'
            r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"'
        )
        for match in re.finditer(pattern, text, re.DOTALL):
            author = match.group(1)
            content = cls._clean_json_content(match.group(2))
            if author and content:
                posts.append(Post(
                    author=author,
                    content=content,
                    floor=0,
                    time_str="",
                ))

        # 去重
        seen = set()
        unique = []
        for p in posts:
            key = (p.author, p.content[:100])
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return unique

    @classmethod
    def parse(cls, html: str) -> tuple[list[Post], dict]:
        """
        解析帖子页面，返回 (帖子列表, 元信息)
        自动尝试：PC端 → 移动端 → script数据提取
        """
        posts = cls.parse_from_api_data(html)
        if not posts:
            posts = cls.parse_from_extracted_data(html)
        if not posts:
            posts = cls.parse_pc_page(html)
        if not posts:
            posts = cls.parse_mobile_page(html)
        if not posts:
            posts = cls.parse_from_script_data(html)

        # 尝试从 API 数据获取贴吧名
        forum_name = cls.get_forum_name(html)
        if not forum_name:
            soup = BeautifulSoup(html, "lxml")
            api_tag = soup.find("script", id=re.compile(r"__API_DATA_\d+__"))
            if api_tag:
                try:
                    data = json.loads(api_tag.get_text(strip=True))
                    forum_name = data.get("forum", {}).get("name", "")
                except (json.JSONDecodeError, Exception):
                    pass

        meta = {
            "title": cls.get_thread_title(html),
            "total_pages": cls.get_total_pages(html),
            "forum_name": forum_name,
        }

        return posts, meta
