"""
抓取器抽象基类
"""

from abc import ABC, abstractmethod


class BaseFetcher(ABC):
    """抓取器抽象基类"""

    def __init__(self, tid: str, cookie_file: str = "", max_pages: int = 0):
        """
        Args:
            tid: 帖子ID
            cookie_file: Cookie文件路径（可选）
            max_pages: 最大抓取页数，0表示不限制
        """
        self.tid = tid
        self.cookie_file = cookie_file
        self.max_pages = max_pages

    @abstractmethod
    def fetch_page(self, page_num: int = 1) -> str:
        """抓取单页内容，返回 HTML 字符串"""
        ...

    @abstractmethod
    def fetch_all(self) -> list[str]:
        """抓取所有页面，返回每页 HTML 列表"""
        ...

    @property
    def thread_url(self) -> str:
        """帖子 PC 端 URL"""
        return f"https://tieba.baidu.com/p/{self.tid}"

    @property
    def mobile_url(self) -> str:
        """帖子移动端 URL"""
        return f"https://tieba.baidu.com/mo/q/m?kz={self.tid}"
