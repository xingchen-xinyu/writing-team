---
name: wechat-daily
version: 2.5.1-xingchen
description: wechat-daily「生活中的美好」轻量日更 Skill。命令入口 /daily，4 步轻量流程、写作计划驱动成文、check_draft.py 过程验证、反哺 wechat-writer 选题雷达。
triggers:
  - /daily
  - /日常
parameters:
  - name: content
    type: string
    required: false
    description: 当天素材（日记片段/口述），省略则由 Agent 引导用户补充
---
# wechat-daily 轻日更系统 (WeChat Daily) v2.5.1

**核心定位**：记录生活中的美好——日行一善、美好时光、读书分享、学习实践感悟。素材现成就跑，没有就不跑，不追求深度，追求"能坚持"。

## 4 步流程总览

| 步骤 | 做什么 | 用户确认 | 产出 |
|------|--------|----------|------|
| **Step 0** 素材采集 + 写作计划 | 读 `diary/` 或口头输入 → 构思具体 3 拍框架 → 写 `Plan.md` | 无（框架好不好留到 Step 1 看真实文字判断） | `diary/YYYY-MM-DD.md`（或 `.txt`） + `Plan.md` |
| **Step 1** 成文 + 用户确认 | 按 `Plan.md` 写作 → 金句识别 → L1 自查（11 条）→ 落盘 → `check_draft.py` 验证 → **只告知路径不输出全文** | ★ 唯一门禁：草稿确认 | `To-be-used/Project_Daily_标题/Draft.md` + `_temp_daily.json` |
| **Step 2** 配图 | 直接选模式 A/B/C，跳过是否配图的确认。**模式 A 时 Part A 根据内容判断 IP 形象**：画面主体是作者本人 → `IP: Yes`；抽象概念/纯物体/第三方 → `IP: No` | 模式选择 | `img/` + `Storyboard.md` |
| **Step 3** 发布 + 选题雷达 | `archive_daily.py` 一键 → 扫描 `diary/` → 追加候选 | 无 | `published/` + HTML + 索引 + 归档 + `topic_radar_pool.md` |

**写作核心规则**：以下规则在 Step 1 写作和自查时**必须执行**，不是参考建议。

### 子标题

文章超过 **500 字**时，至少设计 1-2 个子标题（`##` 格式，2-6 个字）。500 字以下如有明显层次递进也可加。判断标准是**内容结构**，不只是字数。Step 0 的 Plan.md 须写入子标题候选。

### 结构连贯性

写完 3 拍框架后自问：这三拍从头到尾同一个人在说话吗？

**禁止的断裂**：
- 前两拍"我看到了/想到了"，第三拍跳成"你应该"
- 素材里的指令型内容（"盘点自己""聚焦需求""从今天开始做X"）原封不动搬进文章 → 上课感

**修复**：指令型内容用技法 6 转换成"我在想/在试X"的个人思考口吻，不能直接对读者下指令。

### ⛔ L1 自查 11 条（逐条过，不过就改）

| # | 检查项 | 怎么查 |
|---|--------|--------|
| 1 | **禁词** | 「说白了」「本质上」「值得注意的是」「不可否认」「毋庸置疑」「总而言之」「情绪价值」「狠狠」？→ 删/换 |
| 2 | **冒号** | 正文中有中文冒号「：」？→ 改逗号或分句。标题中除外 |
| 3 | **破折号** | ≥ 3 个「——」？→ 删到 2 个以内 |
| 4 | **排比对仗** | 「A 不是 B，是 C」式排比？→ 拆掉 |
| 5 | **人机边界** | 编造了素材中没有的场景细节、对话、观点？→ 删 |
| 6 | **朗读感** | 像说话还是像写稿？→ 像写稿就改，找两处句号改逗号 |
| 7 | **金句自检** | 有 1-3 句值得标记？→ 写入 `gold_quotes`。没有就不填 |
| 8 | **日记对照** | 三维度：① 内容——有没有日记里没有的概括/放大冲突？② 语气——人称、态度变了没？③ 氛围退化——有没有把具体行为替换成「气氛」「氛围」等抽象判断？→ 有就改回具体行为 |
| 9 | **美感自检** | 挑改动最大的一句，说出用了哪条润色技法、为什么改后更好。说不出来 → 换一条真正有效的技法重新润色 |
| 10 | **结构连贯** | 读前三段和后三段——同一篇文章、同一个人吗？有没有突然从"我"跳到"你该"？→ 有就回 Plan 重定主线 |
| 11 | **指令口气** | 有没有直接搬日记的「你应该/你可以/邀请你/盘点一下/聚焦一个/从今天开始做X」？→ 用技法 6 转换成"我在想/在试X" |

> 第 1-6、8-11 条不通过 → 就地修改 → 再查 → 通过才落盘。第 7 条没有就不填，不算不通过。

### 润色技法速查

**技法 1**：抽象感受 → 具体动作/感官。日记"很感动"→"脑后一阵发麻"（细节素材里确实有才用）。

**技法 6**：日记指令 → 个人思考。日记"盘点你的需求"→"我试着盘了一下"。日记"从今天开始做调整"→"我在想，能不能先做一小步"。核心：把"你"换成"我"，把指令换成思考过程。

> 三种写作框架（画面型/引句型/心路型）、完整技法清单、Step 2-3 详细流程见 `references/` 目录。

## 目录结构

```
diary/                              # 原始日记（Step 0 写入，支持 .md / .txt）
  YYYY-MM-DD.md

To-be-used/Project_Daily_标题/      # 进行中的项目（Step 0-2）
  Plan.md                           # (Step 0) 写作计划：3 拍框架落地，Agent 自用参考，纯文档不接入脚本、不等用户确认
  Draft.md                          # 正文草稿
  _temp_daily.json                  # archive_daily.py 输入
  img/                              # (Step 2 可选) 配图
  Storyboard.md                     # (Step 2 可选) 分镜

published/                          # 发布成品（与 writer 共享目录）
  YYYYMMDD_标题.md                  # 发布稿（含 frontmatter + bio footer）
  YYYYMMDD_标题.html                # 微信编辑器 HTML
  img/                              # 封面图
  history/YYYY-MM/                  # 历史文件自动归档

conductor/archive/                  # 项目归档（与 writer 共享目录）
  YYYYMMDD_Daily_标题/              # Step 3 发布后从 To-be-used 移入
    Plan.md
    Draft.md
    Storyboard.md
    img/
```

## 与 wechat-writer 的关系

- `wechat-writer`（`/interview` `/write`）：每周 1-2 篇深度文章，6 角色协同、5 阶段门禁
- `wechat-daily`（`/daily`）：每天轻量记录，写作计划驱动成文
- **共享**：`published/` 发布目录、`conductor/archive/` 归档目录、`wechat-director` 生图引擎、`wechat-writer/knowledge/` 知识库、`wechat-writer/references/bio_footer.md` 脚注
- **反哺**：`/daily` 每次运行扫描 `diary/`，把深挖候选写入 `wechat-writer/knowledge/topic_radar_pool.md`

## 脚本工具箱

| 脚本 | 功能 | 用法 |
|------|------|------|
| `scripts/check_draft.py` | Step 1 过程验证：Draft.md/_temp_daily.json 存在性 + 格式 + 必填字段 | `python .claude/skills/wechat-daily/scripts/check_draft.py <项目目录>` |
| `scripts/archive_daily.py` | 发布：写 Markdown + bio footer、生成 HTML、更新 daily 索引、项目归档、历史清理 | `python .claude/skills/wechat-daily/scripts/archive_daily.py <json路径>` |
| `scripts/draw_daily.py` | 配图包装，复用 `wechat-director` 的生图引擎 | 见 `references/daily_beauty_routine.md`「Step 2」 |

> **Windows 环境**：所有 Python 命令加 `PYTHONIOENCODING=utf-8` 前缀。脚本必须从仓库根目录调用。
