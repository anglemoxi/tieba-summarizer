"""
AI 摘要模块 - 调用 Claude API 生成帖子内容摘要
"""

import logging

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from parser import ThreadInfo, Post

logger = logging.getLogger(__name__)

# 单次摘要最大输入字符数（避免超出 token 限制）
MAX_CHARS_PER_CHUNK = 30000


def _build_prompt(posts: list[Post], thread_info: ThreadInfo) -> str:
    """构建摘要 prompt"""
    # 准备帖子内容
    posts_text = []
    for post in posts:
        time_str = post.time_str or "时间未知"
        floor_str = f"#{post.floor}楼" if post.floor > 0 else ""
        posts_text.append(
            f"[{time_str} {floor_str}]\n{post.content}\n"
        )

    all_content = "\n---\n".join(posts_text)

    prompt = f"""请为以下百度贴吧楼主的发言内容生成一份结构化的摘要。

## 帖子信息
- 标题：{thread_info.title}
- 楼主：{thread_info.author}
- 贴吧：{thread_info.forum_name}
- 楼主发言总数：{thread_info.total_posts} 条

## 楼主发言内容（按时间顺序）

{all_content}

---

请按以下格式输出摘要（使用 Markdown）：

### 主题概述
（用 2-3 句话概括楼主在帖子里主要讲了什么）

### 关键时间线
（列出关键的时间节点和对应的事件/内容，用列表形式）

### 内容要点
（列出楼主提到的主要内容要点，每条一行）

### 总结
（用 1-2 句话做整体总结）

注意：
- 只总结楼主（{thread_info.author}）的发言，不涉及他人回复
- 保持客观，不要添加主观评价
- 如果内容过少，摘要也要相应简洁
"""
    return prompt


def _chunk_posts(posts: list[Post], max_chars: int = MAX_CHARS_PER_CHUNK) -> list[list[Post]]:
    """将帖子列表分块，每块不超过 max_chars"""
    chunks = []
    current_chunk = []
    current_len = 0

    for post in posts:
        post_len = len(post.content) + len(post.time_str) + 50  # 额外开销
        if current_len + post_len > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0
        current_chunk.append(post)
        current_len += post_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _call_claude(prompt: str) -> str:
    """调用 Claude API"""
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "未设置 ANTHROPIC_API_KEY。请在 .env 文件中设置或设置环境变量。"
        )

    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("请安装 anthropic 库: pip install anthropic")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    logger.info(f"正在调用 {ANTHROPIC_MODEL} 生成摘要...")
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    # 提取文本内容
    content = message.content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "\n".join(text_parts)

    return str(content)


def generate_summary(thread_info: ThreadInfo) -> str:
    """
    生成帖子摘要

    Args:
        thread_info: 帖子信息（包含楼主全部发言）

    Returns:
        Markdown 格式的摘要文本
    """
    posts = thread_info.posts

    if not posts:
        return "（无内容可摘要）"

    if not ANTHROPIC_API_KEY:
        logger.warning("未配置 ANTHROPIC_API_KEY，跳过摘要")
        return ""

    # 如果帖子不多，一次性摘要
    total_chars = sum(len(p.content) for p in posts)
    if total_chars <= MAX_CHARS_PER_CHUNK:
        prompt = _build_prompt(posts, thread_info)
        return _call_claude(prompt)

    # 长帖分段摘要
    logger.info(f"内容较长（{total_chars} 字符），分段摘要...")
    chunks = _chunk_posts(posts)
    summaries = []

    for i, chunk in enumerate(chunks, 1):
        logger.info(f"摘要第 {i}/{len(chunks)} 段...")

        mini_info = ThreadInfo(
            title=f"{thread_info.title}（第{i}段）",
            author=thread_info.author,
            forum_name=thread_info.forum_name,
            total_posts=len(chunk),
            posts=chunk,
        )

        prompt = _build_prompt(chunk, mini_info)
        summary = _call_claude(prompt)
        summaries.append(f"### 第 {i} 段\n\n{summary}")

    # 如果有多段，生成总摘要
    if len(summaries) > 1:
        merge_prompt = f"""以下是帖子的分段摘要，请将它们合并为一份完整的结构化摘要。

帖子：{thread_info.title}
楼主：{thread_info.author}

分段摘要：
{chr(10).join(summaries)}

请输出合并后的完整摘要，格式与分段摘要一致（主题概述、关键时间线、内容要点、总结）。
"""
        return _call_claude(merge_prompt)

    return summaries[0] if summaries else ""
