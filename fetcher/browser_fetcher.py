"""
浏览器回退抓取器 - 使用 Playwright 模拟真实浏览器
当 HTTP 方式被反爬拦截时自动切换到此方案
支持可见模式手动过验证码
"""

import json
import logging
import re
import time
from pathlib import Path

from .base import BaseFetcher
from config import BROWSER_WAIT_TIME, BROWSER_SCROLL_DELAY, MIN_DELAY, MAX_DELAY

logger = logging.getLogger(__name__)

COOKIE_FILE = Path(__file__).parent.parent / ".tieba_cookies.json"


class BrowserFetcher(BaseFetcher):
    """Playwright 浏览器抓取器"""

    def __init__(self, tid: str, max_pages: int = 0, headless: bool = False):
        """
        Args:
            tid: 帖子ID
            max_pages: 最大页数
            headless: 是否无头模式。首次使用建议 False，手动过验证后保存 Cookie
        """
        super().__init__(tid, "", max_pages)
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None

    def _get_playwright(self):
        """延迟导入 Playwright"""
        try:
            from playwright.sync_api import sync_playwright
            return sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright 未安装。请运行:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

    def _init_browser(self):
        """初始化浏览器，加载已保存的 Cookie"""
        if self._browser is not None:
            return

        sync_playwright = self._get_playwright()
        self._playwright = sync_playwright().start()

        # 尝试加载已保存的 cookies
        saved_cookies = self._load_saved_cookies()

        if saved_cookies:
            logger.info("使用已保存的 Cookie 创建浏览器上下文")
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(Path(__file__).parent.parent / ".browser_data"),
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
            )
            self._context.add_cookies(saved_cookies)
            self._browser = self._context
        else:
            logger.info("无已保存 Cookie，使用普通模式启动")
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            self._context = self._browser

        logger.info(
            "浏览器已启动 (Chromium, headless=%s)%s",
            self.headless,
            " [首次使用请手动过验证]" if not saved_cookies and not self.headless else "",
        )

    def _load_saved_cookies(self) -> list:
        """加载已保存的 Cookie"""
        if COOKIE_FILE.exists():
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                logger.info(f"已加载 {len(cookies)} 条 Cookie: {COOKIE_FILE}")
                return cookies
            except Exception as e:
                logger.warning(f"Cookie 加载失败: {e}")
        return []

    def _save_cookies(self):
        """保存 Cookie 到文件"""
        try:
            cookies = None

            # 尝试多种方式获取 cookies
            if hasattr(self._context, "cookies") and callable(self._context.cookies):
                cookies = self._context.cookies()
            elif hasattr(self._browser, "contexts"):
                for ctx in self._browser.contexts:
                    cookies = ctx.cookies()
                    break
            elif hasattr(self._context, "pages"):
                for p in self._context.pages:
                    cookies = p.context.cookies()
                    break

            if not cookies:
                logger.debug("无法获取 Cookie（可能浏览器已关闭）")
                return

            if cookies:
                COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存 {len(cookies)} 条 Cookie: {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"Cookie 保存失败: {e}")

    def _close_browser(self):
        """关闭浏览器"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("浏览器已关闭")

    def _wait_for_verification(self, page) -> bool:
        """
        等待用户完成验证码。
        检测验证页面并等待用户手动完成。
        返回 True 表示验证通过，False 表示超时或失败。
        """
        max_wait = 120  # 最多等 2 分钟

        # 检查是否在验证页面
        title = page.title()
        if "验证" not in title and "安全" not in title:
            # 没有验证页，直接返回
            # 但还是要等页面内容加载
            page.wait_for_timeout(BROWSER_WAIT_TIME * 1000)
            return True

        if self.headless:
            logger.error(
                "检测到验证码，但当前为无头模式无法手动操作。\n"
                "请使用 --visible 参数运行以打开可见浏览器手动过验证。"
            )
            return False

        logger.warning("=" * 50)
        logger.warning("检测到百度安全验证！")
        logger.warning("请在打开的浏览器窗口中完成滑动拼图或扫码验证。")
        logger.warning(f"最多等待 {max_wait} 秒...")
        logger.warning("=" * 50)

        # 等待页面 title 改变（验证通过后会跳转）
        for i in range(max_wait):
            try:
                current_title = page.title()
                if "验证" not in current_title and "安全" not in current_title:
                    logger.info("验证通过！页面已加载。")
                    page.wait_for_timeout(BROWSER_WAIT_TIME * 1000)
                    return True

                # 检查是否有帖子内容加载
                post_els = page.query_selector_all(
                    "div.l_post, .d_post_content, article, [data-field]"
                )
                if post_els and len(post_els) > 0:
                    logger.info("检测到帖子内容，验证已通过。")
                    page.wait_for_timeout(2000)
                    return True

                time.sleep(1)
                if i % 10 == 9:
                    logger.info(f"  等待中... ({i + 1}/{max_wait}秒)")
            except Exception:
                time.sleep(1)

        logger.warning("等待超时，尝试继续抓取...")
        return False

    def _is_verification_page(self, page) -> bool:
        """检查当前是否在验证页面"""
        try:
            title = page.title()
            if "验证" in title or "安全验证" in title:
                return True

            # 检查验证元素
            text = page.content().lower()
            indicators = ["请输入验证码", "滑动拼图", "安全验证", "captcha", "请向右滑动"]
            count = sum(1 for i in indicators if i in text)
            return count >= 2
        except Exception:
            return False

    def fetch_page(self, page_num: int = 1) -> str:
        """
        使用浏览器抓取单页，同时拦截 API JSON 响应

        Returns:
            页面 HTML 字符串（内嵌拦截到的 JSON 数据）
        """
        self._init_browser()

        api_responses = []

        def on_response(response):
            """拦截网络响应，捕获帖子 API 数据"""
            url = response.url
            if "c/f/pb/page_pc" in url or "pb/page" in url:
                try:
                    body = response.text()
                    if body and len(body) > 1000:
                        api_responses.append(body)
                        logger.debug(f"捕获 API 响应: {len(body)} 字符")
                except Exception:
                    pass

        # 使用 see_lz=1 只看楼主
        url = f"{self.thread_url}?see_lz=1&pn={page_num}"

        # 如果是 persistent_context，需要创建新页面
        if hasattr(self._context, "new_page"):
            page = self._context.new_page()
        else:
            page = self._browser.new_page()

        try:
            # 注册响应拦截器
            page.on("response", on_response)

            logger.info(f"浏览器抓取第 {page_num} 页: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)

            # 处理验证码
            if self._is_verification_page(page):
                if not self._wait_for_verification(page):
                    return ""

            # 额外等待
            page.wait_for_timeout(3000)
            self._scroll_page(page)

            # 保存 Cookie
            if page_num == 1:
                self._save_cookies()

            html = page.content()

            # 将捕获的 API 数据注入 HTML
            if api_responses:
                import json as _json
                for i, resp in enumerate(api_responses):
                    data_tag = (
                        f'<script id=\"__API_DATA_{i}__\" type=\"application/json\">'
                        + resp
                        + '</script>'
                    )
                    html = html.replace("</body>", data_tag + "</body>")
                logger.info(f"注入了 {len(api_responses)} 条 API 响应数据")

            if page_num == 1:
                debug_file = Path(__file__).parent.parent / "debug_page.html"
                debug_file.write_text(html, encoding="utf-8")
                logger.info(f"调试HTML已保存: {debug_file}")

            logger.info(f"第 {page_num} 页抓取完成 ({len(html)} 字符)")
            return html

        except Exception as e:
            logger.error(f"浏览器第 {page_num} 页抓取失败: {e}")
            raise
        finally:
            page.close()

    def _wait_for_posts(self, page, timeout: int = 10):
        """等待帖子内容出现"""
        selectors = [
            "div.l_post",
            ".d_post_content",
            "article",
            "[data-field]",
            "div[class*='lzljf']",
            "div.p_post",
        ]

        for _ in range(timeout):
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        logger.debug(f"检测到帖子元素: {sel}")
                        page.wait_for_timeout(2000)
                        return True
                except Exception:
                    pass
            time.sleep(1)

        # 没检测到特定元素，但还是等加载
        page.wait_for_timeout(BROWSER_WAIT_TIME * 1000)
        return False

    def _extract_posts_via_js(self, page) -> list | None:
        """通过 JavaScript 从 DOM 中提取帖子数据"""
        try:
            result = page.evaluate("""() => {
                const posts = [];

                // 尝试多种选择器找到帖子容器
                const selectors = [
                    '.l_post', '[data-field]', '.p_post',
                    'div[class*="post"]', 'div[class*="Post"]',
                    'li[class*="post"]', 'li[class*="Post"]',
                    'article', '.d_post'
                ];

                let containers = [];
                for (const sel of selectors) {
                    containers = document.querySelectorAll(sel);
                    if (containers.length > 0) break;
                }

                // 如果标准选择器都不匹配，尝试通过文本找
                if (containers.length === 0) {
                    // 查找所有包含"楼"文本的元素的父级帖子容器
                    const allElements = document.querySelectorAll('*');
                    const floorParents = new Set();
                    for (const el of allElements) {
                        if (el.childNodes.length === 1 &&
                            el.childNodes[0].nodeType === 3 &&
                            /\\d+楼/.test(el.textContent.trim())) {
                            // 向上查找帖子容器
                            let parent = el.parentElement;
                            for (let i = 0; i < 10 && parent; i++) {
                                const cls = parent.className || '';
                                if (cls.includes('post') || cls.includes('reply') ||
                                    cls.includes('item') || parent.getAttribute('data-field')) {
                                    floorParents.add(parent);
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                        }
                    }
                    containers = Array.from(floorParents);
                }

                for (const container of containers) {
                    try {
                        // 提取 data-field
                        const dataField = container.getAttribute('data-field');
                        let data = {};
                        if (dataField) {
                            try { data = JSON.parse(dataField); } catch(e) {}
                        }

                        // 提取作者
                        let author = '';
                        const authorEl = container.querySelector(
                            '.d_name a, .p_author_name, [class*="user_name"], [class*="username"], a[class*="name"]'
                        );
                        if (authorEl) author = authorEl.textContent.trim();

                        // 提取内容
                        let content = '';
                        const contentEl = container.querySelector(
                            '.d_post_content, .j_d_post_content, [class*="content"]'
                        );
                        if (contentEl) {
                            content = contentEl.innerText || contentEl.textContent || '';
                            content = content.trim();
                        }

                        // 提取时间
                        let timeStr = '';
                        const timeEl = container.querySelector(
                            '.tail-info, [class*="time"], [class*="date"], time'
                        );
                        if (timeEl) timeStr = timeEl.textContent.trim();

                        // 提取楼层
                        let floor = 0;
                        const floorEl = container.querySelector(
                            '.tail-info, [class*="floor"], [class*="post_no"]'
                        );
                        if (floorEl) {
                            const match = floorEl.textContent.match(/(\\d+)楼/);
                            if (match) floor = parseInt(match[1]);
                        }

                        if (author || content) {
                            posts.push({
                                author: author,
                                content: content,
                                floor: floor,
                                time_str: timeStr,
                                data: data
                            });
                        }
                    } catch(e) {}
                }

                return posts;
            }""")

            if result and isinstance(result, list) and len(result) > 0:
                return result

            return None
        except Exception as e:
            logger.debug(f"JS 提取失败: {e}")
            return None

    def _scroll_page(self, page, max_scrolls: int = 5):
        """模拟滚动页面以加载懒加载内容"""
        try:
            prev_height = 0
            for _ in range(max_scrolls):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(int(BROWSER_SCROLL_DELAY * 1000))

                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == prev_height:
                    break
                prev_height = new_height

            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"scroll error: {e}")

    def fetch_all(self) -> list[str]:
        """抓取所有页面"""
        self._init_browser()

        pages = []

        try:
            first_page = self.fetch_page(1)
            if not first_page or len(first_page) < 500:
                logger.error("第一页抓取失败或内容为空（可能是验证未通过）。")
                return pages

            pages.append(first_page)

            from parser import TiebaParser

            total_pages = TiebaParser.get_total_pages(first_page)
            logger.info(f"检测到总页数: {total_pages}")

            if self.max_pages > 0:
                total_pages = min(total_pages, self.max_pages)
                logger.info(f"已限制最大页数为: {total_pages}")

            for page_num in range(2, total_pages + 1):
                try:
                    import random as _random

                    time.sleep(_random.uniform(MIN_DELAY, MAX_DELAY))
                    html = self.fetch_page(page_num)
                    if html and len(html) > 500:
                        pages.append(html)
                    logger.info(f"进度: {page_num}/{total_pages}")
                except Exception as e:
                    logger.error(f"第 {page_num} 页抓取失败: {e}")
                    continue

            return pages

        finally:
            self._close_browser()
