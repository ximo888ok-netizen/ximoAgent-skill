---
name: "project-map"
description: "项目知识图谱生成与检索。当需要为项目创建结构化知识图谱、检索项目架构信息、或在代码变更后同步更新图谱时调用。适用于任何需要 AI 理解项目全貌的场景。"
---

# 项目知识图谱技能

为任意项目生成结构化知识图谱（`PROJECT_MAP.md` + `index.json`），并提供渐进式检索工具链，大幅节省 AI 编程时的 token 消耗。

## 核心理念

> **先用最小的 token 成本了解代码全貌，再精准读取需要修改的部分。**

传统的 "grep → read_file 全文件" 模式每次消耗 3000-8000 token。本技能提供三级检索体系，将典型探索成本压缩到 300-800 token（省 80-95%）。

## 何时调用

- **新项目初始化**：用户要求"分析项目结构""生成知识图谱""创建项目地图"时
- **动手前检索**：修改代码前需要了解项目架构、模块依赖、API 接口时
- **变更后同步**：完成代码修改后，更新索引和知识图谱
- **跨项目快速上手**：接手陌生项目，快速建立全局认知

## 核心组件

| 组件 | 位置 | 作用 |
|------|------|------|
| `PROJECT_MAP.md` | 目标项目根目录 | 知识图谱本体（10 章，AI 按项目实际情况编写） |
| `index.json` | 目标项目根目录 | 结构化索引（`gen_index.py` 自动生成，机器可读） |
| `tools/gen_index.py` | 本 skill 目录 | 项目索引生成器（零依赖，自动分析源码） |
| `tools/outline.py` | 本 skill 目录 | 文件大纲提取器（多语言，省 85-95% token） |
| `tools/search_map.py` | 本 skill 目录 | 知识图谱检索工具（关键词/章节号/鲜度检查） |
| `templates/AGENTS_PATCH.md` | 本 skill 目录 | AGENTS.md 补丁（渐进式读取规则 + 工具引导） |
| `templates/PROJECT_MAP_TEMPLATE.md` | 本 skill 目录 | 知识图谱空白章节模板 |
| `templates/INDEX_TEMPLATE.json` | 本 skill 目录 | index.json 参考模板 |

## 三级检索体系

```
                     ┌─────────────────────────────┐
  第一级：快速索引     │  gen_index.py --check        │  50 token
  （了解全貌）         │  outline.py <file>           │  100 token
                     │  search_map.py list          │  300 token
                     └─────────────┬───────────────┘
                                   │ 找到目标模块
                     ┌─────────────▼───────────────┐
  第二级：精准检索     │  search_map.py <章节号>      │  200 token
  （定位到行）         │  search_map.py "关键词"       │  400 token
                     │  outline.py <file> --json    │  300 token
                     └─────────────┬───────────────┘
                                   │ 确定修改范围
                     ┌─────────────▼───────────────┐
  第三级：按需读取     │  read_file offset/limit      │  500-1500 token
  （确认+修改）        │  read_file（仅需要时全读）     │  1500+ token
                     └─────────────────────────────┘
```

## 章节分类：核心 vs 辅助

知识图谱 10 章分为两类，通过标题标记区分可信度和维护策略：

| 分类 | 标记 | 章节 | 含义 |
|------|------|------|------|
| **核心章节** | `[curated]` | 第4章 业务流程、第8章 项目特有体系、第10章 风险禁忌 | 人工策划的架构决策和风险提示，AI 应高度信任 |
| **辅助章节** | `[auto-generated]` | 第2章 目录结构、第6章 数据模型、第9章 技术栈 | 可由工具辅助生成/更新，AI 应做信任前验证 |
| **混合章节** | 无标记 | 第0/1/3/5/7章 | 部分手写、部分可自动，按实际情况标记 |

**信任原则：过期地图比没有地图更危险。始终以实际代码为最终事实来源。**

---

## 工作流零：渐进式读取（每次修改前）

这是本技能最重要的行为规则。**永远不要用昂贵的工具做便宜工具能做的事。**

### 读取阶梯

| 优先级 | 工具 | Token | 场景 |
|--------|------|-------|------|
| 1 | `python scripts/outline.py <file>` | ~100 | 了解文件有哪些函数/类 |
| 2 | `python scripts/search_map.py <章节>` | ~200 | 了解项目架构/模块/API |
| 3 | `python scripts/search_map.py "关键词"` | ~400 | 搜索特定主题 |
| 4 | `read_file offset/limit` | ~500 | 只看目标函数实现 |
| 5 | `read_file` 全文件 | ~1500+ | 最后手段 |

### 反模式

- ❌ 上来就读整个文件（除非明确需要全文件理解）
- ❌ 用 `read_file` 浏览目录（用 `outline.py --recursive --summary` 替代）
- ❌ grep 后直接 read_file 每个匹配文件（先 `outline` 筛选）

---

## 工作流一：初始化

当用户要求分析项目并生成知识图谱时，执行以下步骤：

### 步骤 1：生成结构化索引（首选）

```bash
python tools/gen_index.py --output index.json --pretty
```

自动检测语言，扫描源码，生成 `index.json`（包含包结构、导出符号、入口点、git 热点）。

### 步骤 2：生成知识图谱（如需深度文档）

根据项目规模选择策略：

- **小型项目**（<50 源文件）：轻量初始化，详写第 0/2/9/10 章，简写其余
- **中型项目**（50-200 源文件）：轻量初始化，核心章节可深度分析
- **大型项目**（>200 源文件）：使用 Task 子代理并行探索（3-5 个并行）

**参考 `templates/PROJECT_MAP_TEMPLATE.md` 的章节结构，所有内容必须基于实际代码分析填写。**

### 步骤 3：部署工具

将 `tools/` 下所有 Python 文件复制到目标项目的 `scripts/` 目录。

### 步骤 4：更新 AGENTS.md

参考 `templates/AGENTS_PATCH.md` 添加渐进式读取规则和工具引导。

---

## 工作流二：检索

修改代码前，按优先级使用检索工具：

```
# 第一步：检查鲜度（每次必做）
python scripts/gen_index.py --check
python scripts/search_map.py stale

# 第二步：了解文件结构（替代 read_file）
python scripts/outline.py src/service/user.go
python scripts/outline.py src/ --recursive --summary

# 第三步：查看风险禁忌（强制）
python scripts/search_map.py 10

# 第四步：按需查章节/搜索
python scripts/search_map.py list
python scripts/search_map.py 7
python scripts/search_map.py "事务" --max-per-section 3
python scripts/search_map.py "认证" --summary

# 第五步：确认后精准读取
# read_file offset/limit（只读需要的部分）
```

### 工具速查

| 需求 | 命令 | Token |
|------|------|-------|
| 检查索引鲜度 | `python scripts/gen_index.py --check` | ~30 |
| 重新生成索引 | `python scripts/gen_index.py` | ~100 |
| 文件大纲 | `python scripts/outline.py <file>` | ~100 |
| 目录统计 | `python scripts/outline.py src/ -r -s` | ~50 |
| 列出章节 | `python scripts/search_map.py list` | ~300 |
| 查风险禁忌 | `python scripts/search_map.py 10` | ~200 |
| 查特定章节 | `python scripts/search_map.py 7` | ~200 |
| 搜索关键词 | `python scripts/search_map.py "缓存"` | ~400 |
| 精简搜索 | `python scripts/search_map.py "缓存" -s` | ~100 |
| 限制匹配数 | `python scripts/search_map.py "err" --max-per-section 3` | ~200 |
| 无上下文搜索 | `python scripts/search_map.py "接口" --no-context` | ~200 |

### 重要提醒

检索工具帮你定位信息位置，**动手修改前仍需 Read 实际代码确认**。过期地图比没有地图更危险——如果鲜度检查报告 `critical`，应直接读代码而非依赖地图。

---

## 工作流三：变更后同步

### 快速同步（推荐）

代码变更后重新生成 `index.json`：

```bash
python scripts/gen_index.py
```

### 知识图谱同步

| 变更类型 | 需同步的章节 |
|---------|------------|
| 新增/删除文件 | 第2章 目录结构 [auto-generated] |
| 修改架构/分层 | 第1章 架构层次、第3章 模块依赖 |
| 新增/修改 API | 第7章 API 接口定义 |
| 修改数据模型 | 第6章 数据模型 [auto-generated] |
| 新增/修改工具/插件 | 第8章 项目特有章节 |
| 修复已知风险 | 第10章 已知风险与禁忌 [curated] |
| 新增依赖 | 第9章 技术栈组件 [auto-generated] |
| 修改核心流程 | 第4章 核心业务流程、第5章 关键函数调用链 |

同步后更新文件末尾的"最后更新"日期。

---

## 工具参数详解

### gen_index.py

```
gen_index.py [--output <路径>] [--check] [--language <语言>] [--skip-git] [--pretty]

参数:
  --output, -o    输出路径，默认 ./index.json
  --check         仅检查鲜度（退出码: 0=fresh, 1=stale, 2=critical）
  --language, -l  强制指定语言 (python/go/typescript/javascript/rust/java)
  --skip-git      跳过 git 热点分析
  --pretty, -p    格式化 JSON 输出

示例:
  gen_index.py                             生成 index.json
  gen_index.py --check                     检查鲜度
  gen_index.py --language go --pretty      指定语言 + 格式化
```

### outline.py

```
outline.py <target> [--recursive] [--summary] [--json] [--kind <类型>] [--flat]

参数:
  target           文件或目录路径
  --recursive, -r  递归扫描目录
  --summary, -s    只显示文件级符号统计
  --json, -j       JSON 格式输出（机器可读）
  --kind, -k       筛选类型: func/class/type/const/var/mod
  --flat, -f       平铺显示（含行号）

示例:
  outline.py src/main.go                   单文件大纲
  outline.py src/ --recursive --summary    目录符号统计
  outline.py src/main.go --kind=func       只看函数
  outline.py src/main.go --json            JSON 输出
```

### search_map.py

```
search_map.py <query> [--map <路径>] [--json] [--summary] [--max-per-section <N>] [--no-context] [--check-stale]

参数:
  query             章节号(如 3, 7.3)、关键词(如 'DI容器')、list 或 stale
  --map, -m         知识图谱文件路径，默认 PROJECT_MAP.md
  --json, -j        JSON 格式输出
  --summary, -s     精简模式（只显示命中分布）
  --max-per-section 每章节最多显示匹配数，默认 8
  --no-context      只显示匹配行，无上下文
  --check-stale     命令前先检查鲜度（警告 → stderr）

子命令:
  stale             检查鲜度（退出码: 0=fresh, 1=stale, 2=critical）

示例:
  search_map.py list                             列出所有章节
  search_map.py stale                            检查鲜度
  search_map.py 10                               查看第10章
  search_map.py "消息队列"                         搜索关键词
  search_map.py "error" --max-per-section 3       限制匹配数
  search_map.py "接口" --no-context                无上下文搜索
  search_map.py "认证" --summary                   精简搜索
  search_map.py 6 --check-stale                   查第6章前先检查鲜度
```

所有工具零依赖，仅需 Python 3.8+。
