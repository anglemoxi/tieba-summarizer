"""
Markdown 输出模块 - 生成格式化的 .md 文件
"""

import re
from datetime import datetime
from pathlib import Path

from parser import ThreadInfo, Post


class MarkdownWriter:
    """Markdown 文件写入器"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """清理文件名中的非法字符"""
        # 移除或替换 Windows 文件名不允许的字符
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        # 限制长度
        if len(name) > 80:
            name = name[:80]
        return name.strip()

    def _format_time(self, post: Post) -> str:
        """格式化帖子时间"""
        if post.timestamp:
            return post.timestamp.strftime("%Y-%m-%d %H:%M")
        return post.time_str or "时间未知"

    def _format_post_content(self, content: str) -> str:
        """格式化帖子内容（处理缩进、引用等）"""
        if not content:
            return "（无内容）"

        lines = content.split("\n")
        formatted = []
        for line in lines:
            line = line.strip()
            if line:
                formatted.append(line)
            else:
                formatted.append("")

        # 如果内容较长，用引用块包裹
        result = "\n".join(formatted)
        if len(result) > 200:
            # 长内容用分隔线标记
            return f"\n{result}\n"
        return result

    def _build_timeline(self, posts: list[Post]) -> str:
        """构建楼主发言时间线"""
        if not posts:
            return "（无发言）\n"

        lines = ["## 📋 楼主发言时间线\n"]

        # 按日期分组
        current_date = None

        for i, post in enumerate(posts, 1):
            post_date = ""
            if post.timestamp:
                post_date = post.timestamp.strftime("%Y-%m-%d")

            # 新日期添加分隔标题
            if post_date and post_date != current_date:
                current_date = post_date
                lines.append(f"### 📅 {current_date}\n")

            # 时间标签
            time_label = self._format_time(post)

            # 楼层信息
            floor_info = f" #{post.floor}楼" if post.floor > 0 else ""

            lines.append(f"**{time_label}**{floor_info}\n")

            # 内容
            content = self._format_post_content(post.content)
            lines.append(f"{content}\n")

            # 分隔线（非最后一条）
            if i < len(posts):
                lines.append("---\n")

        return "\n".join(lines)

    def _build_header(self, info: ThreadInfo, summary: str, source_url: str) -> str:
        """构建文件头部信息"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# 📝 {info.title or '贴吧帖子汇总'}",
            "",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| 帖子链接 | {source_url} |",
            f"| 贴吧 | {info.forum_name or '未知'} |",
            f"| 楼主 | **{info.author}** |",
            f"| 楼主发言数 | {info.total_posts} 条 |",
            f"| 总页数 | {info.total_pages} 页 |",
            f"| 抓取时间 | {now} |",
            "",
            "---\n",
        ]

        return "\n".join(lines)

    def _build_summary_section(self, summary: str) -> str:
        """构建摘要区域"""
        if not summary:
            return ""
        return f"## 🤖 AI 摘要\n\n{summary}\n\n---\n"

    def write(
        self,
        thread_info: ThreadInfo,
        summary: str = "",
        source_url: str = "",
    ) -> Path:
        """
        写入 Markdown 文件

        Args:
            thread_info: 帖子信息
            summary: AI 摘要文本
            source_url: 原始URL

        Returns:
            输出文件路径
        """
        # 生成文件名
        forum = self._sanitize_filename(thread_info.forum_name) or "贴吧"
        title = self._sanitize_filename(thread_info.title) or thread_info.tid
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{forum}_{title}_楼主汇总_{date_str}.md"
        filepath = self.output_dir / filename

        # 构建 Markdown 内容
        parts = [
            self._build_header(thread_info, summary, source_url),
            self._build_summary_section(summary),
            self._build_timeline(thread_info.posts),
            "",
            "---",
            "",
            f"*由贴吧楼主汇总工具自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        ]

        content = "\n".join(parts)

        # 写入文件
        filepath.write_text(content, encoding="utf-8")
        return filepath
