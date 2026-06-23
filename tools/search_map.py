#!/usr/bin/env python3
"""
项目知识图谱检索工具
通用版，适配任意项目的 Markdown 知识图谱文件。无第三方依赖，仅需 Python 3.8+。

用法:
  python search_map.py list [--map <路径>]           列出所有章节
  python search_map.py <章节号> [--map <路径>]        查看指定章节
  python search_map.py "<关键词>" [--map <路径>]      按关键词搜索
  python search_map.py --map docs/ARCHITECTURE.md list

默认读取当前工作目录下的 PROJECT_MAP.md。
"""
import re
import sys
import argparse
from pathlib import Path


def find_map_file(explicit: str = None) -> Path:
    """定位知识图谱文件"""
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p
    return Path.cwd() / "PROJECT_MAP.md"


def load_sections(text: str) -> list:
    """按 ## / ### 标题切分章节，返回 [(level, title, content), ...] 列表"""
    lines = text.splitlines()
    sections = []
    current_title = None
    current_level = 0
    current_lines = []

    for line in lines:
        m = re.match(r'^(#{2,3})\s+(.+)', line)
        if m:
            if current_title is not None:
                sections.append((current_level, current_title, '\n'.join(current_lines)))
            current_level = len(m.group(1))
            current_title = m.group(2).strip()
            current_lines = [line]
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append((current_level, current_title, '\n'.join(current_lines)))

    return sections


def extract_chapter_number(title: str) -> str:
    """从标题提取章节号，如 '7.3 商品管理域' -> '7.3'"""
    m = re.match(r'^(\d+(?:\.\d+)*)', title)
    return m.group(1) if m else ""


def cmd_list(sections, map_path):
    print(f"知识图谱: {map_path}")
    print(f"共 {len(sections)} 个章节:\n")
    for level, title, content in sections:
        num = extract_chapter_number(title)
        indent = "  " if level == 3 else ""
        line_count = len(content.splitlines())
        print(f"  {indent}{num:<6} {title}  ({line_count}行)")
    print(f"\n用法: python search_map.py <章节号|关键词> [--map <路径>]")


def cmd_chapter(sections, query):
    """按章节号返回完整章节内容"""
    for i, (level, title, content) in enumerate(sections):
        num = extract_chapter_number(title)
        if num == query or num.startswith(query + "."):
            if "." not in query and level == 2:
                # 二级章节：收集其所有子章节
                print("=" * 60)
                print(f"# {title}")
                print("=" * 60)
                print(content)
                for j in range(i + 1, len(sections)):
                    sub_level, sub_title, sub_content = sections[j]
                    if sub_level <= 2:
                        break
                    print(sub_content)
                return
            else:
                print(content)
                return
    print(f"未找到章节: {query}")
    print(f"运行 'python search_map.py list' 查看所有章节")


def cmd_search(sections, keyword):
    """按关键词搜索，返回匹配的行及上下文"""
    results = []
    kw_norm = re.sub(r'\s+', '', keyword).lower()

    for level, title, content in sections:
        content_lines = content.splitlines()
        matches = []
        for i, line in enumerate(content_lines):
            line_norm = re.sub(r'\s+', '', line).lower()
            if kw_norm in line_norm:
                ctx_start = max(0, i - 2)
                ctx_end = min(len(content_lines), i + 3)
                matches.append(content_lines[ctx_start:ctx_end])

        if matches:
            num = extract_chapter_number(title)
            results.append((num, title, matches))

    if not results:
        print(f"未找到匹配 '{keyword}' 的内容")
        all_titles = [t for _, t, _ in sections]
        suggestions = [t for t in all_titles
                       if kw_norm in re.sub(r'\s+', '', t).lower()]
        if suggestions:
            print(f"\n相关章节: {', '.join(suggestions)}")
        return

    total = sum(len(m) for _, _, m in results)
    print(f"找到 {len(results)} 个章节、{total} 处匹配 '{keyword}':\n")
    for num, title, matches in results:
        print("-" * 50)
        print(f"  {num} {title}  ({len(matches)}处匹配)")
        print("-" * 50)
        for ctx in matches[:8]:
            for ctx_line in ctx:
                ctx_norm = re.sub(r'\s+', '', ctx_line).lower()
                marker = ">" if kw_norm in ctx_norm else " "
                print(f"  {marker} {ctx_line}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="项目知识图谱检索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="list",
        help="章节号(如 3)、关键词(如 'DI容器')、或 list",
    )
    parser.add_argument(
        "--map", "-m",
        default=None,
        help="知识图谱文件路径，默认 PROJECT_MAP.md",
    )
    args = parser.parse_args()

    map_path = find_map_file(args.map)
    if not map_path.exists():
        print(f"错误: 找不到知识图谱文件 {map_path}")
        print("提示: 用 --map <路径> 指定，或在项目根目录创建 PROJECT_MAP.md")
        sys.exit(1)

    text = map_path.read_text(encoding="utf-8")
    sections = load_sections(text)

    query = args.query.strip()
    if query.lower() in ("list", "ls", "-l"):
        cmd_list(sections, map_path)
    elif re.match(r'^\d+(\.\d+)*$', query):
        cmd_chapter(sections, query)
    else:
        cmd_search(sections, query)


if __name__ == "__main__":
    main()
