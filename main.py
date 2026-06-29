"""
贴吧楼主帖子汇总工具 - CLI 入口

用法:
    python main.py "https://tieba.baidu.com/p/1234567890"
    python main.py "https://tieba.baidu.com/p/1234567890" --cookie-file cookies.txt --no-summary
    python main.py "https://tieba.baidu.com/p/1234567890" --max-pages 5 --output-dir ./output
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from config import DEFAULT_MAX_PAGES, DEFAULT_OUTPUT_DIR
from parser import TiebaParser, Post, ThreadInfo
from writer import MarkdownWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def api_dict_to_post(d: dict) -> Post:
    """将 API 返回的 dict 转为 Post 对象"""
    ts = d.get("timestamp", 0)
    if isinstance(ts, (int, float)) and ts > 1000000000:
        timestamp = datetime.fromtimestamp(ts)
    else:
        timestamp = TiebaParser.parse_time(str(d.get("time_str", "")))

    return Post(
        author=d.get("author", ""),
        content=d.get("content", ""),
        floor=d.get("floor", 0),
        time_str=d.get("time_str", ""),
        timestamp=timestamp,
    )


def fetch_with_api(tid: str, cookie_file: str = "", max_pages: int = 0) -> tuple[list[dict], dict] | None:
    """使用 JSON API 抓取"""
    try:
        from fetcher.api_fetcher import ApiFetcher

        logger.info("使用 JSON API 抓取...")
        fetcher = ApiFetcher(tid=tid, cookie_file=cookie_file, max_pages=max_pages)
        api_data_list = fetcher.fetch_all()

        if not api_data_list:
            logger.warning("API 未返回数据")
            return None

        info = ApiFetcher.extract_thread_info(api_data_list)
        logger.info(
            "楼主 '%s' 共 %d 条发言，来自 %d 页",
            info.get("author", "?"),
            info.get("total_posts", 0),
            info.get("total_pages", 0),
        )
        return api_data_list, info

    except ImportError:
        logger.warning("API fetcher 不可用")
        return None
    except Exception as e:
        logger.warning(f"API 抓取失败: {e}")
        return None


def fetch_with_browser(tid: str, max_pages: int = 0, headless: bool = True) -> tuple[list[str], ThreadInfo] | None:
    """使用浏览器抓取（手动过验证码）"""
    try:
        from fetcher.browser_fetcher import BrowserFetcher

        logger.info("使用 Playwright 浏览器抓取 (headless=%s)...", headless)
        fetcher = BrowserFetcher(tid=tid, max_pages=max_pages, headless=headless)

        parser = TiebaParser()
        html_pages = fetcher.fetch_all()
        logger.info(f"共抓取 {len(html_pages)} 页 HTML")

        all_posts = []
        thread_meta = {}
        for i, html in enumerate(html_pages, 1):
            posts, meta = parser.parse(html)
            all_posts.extend(posts)
            if i == 1:
                thread_meta = meta
                thread_meta["author"] = posts[0].author if posts else ""

        author = thread_meta.get("author", "")
        owner_posts = parser.filter_author_posts(all_posts, author)
        owner_posts = parser.sort_by_time(owner_posts)

        thread_info = ThreadInfo(
            title=thread_meta.get("title", ""),
            tid=tid,
            author=author,
            total_pages=thread_meta.get("total_pages", len(html_pages)),
            total_posts=len(owner_posts),
            forum_name=thread_meta.get("forum_name", ""),
            posts=owner_posts,
        )

        return html_pages, thread_info

    except ImportError:
        logger.error("Playwright 未安装。请运行: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        logger.error(f"浏览器抓取失败: {e}")
        return None


def main():
    parser_args = argparse.ArgumentParser(
        description="贴吧楼主帖子汇总工具 - 提取楼主发言并生成 Markdown 汇总",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "https://tieba.baidu.com/p/1234567890"
  python main.py "https://tieba.baidu.com/p/1234567890" --visible  # 首次使用，手动过验证
  python main.py "https://tieba.baidu.com/p/1234567890" --max-pages 10 --no-summary
        """,
    )
    parser_args.add_argument("url", help="贴吧帖子链接")
    parser_args.add_argument("--cookie-file", default="", help="Cookie 文件路径")
    parser_args.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                             help=f"最大抓取页数，0 表示不限制 (默认: {DEFAULT_MAX_PAGES})")
    parser_args.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser_args.add_argument("--no-summary", action="store_true", help="跳过 AI 摘要生成")
    parser_args.add_argument("--force-browser", action="store_true", help="强制使用浏览器（Playwright）抓取")
    parser_args.add_argument("--visible", action="store_true", help="可见浏览器模式（用于首次手动过验证码）")

    args = parser_args.parse_args()

    # 解析 URL
    try:
        tid = TiebaParser.extract_tid(args.url)
        logger.info(f"帖子ID: {tid}")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    browser_headless = not args.visible
    thread_info = None
    api_data_list = None

    # ---- 策略1: JSON API（优先，最快）----
    if not args.force_browser:
        result = fetch_with_api(tid, args.cookie_file, args.max_pages)
        if result is not None:
            api_data_list, api_info = result
            if api_info.get("posts"):
                # 转为 Post 对象
                posts = [api_dict_to_post(p) for p in api_info["posts"]]
                thread_info = ThreadInfo(
                    title=api_info.get("title", ""),
                    tid=tid,
                    author=api_info.get("author", ""),
                    total_pages=api_info.get("total_pages", 0),
                    total_posts=len(posts),
                    forum_name=api_info.get("forum_name", ""),
                    posts=posts,
                )
                logger.info(f"API 抓取成功！楼主 {thread_info.author} 共 {thread_info.total_posts} 条发言")

    # ---- 策略2: 浏览器抓取 ----
    if thread_info is None or not thread_info.posts:
        if args.force_browser or thread_info is None:
            logger.info("尝试浏览器抓取...")
            result = fetch_with_browser(tid, args.max_pages, browser_headless)
            if result:
                _, thread_info = result

    if thread_info is None or not thread_info.posts:
        logger.error("所有抓取方式均失败，未能获取帖子内容。")
        if not args.visible:
            logger.info("提示：首次使用请运行 --visible --force-browser 手动过验证码")
        sys.exit(1)

    # ---- AI 摘要 ----
    summary = ""
    if not args.no_summary:
        try:
            from summarizer import generate_summary
            logger.info("正在生成 AI 摘要...")
            summary = generate_summary(thread_info)
        except ImportError:
            logger.warning("摘要模块不可用（需要安装 anthropic）")
        except Exception as e:
            logger.warning(f"生成摘要失败: {e}")

    # ---- 写入 Markdown ----
    writer = MarkdownWriter(output_dir=args.output_dir)
    output_path = writer.write(thread_info, summary, source_url=args.url)

    logger.info(f"完成！输出文件: {output_path}")
    print(f"\n{output_path}")


if __name__ == "__main__":
    main()
