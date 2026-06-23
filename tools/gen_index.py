#!/usr/bin/env python3
"""
项目结构化索引生成器
扫描项目源码，生成机器可读的 index.json。零依赖，Python 3.8+。

输出 index.json 包含：
  - 包/目录结构及导出符号
  - 模块间导入依赖图
  - 入口点识别
  - 热点路径（基于 git log）
  - 项目统计数据

用法:
  python gen_index.py                          # 在 cwd 生成 index.json
  python gen_index.py --output docs/index.json # 指定输出路径
  python gen_index.py --check                  # 只检查是否需要更新（退出码 0=新鲜, 1=过期）
  python gen_index.py --language go            # 强制指定语言（默认自动检测）
  python gen_index.py --skip-git               # 跳过 git 热点分析
"""
import json
import re
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# ── 语言检测与解析器注册 ──────────────────────────────

LANGUAGE_PARSERS = {}

def parser(lang, extensions):
    """装饰器：注册语言解析器"""
    def decorator(fn):
        for ext in extensions:
            LANGUAGE_PARSERS.setdefault(ext, {})[lang] = fn
        return fn
    return decorator


# ── 各语言导出符号提取 ─────────────────────────────────

@parser("python", [".py"])
def parse_python(lines):
    exports = []
    imports = []
    for line_num, line in enumerate(lines, 1):
        # 函数 / 异步函数定义
        m = re.match(r'^\s*(async\s+)?def\s+(\w+)', line)
        if m:
            name = m.group(2)
            if not name.startswith('_'):  # skip private
                exports.append({"kind": "func", "name": name, "line": line_num})
            continue
        # 类定义
        m = re.match(r'^\s*class\s+(\w+)', line)
        if m:
            name = m.group(1)
            if not name.startswith('_'):
                exports.append({"kind": "class", "name": name, "line": line_num})
            continue
        # import 语句
        m = re.match(r'^\s*(?:from\s+(\S+)\s+)?import\s+(.+)', line)
        if m:
            pkg = m.group(1) or ""
            items = m.group(2)
            imports.append(f"{pkg}::{items}" if pkg else items)
    return exports, imports


@parser("go", [".go"])
def parse_go(lines):
    exports = []
    imports = []
    in_import_block = False
    for line_num, line in enumerate(lines, 1):
        # import 块
        if re.match(r'^\s*import\s*\(', line):
            in_import_block = True
            continue
        if in_import_block:
            if ')' in line:
                in_import_block = False
            m = re.search(r'"([^"]+)"', line)
            if m:
                imports.append(m.group(1))
            continue
        # 单行 import
        m = re.match(r'^\s*import\s+"([^"]+)"', line)
        if m:
            imports.append(m.group(1))
            continue
        # 函数（大写开头 = exported）
        m = re.match(r'^\s*func\s+(?:\([^)]+\)\s+)?(\w+)', line)
        if m:
            name = m.group(1)
            if name[0].isupper():
                exports.append({"kind": "func", "name": name, "line": line_num})
            continue
        # 类型定义
        m = re.match(r'^\s*type\s+(\w+)', line)
        if m:
            name = m.group(1)
            if name[0].isupper():
                exports.append({"kind": "type", "name": name, "line": line_num})
            continue
        # 常量/变量（大写开头 = exported）
        m = re.match(r'^\s*(?:var|const)\s+(\w+)', line)
        if m:
            name = m.group(1)
            if name[0].isupper():
                exports.append({"kind": "var", "name": name, "line": line_num})
            continue
    return exports, imports


@parser("typescript", [".ts", ".tsx", ".mts", ".cts"])
@parser("javascript", [".js", ".jsx", ".mjs", ".cjs"])
def parse_tsjs(lines):
    exports = []
    imports = []
    for line_num, line in enumerate(lines, 1):
        # import 语句
        m = re.match(r'^\s*import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', line)
        if m:
            imports.append(m.group(1))
            continue
        m = re.match(r'^\s*import\s+[\'"]([^\'"]+)[\'"]', line)
        if m:
            imports.append(m.group(1))
            continue
        # export 语句
        m = re.match(r'^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)', line)
        if m:
            exports.append({"kind": "func", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*export\s+(?:default\s+)?class\s+(\w+)', line)
        if m:
            exports.append({"kind": "class", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*export\s+(?:const|let|var)\s+(\w+)', line)
        if m:
            exports.append({"kind": "var", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*export\s+(?:interface|type)\s+(\w+)', line)
        if m:
            exports.append({"kind": "type", "name": m.group(1), "line": line_num})
            continue
        # 非 export 的顶层定义（在模块作用域内也算导出候选）
        m = re.match(r'^\s*(?:async\s+)?function\s+(\w+)', line)
        if m:
            name = m.group(1)
            if name[0].isupper():
                exports.append({"kind": "func", "name": name, "line": line_num})
            continue
        m = re.match(r'^\s*class\s+(\w+)', line)
        if m:
            name = m.group(1)
            if name[0].isupper():
                exports.append({"kind": "class", "name": name, "line": line_num})
    return exports, imports


@parser("rust", [".rs"])
def parse_rust(lines):
    exports = []
    imports = []
    for line_num, line in enumerate(lines, 1):
        m = re.match(r'^\s*pub\s+(?:async\s+)?fn\s+(\w+)', line)
        if m:
            exports.append({"kind": "func", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*pub\s+(?:unsafe\s+)?(?:struct|enum|trait|type)\s+(\w+)', line)
        if m:
            exports.append({"kind": "type", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*pub\s+(?:const|static)\s+(\w+)', line)
        if m:
            exports.append({"kind": "var", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*(?:pub\s+)?mod\s+(\w+)', line)
        if m:
            exports.append({"kind": "mod", "name": m.group(1), "line": line_num})
            continue
        # use 语句
        m = re.match(r'^\s*use\s+(.+);', line)
        if m:
            imports.append(m.group(1))
    return exports, imports


@parser("java", [".java"])
def parse_java(lines):
    exports = []
    imports = []
    for line_num, line in enumerate(lines, 1):
        m = re.match(r'^\s*import\s+(\S+);', line)
        if m:
            imports.append(m.group(1))
            continue
        m = re.match(r'^\s*public\s+(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)', line)
        if m:
            exports.append({"kind": "type", "name": m.group(1), "line": line_num})
            continue
        m = re.match(r'^\s*public\s+(?:static\s+)?(?:[\w<>\[\]]+\s+)+(\w+)\s*\(', line)
        if m:
            exports.append({"kind": "func", "name": m.group(1), "line": line_num})
    return exports, imports


# ── 语言检测 ───────────────────────────────────────────

def detect_languages(root: Path) -> dict:
    """检测项目中各语言的源文件数量，返回 {语言: 文件数}"""
    counts = defaultdict(int)
    lang_names = {
        ".py": "python", ".go": "go",
        ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript",
        ".rs": "rust", ".java": "java",
    }
    # 只扫描顶层若干目录，避免进入 node_modules/.git 等
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "target", "build", "dist", ".next", ".nuxt", "vendor",
        ".reasonix", ".trae",
    }
    for entry in root.rglob("*"):
        if entry.is_file():
            # 跳过隐藏目录和依赖目录
            parts = set(entry.parts)
            if parts & skip_dirs:
                continue
            ext = entry.suffix
            if ext in lang_names:
                counts[lang_names[ext]] += 1
    return dict(counts)


# ── 主分析逻辑 ─────────────────────────────────────────

def analyze_project(root: Path, language: str = None) -> dict:
    """扫描项目并生成结构化索引"""
    if language is None:
        lang_counts = detect_languages(root)
        if not lang_counts:
            return {"error": "未检测到支持的源代码文件"}
        language = max(lang_counts, key=lang_counts.get)

    # 收集所有源码文件
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "target", "build", "dist", ".next", ".nuxt", "vendor",
        ".reasonix", ".trae", "scripts",  # scripts 里放的是工具脚本
    }

    ext_to_lang = {}
    for lang, exts in {
        "python": [".py"], "go": [".go"],
        "typescript": [".ts", ".tsx"], "javascript": [".js", ".jsx"],
        "rust": [".rs"], "java": [".java"],
    }.items():
        for ext in exts:
            ext_to_lang[ext] = lang

    # 按目录分组
    dir_files = defaultdict(list)      # dir -> [file_paths]
    dir_exports = defaultdict(list)    # dir -> [exports]
    dir_imports = defaultdict(set)     # dir -> set of import targets
    all_files = []
    total_lines = 0

    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            parts = set(entry.parts)
            if parts & skip_dirs:
                continue
            ext = entry.suffix
            if ext not in ext_to_lang:
                continue
            try:
                content = entry.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                total_lines += len(lines)

                # 确定解析器
                lang = ext_to_lang[ext]
                parser_fn = LANGUAGE_PARSERS.get(ext, {}).get(lang)
                if parser_fn:
                    exports, imports = parser_fn(lines)
                    # 给导出符号填上行号
                    for exp in exports:
                        exp["file"] = str(entry.relative_to(root))
                else:
                    exports, imports = [], []

                rel = entry.relative_to(root)
                parent = str(rel.parent) if str(rel.parent) != "." else "."
                dir_files[parent].append(str(rel))
                all_files.append(str(rel))

                if exports:
                    dir_exports[parent].extend(exports)
                for imp in imports:
                    dir_imports[parent].add(imp)

            except Exception:
                continue

    # 推断入口点
    entry_points = _find_entry_points(root, dir_files, language)

    # 构建包信息
    packages = {}
    for d in sorted(dir_files):
        packages[d] = {
            "files": sorted(dir_files[d]),
            "file_count": len(dir_files[d]),
            "exports": sorted(
                [e for e in dir_exports[d] if "file" in e and "name" in e],
                key=lambda x: (x.get("file", ""), x.get("name", ""))
            )[:50],  # 每目录最多 50 个导出
            "imports": sorted(dir_imports[d])[:30],
        }

    result = {
        "project": root.resolve().name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "language": language,
        "root": str(root.resolve()),
        "packages": packages,
        "entry_points": entry_points,
        "risk_annotations": [],
        "stats": {
            "total_files": len(all_files),
            "total_dirs": len(dir_files),
            "total_lines": total_lines,
            "total_exports": sum(len(v) for v in dir_exports.values()),
        },
    }

    return result


def _find_entry_points(root: Path, dir_files: dict, language: str) -> list:
    """识别项目入口点文件"""
    candidates = []

    # 按语言查找典型入口文件名
    patterns = {
        "python": [r"^main\.py$", r"^app\.py$", r"^wsgi\.py$", r"^manage\.py$",
                    r"^__main__\.py$"],
        "go": [r"^main\.go$"],
        "typescript": [r"^index\.ts$", r"^main\.ts$", r"^app\.ts$", r"^server\.ts$"],
        "javascript": [r"^index\.js$", r"^main\.js$", r"^app\.js$", r"^server\.js$"],
        "rust": [r"^main\.rs$"],
        "java": [r"^Main\.java$", r"^Application\.java$", r"^App\.java$"],
    }

    pats = patterns.get(language, [])
    for d, files in dir_files.items():
        for f in files:
            fname = Path(f).name
            for pat in pats:
                if re.match(pat, fname):
                    candidates.append(f)
                    break

    return sorted(candidates)[:10]


# ── Git 热点分析 ───────────────────────────────────────

def analyze_hotspots(root: Path, max_files: int = 15) -> list:
    """基于 git log 识别最近修改频繁的文件（热点路径）"""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--name-only", "-50", "--format=%H"],
            capture_output=True, text=True, timeout=10, cwd=str(root)
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    # 统计文件出现频次
    file_counts = defaultdict(int)
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or len(line) == 40:  # commit hash line
            continue
        # 只统计源码文件
        ext = Path(line).suffix
        if ext in {".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs", ".java"}:
            file_counts[line] += 1

    # 按频次降序排列
    hotspots = sorted(file_counts.items(), key=lambda x: -x[1])[:max_files]
    return [
        {"file": f, "recent_changes": count}
        for f, count in hotspots if count >= 2
    ]


# ── 鲜度检查 ────────────────────────────────────────────

def check_staleness(index_path: Path, root: Path) -> dict:
    """检查 index.json 是否过期"""
    import subprocess

    if not index_path.exists():
        return {"stale": True, "level": "critical", "reason": "index.json not found"}

    try:
        index_mtime = index_path.stat().st_mtime
    except OSError:
        return {"stale": True, "level": "critical", "reason": "cannot read index.json"}

    # 检查源码最新修改时间
    max_source_mtime = 0.0
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv",
                 "target", "build", "dist", ".next", ".nuxt", "vendor"}

    for ext in [".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs", ".java"]:
        for entry in root.rglob(f"*{ext}"):
            if set(entry.parts) & skip_dirs:
                continue
            try:
                mtime = entry.stat().st_mtime
                if mtime > max_source_mtime:
                    max_source_mtime = mtime
            except OSError:
                pass

    # 也检查新增/删除文件
    try:
        added = subprocess.run(
            ["git", "diff", "--name-status", "HEAD~20..HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(root)
        )
        for line in added.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] in ("A", "D", "R"):  # Added, Deleted, Renamed
                max_source_mtime = max(max_source_mtime, index_mtime + 86401)
                break
    except Exception:
        pass

    # 判定
    if max_source_mtime > index_mtime + 86400:
        return {"stale": True, "level": "critical",
                "reason": f"源码变更比索引新 {(max_source_mtime - index_mtime)/86400:.1f} 天"}
    elif max_source_mtime > index_mtime + 3600:
        return {"stale": True, "level": "stale",
                "reason": f"源码变更比索引新 {(max_source_mtime - index_mtime)/3600:.1f} 小时"}
    else:
        return {"stale": False, "level": "fresh", "reason": "索引新鲜"}


# ── 主入口 ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="项目结构化索引生成器 — 生成机器可读的 index.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  gen_index.py                          在当前目录生成 index.json
  gen_index.py --output docs/index.json 指定输出路径
  gen_index.py --check                  仅检查索引鲜度
  gen_index.py --language go            强制指定语言
  gen_index.py --skip-git               跳过 git 热点分析
  gen_index.py --pretty                 格式化 JSON 输出（方便人类阅读）
        """,
    )
    parser.add_argument("--output", "-o", default=None,
                        help="输出路径，默认 ./index.json")
    parser.add_argument("--check", action="store_true",
                        help="仅检查鲜度，不生成")
    parser.add_argument("--language", "-l", default=None,
                        help="强制指定语言 (python/go/typescript/javascript/rust/java)")
    parser.add_argument("--skip-git", action="store_true",
                        help="跳过 git 热点分析")
    parser.add_argument("--pretty", "-p", action="store_true",
                        help="格式化 JSON 输出")
    parser.add_argument("--root", "-r", default=".",
                        help="项目根目录，默认当前目录")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_path = Path(args.output) if args.output else root / "index.json"

    if args.check:
        result = check_staleness(output_path, root)
        if result["stale"]:
            print(f"[WARN] index.json stale ({result['level']}): {result['reason']}")
            sys.exit(1 if result["level"] == "stale" else 2)
        else:
            print(f"[OK] {result['reason']}")
            sys.exit(0)

    # 生成索引
    print(f"[*] Scanning: {root}")
    index = analyze_project(root, args.language)

    if "error" in index:
        print(f"[!] {index['error']}", file=sys.stderr)
        sys.exit(1)

    # 添加 git 热点
    if not args.skip_git and not args.check:
        hotspots = analyze_hotspots(root)
        if hotspots:
            index["hotspots"] = hotspots

    # 计算文件 hash 用于快速鲜度检查
    index["content_hash"] = hashlib.sha256(
        json.dumps(index.get("packages", {}), sort_keys=True).encode()
    ).hexdigest()[:16]

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if args.pretty else None
    output_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=indent),
        encoding="utf-8"
    )

    # 报告
    stats = index["stats"]
    print(f"[OK] Generated index.json")
    print(f"  Language: {index['language']}")
    print(f"  Files: {stats['total_files']}")
    print(f"  Dirs: {stats['total_dirs']}")
    print(f"  Exports: {stats['total_exports']} symbols")
    if "hotspots" in index:
        print(f"  Hotspots: {len(index['hotspots'])} files")
    print(f"  Entry points: {', '.join(index['entry_points']) if index['entry_points'] else 'none'}")

    # 提示后续步骤
    print(f"\n[HINT] Search: python search_map.py list")
    print(f"[HINT] Outline: python outline.py <file>")


if __name__ == "__main__":
    main()
