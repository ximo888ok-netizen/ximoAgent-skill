#!/usr/bin/env python3
"""
项目知识图谱检索工具
通用版，适配任意项目的 Markdown 知识图谱文件。无第三方依赖，仅需 Python 3.8+。

用法:
  python search_map.py list [--map <路径>]           列出所有章节
  python search_map.py <章节号> [--map <路径>]        查看指定章节
  python search_map.py "<关键词>" [--map <路径>]      按关键词搜索
  python search_map.py stale [--map <路径>]           检查图谱鲜度
  python search_map.py --map docs/ARCHITECTURE.md list

全局标志:
  --json        以 JSON 格式输出（机器可读）
  --summary     搜索时只显示匹配章节名和行数（精简模式）
  --check-stale 在任何命令前先检查图谱鲜度并警告
"""
import re
import sys
import json
import argparse
from pathlib import Path

# Windows 控制台 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── 文件定位 ──────────────────────────────────────────

def find_map_file(explicit: str = None) -> Path:
    """定位知识图谱文件"""
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p
    return Path.cwd() / "PROJECT_MAP.md"


# ── 章节解析 ──────────────────────────────────────────

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


def chapter_tag(title: str) -> str:
    """检测章节的来源标记：[curated] 或 [auto-generated] 或空"""
    m = re.search(r'\[(curated|auto-generated)\]', title)
    return m.group(1) if m else ""


def chapter_base_title(title: str) -> str:
    """去掉标记后的纯标题"""
    return re.sub(r'\s*\[(curated|auto-generated)\]\s*', ' ', title).strip()


# ── 鲜度检查 ──────────────────────────────────────────

def get_git_last_commit_time() -> float:
    """返回最近一次 git 提交的时间戳（秒），失败返回 0"""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0


def get_source_files_mtime(root: Path, patterns: list = None) -> float:
    """返回源码目录下最新文件的 mtime（秒），失败返回 0。
    
    默认扫描: src/, lib/, app/, internal/, pkg/, cmd/, main.*, *.py, *.go, *.ts, *.js, *.rs, *.java
    """
    if patterns is None:
        patterns = [
            "src/**/*", "lib/**/*", "app/**/*", "internal/**/*",
            "pkg/**/*", "cmd/**/*",
            "main.*", "*.py", "*.go", "*.ts", "*.js", "*.rs", "*.java",
        ]
    
    max_mtime = 0.0
    seen_dirs = set()
    
    for pattern in patterns:
        # 避免大量重复扫描
        matches = list(root.glob(pattern))
        for p in matches:
            if p.is_file() and p.suffix not in ('.md', '.txt', '.yml', '.yaml', '.json', '.toml'):
                try:
                    mtime = p.stat().st_mtime
                    if mtime > max_mtime:
                        max_mtime = mtime
                except OSError:
                    pass
    
    return max_mtime


def check_staleness(map_path: Path, sections: list = None) -> dict:
    """检查图谱鲜度，返回诊断字典。

    返回: {
        "stale": bool,          # 是否过期
        "level": "fresh"|"stale"|"critical",  # 鲜度等级
        "map_mtime": float,     # 地图修改时间
        "git_mtime": float,     # 最近 git 提交时间
        "source_mtime": float,  # 最新源码修改时间
        "map_mtime_str": str,   # 可读地图时间
        "git_mtime_str": str,   # 可读 git 时间
        "source_mtime_str": str,# 可读源码时间
        "stale_sections": [],   # 可能过期的章节号列表
        "message": str,         # 人类可读摘要
    }
    """
    import datetime
    
    result = {
        "stale": False,
        "level": "fresh",
        "map_mtime": 0.0,
        "git_mtime": 0.0,
        "source_mtime": 0.0,
        "map_mtime_str": "",
        "git_mtime_str": "",
        "source_mtime_str": "",
        "stale_sections": [],
        "message": "",
    }
    
    try:
        result["map_mtime"] = map_path.stat().st_mtime
    except OSError:
        result["stale"] = True
        result["level"] = "critical"
        result["message"] = f"错误: 无法读取地图文件 {map_path}"
        return result
    
    def fmt_ts(ts):
        if ts == 0:
            return "N/A"
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    
    result["map_mtime_str"] = fmt_ts(result["map_mtime"])
    
    # 对比 git 最近提交
    result["git_mtime"] = get_git_last_commit_time()
    result["git_mtime_str"] = fmt_ts(result["git_mtime"])
    
    # 对比源码最新修改
    result["source_mtime"] = get_source_files_mtime(Path.cwd())
    result["source_mtime_str"] = fmt_ts(result["source_mtime"])
    
    # 判定鲜度
    map_ts = result["map_mtime"]
    
    # 如果有 git 记录，以最近提交为基准
    if result["git_mtime"] > 0 and result["git_mtime"] > map_ts + 3600:
        result["stale"] = True
        result["level"] = "stale"
    
    # 如果源码比地图新超过 1 天（86400 秒），标记为严重过期
    if result["source_mtime"] > map_ts + 86400:
        result["stale"] = True
        result["level"] = "critical"
    elif result["source_mtime"] > map_ts + 3600:
        result["stale"] = True
        if result["level"] != "critical":
            result["level"] = "stale"
    
    # 生成消息
    parts = [f"地图最后更新: {result['map_mtime_str']}"]
    if result["git_mtime"] > 0:
        delta = result["git_mtime"] - map_ts
        if delta > 86400:
            parts.append(f"[WARN] git commit ({result['git_mtime_str']}) is {delta/86400:.1f}d newer than map")
        elif delta > 3600:
            parts.append(f"[WARN] git commit ({result['git_mtime_str']}) is {delta/3600:.1f}h newer than map")
        else:
            parts.append(f"[OK] in sync with latest commit ({result['git_mtime_str']})")
    
    if result["source_mtime"] > map_ts + 3600:
        delta = result["source_mtime"] - map_ts
        if delta > 86400:
            parts.append(f"[WARN] source is {delta/86400:.1f}d newer than map")
        else:
            parts.append(f"[WARN] source is {delta/3600:.1f}h newer than map")
    
    if not result["stale"]:
        parts.append("[OK] map is fresh")
    
    result["message"] = "\n".join(parts)
    
    # 推断可能过期的章节（简化：若过期则提示第2章目录和第6章数据模型优先检查）
    if result["stale"] and result["git_mtime"] > 0:
        # 简单启发式：检查 git 最近改了什么类型文件
        import subprocess
        try:
            changed = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~5..HEAD"],
                capture_output=True, text=True, timeout=5
            )
            files = changed.stdout.strip().split("\n") if changed.stdout.strip() else []
            hints = set()
            for f in files:
                f = f.strip()
                if f.endswith(('.py', '.go', '.ts', '.js', '.rs', '.java', '.cpp')):
                    hints.add("2")  # 目录结构
                if any(k in f for k in ['model', 'schema', 'entity', 'migration']):
                    hints.add("6")  # 数据模型
                if any(k in f for k in ['api', 'route', 'handler', 'controller', 'endpoint']):
                    hints.add("7")  # API
                if any(k in f for k in ['config', 'setting', 'env', 'docker', 'deploy']):
                    hints.add("9")  # 技术栈
            result["stale_sections"] = sorted(hints)
        except Exception:
            pass
    
    return result


def cmd_stale(sections, map_path, args):
    """检查图谱鲜度"""
    result = check_staleness(map_path, sections)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    # 彩色输出的图标映射
    icons = {"fresh": "[OK]", "stale": "[WARN]", "critical": "[CRIT]"}
    icon = icons.get(result["level"], "?")
    
    print(f"{icon} Staleness: {result['level'].upper()}")
    print(result["message"])
    
    if result["stale_sections"]:
        print(f"\n建议优先检查的章节: {', '.join(f'第{ch}章' for ch in result['stale_sections'])}")
    
    # 退出码反映鲜度
    if result["level"] == "critical":
        sys.exit(2)
    elif result["level"] == "stale":
        sys.exit(1)


# ── 命令：list ────────────────────────────────────────

def cmd_list(sections, map_path, args):
    """列出所有章节"""
    if args.json:
        entries = []
        for level, title, content in sections:
            entries.append({
                "number": extract_chapter_number(title),
                "title": chapter_base_title(title),
                "level": level,
                "lines": len(content.splitlines()),
                "tag": chapter_tag(title),
                "is_risk_chapter": extract_chapter_number(title) == "10",
            })
        print(json.dumps({"map_path": str(map_path), "total_sections": len(sections), "sections": entries},
                         ensure_ascii=False, indent=2))
        return

    print(f"知识图谱: {map_path}")
    print(f"共 {len(sections)} 个章节:\n")
    
    for level, title, content in sections:
        num = extract_chapter_number(title)
        tag = chapter_tag(title)
        base = chapter_base_title(title)
        indent = "  " if level == 3 else ""
        line_count = len(content.splitlines())
        
        # 高亮第 10 章（风险禁忌）
        risk_marker = " [PRIORITY]" if num == "10" else ""
        # 来源标记
        tag_marker = ""
        if tag == "curated":
            tag_marker = " [curated]"
        elif tag == "auto-generated":
            tag_marker = " [auto]"
        
        print(f"  {indent}{num:<6} {base}{tag_marker}{risk_marker}  ({line_count}行)")
    
    print(f"\n用法: python search_map.py <章节号|关键词> [--map <路径>]")
    print(f"      python search_map.py stale                       # 检查鲜度")


# ── 命令：chapter ─────────────────────────────────────

def cmd_chapter(sections, query, args):
    """按章节号返回完整章节内容"""
    for i, (level, title, content) in enumerate(sections):
        num = extract_chapter_number(title)
        if num == query or num.startswith(query + "."):
            if args.json:
                result = {
                    "number": num,
                    "title": chapter_base_title(title),
                    "level": level,
                    "tag": chapter_tag(title),
                    "content": content,
                    "subsections": [],
                }
                if "." not in query and level == 2:
                    for j in range(i + 1, len(sections)):
                        sub_level, sub_title, sub_content = sections[j]
                        if sub_level <= 2:
                            break
                        result["subsections"].append({
                            "number": extract_chapter_number(sub_title),
                            "title": chapter_base_title(sub_title),
                            "content": sub_content,
                        })
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            
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
    
    err = f"未找到章节: {query}"
    if args.json:
        print(json.dumps({"error": err}, ensure_ascii=False))
    else:
        print(err)
        print(f"运行 'python search_map.py list' 查看所有章节")
    sys.exit(1)


# ── 命令：search ──────────────────────────────────────

def cmd_search(sections, keyword, args):
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
                matches.append({
                    "line": i,
                    "context": content_lines[ctx_start:ctx_end],
                    "matched_line": line.strip(),
                })

        if matches:
            num = extract_chapter_number(title)
            results.append((num, title, matches))

    if args.json:
        output = {
            "keyword": keyword,
            "total_sections": len(results),
            "total_matches": sum(len(m) for _, _, m in results),
            "results": [],
        }
        for num, title, matches in results:
            output["results"].append({
                "number": num,
                "title": chapter_base_title(title),
                "tag": chapter_tag(title),
                "matches": [
                    {
                        "line": m["line"],
                        "matched_line": m["matched_line"],
                        "context": m["context"],
                    }
                    for m in matches
                ],
            })
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 精简模式
    if args.summary:
        total = sum(len(m) for _, _, m in results)
        print(f"找到 {len(results)} 个章节、{total} 处匹配 '{keyword}':\n")
        for num, title, matches in results:
            tag_marker = ""
            tag = chapter_tag(title)
            if tag == "curated":
                tag_marker = " [curated]"
            if num:
                print(f"  第{num}章 {chapter_base_title(title)}{tag_marker} — {len(matches)}处匹配")
            else:
                print(f"  └ {chapter_base_title(title)} — {len(matches)}处匹配")
        return

    max_per = getattr(args, 'max_per_section', 8)
    no_context = getattr(args, 'no_context', False)

    if not results:
        print(f"未找到匹配 '{keyword}' 的内容")
        all_titles = [t for _, t, _ in sections]
        suggestions = [t for t in all_titles
                       if kw_norm in re.sub(r'\s+', '', t).lower()]
        if suggestions:
            print(f"\n相关章节: {', '.join(suggestions)}")
        return

    total = sum(len(m) for _, _, m in results)
    shown = sum(min(len(m), max_per) for _, _, m in results)
    if shown < total:
        print(f"找到 {len(results)} 个章节、{total} 处匹配（显示 {shown} 处，--max-per-section={max_per}） '{keyword}':\n")
    else:
        print(f"找到 {len(results)} 个章节、{total} 处匹配 '{keyword}':\n")

    for num, title, matches in results:
        tag = chapter_tag(title)
        tag_str = f" [curated]" if tag == "curated" else (" [auto]" if tag == "auto-generated" else "")
        header = f"{num} {title}" if num else f"  └ {title}"
        print("-" * 50)
        shown_count = min(len(matches), max_per)
        if len(matches) > max_per:
            print(f"  {header}{tag_str}  ({len(matches)}处匹配, 显示前{max_per}处)")
        else:
            print(f"  {header}{tag_str}  ({len(matches)}处匹配)")
        print("-" * 50)
        for ctx in matches[:max_per]:
            if no_context:
                print(f"  > {ctx['matched_line']}")
            else:
                for ctx_line in ctx["context"]:
                    ctx_norm = re.sub(r'\s+', '', ctx_line).lower()
                    marker = ">" if kw_norm in ctx_norm else " "
                    print(f"  {marker} {ctx_line}")
                print()


# ── 主入口 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="项目知识图谱检索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  search_map.py list                        列出所有章节
  search_map.py 7.3                         查看第7.3节
  search_map.py "消息队列"                   搜索关键词
  search_map.py stale                       检查图谱鲜度
  search_map.py list --json                 以JSON格式输出章节列表
  search_map.py "认证" --summary            精简搜索
  search_map.py "认证" --max-per-section 3  每章节最多3处匹配
  search_map.py "认证" --no-context         只显示匹配行，不含上下文
  search_map.py 6 --check-stale             查看第6章前先检查鲜度
        """,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="list",
        help="章节号(如 3)、关键词(如 'DI容器')、list 或 stale",
    )
    parser.add_argument(
        "--map", "-m",
        default=None,
        help="知识图谱文件路径，默认 PROJECT_MAP.md",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="以 JSON 格式输出（机器可读）",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="搜索时只显示匹配章节名和行数（精简模式）",
    )
    parser.add_argument(
        "--max-per-section",
        type=int,
        default=8,
        help="每章节最多显示的匹配数，默认 8",
    )
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="搜索时只显示匹配行，不显示上下文",
    )
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="在任何命令前先检查图谱鲜度并警告",
    )
    args = parser.parse_args()

    map_path = find_map_file(args.map)
    if not map_path.exists():
        err = f"错误: 找不到知识图谱文件 {map_path}"
        if args.json:
            print(json.dumps({"error": err, "hint": "用 --map <路径> 指定，或在项目根目录创建 PROJECT_MAP.md"},
                             ensure_ascii=False))
        else:
            print(err)
            print("提示: 用 --map <路径> 指定，或在项目根目录创建 PROJECT_MAP.md")
        sys.exit(1)

    text = map_path.read_text(encoding="utf-8")
    sections = load_sections(text)

    # --check-stale 前缀检查
    if args.check_stale:
        result = check_staleness(map_path, sections)
        if result["stale"]:
            icons = {"stale": "[WARN]", "critical": "[CRIT]"}
            icon = icons.get(result["level"], "[WARN]")
            if args.json:
                # JSON 模式下将鲜度信息注入后续输出（作为 stderr 警告）
                pass  # 不阻塞，但下面会打印到 stderr
            print(f"{icon} Staleness warning ({result['level']}): {result['map_mtime_str']}", file=sys.stderr)
            if result["stale_sections"]:
                print(f"   建议优先检查: {', '.join(f'第{ch}章' for ch in result['stale_sections'])}", file=sys.stderr)
            print(file=sys.stderr)
        else:
            print(f"[OK] map is fresh ({result['map_mtime_str']})", file=sys.stderr)
            print(file=sys.stderr)

    query = args.query.strip()
    if query.lower() in ("list", "ls", "-l"):
        cmd_list(sections, map_path, args)
    elif query.lower() == "stale":
        cmd_stale(sections, map_path, args)
    elif re.match(r'^\d+(\.\d+)*$', query):
        cmd_chapter(sections, query, args)
    else:
        cmd_search(sections, query, args)


if __name__ == "__main__":
    main()
