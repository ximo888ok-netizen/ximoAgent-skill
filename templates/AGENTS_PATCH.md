# AGENTS.md 补丁片段

> 以下内容需添加到目标项目的 AGENTS.md 中。
> 章节编号根据目标项目 AGENTS.md 现有结构调整。

---

## X. 渐进式读取原则（核心铁律）

**在修改任何代码前，用最小代价获取所需信息。永远不要用 `read_file` 做 `outline` 或 `lsp_symbols` 能做的事。**

### 读取阶梯（按优先级从低到高）

| 优先级 | 工具 | Token 成本 | 适用场景 |
|--------|------|-----------|---------|
| 1 | `python scripts/outline.py <file>` | ~100-300 | 了解文件有哪些函数/类 |
| 2 | `python scripts/search_map.py <章节>` | ~200-400 | 了解项目架构/模块/API |
| 3 | `python scripts/search_map.py "关键词"` | ~300-500 | 搜索特定主题 |
| 4 | `read_file <file> --offset=N --limit=M` | ~500-1500 | 只看需要的函数实现 |
| 5 | `read_file <file>`（全文件） | ~1500-5000 | 需要完整理解时（最后手段） |

### 标准修改工作流

```
1. outline.py <target_file>               ← 100 token，看有哪些函数
2. 判断范围：
   - 新增函数 → 直接编辑（只需看 outline 确认位置）
   - 修改现有函数 → read_file offset/limit 只看该函数
   - 重构/大改 → read_file 全文件
3. edit_file                               ← 精准修改
4. bash <test>                             ← 跑相关测试验证
5. read_file（仅验证变更部分）             ← 确认，可用 git diff 替代
```

### 反模式（禁止行为）

- ❌ 上来就读整个文件（除非明确需要全文件理解）
- ❌ 用 `read_file` 浏览目录（用 `outline.py --recursive --summary` 替代）
- ❌ 用 `grep` 搜索后直接 `read_file` 每个匹配文件（先 `outline` 筛选）

---

## Y. 项目结构检索（动手前必读）

**在修改任何代码前，先用检索工具了解项目结构，避免盲目猜测。**

### 快速索引（首选）

项目结构化索引位于 `index.json`（机器可读，由 `gen_index.py` 自动生成）：

```
python scripts/gen_index.py --check         # 检查索引鲜度
python scripts/gen_index.py                 # 重新生成索引
cat index.json | python -m json.tool        # 查看索引内容
```

`index.json` 包含：包/目录结构、每目录导出符号、入口点、git 热点文件、项目统计。

### 知识图谱（详细参考）

项目知识图谱位于 `PROJECT_MAP.md`（10 章，覆盖架构/目录/依赖/流程/数据模型/API/风险禁忌）。
**不要直接读取整个文件**（浪费 token），使用检索工具按需查询：

```
python scripts/search_map.py list              # 列出所有章节（先运行这个了解全貌）
python scripts/search_map.py stale             # 检查图谱是否过期（每次必做）
python scripts/search_map.py 10                # 强制先读第10章「已知风险与禁忌」
python scripts/search_map.py 2                 # 查看第2章「目录结构」完整内容
python scripts/search_map.py "关键词"           # 按关键词搜索相关章节
python scripts/search_map.py "关键词" --summary # 精简搜索（只看命中分布）
python scripts/search_map.py "关键词" --max-per-section 3  # 限制每章节显示数
```

### 文件大纲（精准阅读前必备）

```
python scripts/outline.py src/service/user.go              # 单文件大纲
python scripts/outline.py src/service/ --recursive          # 递归扫描目录
python scripts/outline.py src/service/ --summary            # 只看文件级统计
python scripts/outline.py src/main.py --json                # JSON 输出（机器可读）
python scripts/outline.py src/main.py --kind=func           # 只看函数
```

### 强制工作流（每次修改前）

1. `gen_index.py --check` 或 `search_map.py stale` → 确认索引/图谱新鲜度
2. `outline.py <target_file>` → 了解文件结构（省 85-95% token vs 读全文件）
3. `search_map.py 10` → **强制先读第 10 章**（已知风险与禁忌）
4. 按需 `search_map.py <章节>` 或 `search_map.py "关键词"` → 查架构/API
5. `read_file offset/limit` → 只读需要的部分
6. **动手前 Read 实际代码确认**（地图是线索，不是事实）

### 信任原则

- `[★ 人工维护]` 章节 → 高度可信（人工策划的架构决策和风险提示）
- `[⚙ 自动生成]` 章节 → 仅供参考（可能已过时，务必 Read 代码验证）
- `index.json` → 机器生成的结构化索引，比 Markdown 地图更新更及时
- **过期地图比没有地图更危险** → 始终以实际代码为最终事实来源

---

## Z. 知识图谱同步

**任何项目变动完成后，立即更新 `PROJECT_MAP.md` 和/或 `index.json`。**

### 快速同步（自动）

代码变更后运行 `gen_index.py` 自动刷新 `index.json`：

```
python scripts/gen_index.py    # 重新生成结构化索引
```

### 精确同步（手动）

根据变更类型更新 `PROJECT_MAP.md` 对应章节：

| 变更类型 | 需同步的章节 |
|---------|------------|
| 新增/删除文件 | 第2章 目录结构 [auto-generated] |
| 修改架构/分层 | 第1章 架构层次、第3章 模块依赖 |
| 新增/修改 API | 第7章 API 接口定义 |
| 修改数据模型 | 第6章 数据模型 [auto-generated] |
| 新增/修改工具/插件 | 第8章 项目特有章节 |
| 修复已知风险 | 第10章 已知风险与禁忌 [curated]（移除已修复项） |
| 新增依赖 | 第9章 技术栈组件 [auto-generated] |
| 修改核心流程 | 第4章 核心业务流程、第5章 关键函数调用链 |

同步后更新文件末尾的"最后更新"日期。

### 章节标记规范

- 核心章节（第4/8/10 章）标题末尾加 `[curated]`
- 可由工具辅助更新的章节（第2/6/9 章）标题末尾加 `[auto-generated]`
- 无标记 = 混合维护

---

## 工具速查表

| 工具 | 命令 | 作用 |
|------|------|------|
| `gen_index.py` | `python scripts/gen_index.py` | 生成/刷新 index.json |
| `gen_index.py --check` | `python scripts/gen_index.py --check` | 检查索引鲜度 |
| `outline.py` | `python scripts/outline.py <file>` | 文件大纲（省 85-95% token） |
| `outline.py --recursive --summary` | `python scripts/outline.py src/ -r -s` | 目录级统计 |
| `search_map.py list` | `python scripts/search_map.py list` | 列出知识图谱章节 |
| `search_map.py stale` | `python scripts/search_map.py stale` | 检查图谱鲜度 |
| `search_map.py <N>` | `python scripts/search_map.py 6` | 查看第 N 章 |
| `search_map.py "关键词"` | `python scripts/search_map.py "认证"` | 搜索关键词 |
