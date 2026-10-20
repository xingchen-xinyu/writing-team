# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

微信公众号写作 + 轻日更 + 配图 AI Skill 组合。包含三个 Skill：**wechat-writer**（深度写作）、**wechat-daily**（轻日更）和 **wechat-director**（配图生成）。Skill 入口文件为各目录下的 `SKILL.md`，由 Claude Code 自动识别。

当前版本：**wechat-writer v6.0.0-xingchen** / **wechat-daily v2.5.1-xingchen**。writer 升级为 6 角色协同（+李长征·研究员）、价值主张驱动、子 Agent 并行；daily 提供 5 步轻量流程，产出反哺 writer 的选题雷达候选池。

## 核心概念

### 三种入口

| 入口 | 场景 | 对应 Skill |
|------|------|-----------|
| `/daily` | 记录生活中的美好，轻量日更 | wechat-daily |
| `/interview "话题"` | 有想法，需要梳理 | wechat-writer |
| `/write "标题"` | 已有素材或标题，深度文章 | wechat-writer |

### wechat-writer：深度写作

所有文章均为**原生模式**：个人经历/体感为核心，外部素材零引入或仅点缀。主线：体感 → 反思 → 回到体感。

**6 角色协同**：首席记者 (Lyra) → 研究员 (李长征) → 主编 (呼延雷锋) → 主笔 (冰清) → 顾问 (罗永浩) → 制作人 (马可婷)

**5 阶段门禁**：Stage 0 (Interview) → Stage 1 (Plan) → Stage 2 (Draft) → Stage 3 (Production) → Stage 4 (Archive)

### wechat-daily：轻日更

记录生活中的美好——日行一善、美好时光、读书分享、学习实践感悟。素材现成就跑，没有就不跑，不追求深度，追求"能坚持"。

**5 步轻量流程**：Step 0 (素材采集) → Step 1 (成文) → Step 2 (用户确认 ★ 核心门禁) → Step 3 (配图·可选) → Step 4 (发布) → Step 5 (选题雷达扫描)

**与 writer 的关系**：
- daily 共用 writer 的共享知识库（style_guide / ai_smell_guide / team_memory 等）和 director 的生图引擎
- daily 每次运行顺带扫描 `diary/`，把有深挖价值的候选写入 `topic_radar_pool.md`，供 writer 启动时消费
- writer 通过 **Diary 桥接**：用户说"用日记写深度文章"时，直接从 `diary/` 读取素材进入 Stage 1

## 目录结构

```
.claude/skills/wechat-writer/   # 写作 Skill（主入口）
  SKILL.md                      # Skill 触发点，定义 triggers 和完整工作流
  scripts/                      # Python 渲染工具（纯格式化，不含 LLM 调用）
    config_check.py             # 环境检测
    cleaner.py                  # 素材清洗 → Cleaned_*.md
    research.py                 # 调研报告格式化 → Research_Report.md
    review_toolkit.py           # 审校报告渲染（3 种模式）→ [Critique_Report]*.md / Directive_*.md
    format.py                   # Markdown → 微信编辑器 HTML
    archive.py                  # 归档发布 → published/*.md + 更新索引 + 生成文章卡片
  references/                   # 角色定义、模板、SOP
    core_personas.md            # 6 大核心角色人设详情
    routine_plan.md             # Stage 1 策划完整操作步骤
    template_01_plan.md         # 01_Plan 半空白示例样本
    title_design_checklist.md   # 标题设计清单（5 路径 + C/E/V 三维评分）
    bio_footer.md               # 文末个人 IP 介绍文案
    io_schema.md                # 交付文件 + 脚本 I/O 契约
  knowledge/                    # 静态知识库
    style_guide.md              # 星辰个人写作风格（体感叙事五锚点 + 氛围感三技法 + 主笔工具箱）
    ai_smell_guide.md           # 去 AI 味审校清单（L1-L4 四层校验）
    brand_positioning.md        # 编码人生.lab 品牌定位
    team_memory.md              # 团队记忆与踩坑记录
    published_article_index.md  # 已发布文章索引
    wechat_index_keywords.md    # 微信指数关键词积累库
    素材库.md                    # 私有灵感、金句、碎片观察
  tests/                        # test_archive.py + test_review_toolkit.py

.claude/skills/wechat-daily/     # 轻日更 Skill
  SKILL.md                      # Skill 触发点，定义 triggers 和 5 步流程
  scripts/
    archive_daily.py            # 发布轻量文章 → published/ + HTML + 索引 + 归档 + 历史清理
    draw_daily.py               # 配图轻量包装（复用 wechat-director 引擎）
  references/
    daily_beauty_routine.md     # 5 步完整流程、写作要求、脚本契约
  tests/                        # test_archive_daily.py

.claude/skills/wechat-director/ # 配图 Skill
  SKILL.md                      # Skill 触发点
  scripts/
    config_check.py             # 检测生图 provider 配置
    visualize.py                # 批量生图 → 压缩 → 上传 COS → 注入正文
  references/
  assets/IP_Reference.png       # IP 形象参考图（用于保持角色一致性）

conductor/api_keys.json         # API 密钥配置（不入 git，需用户自行创建）
```

## 脚本调用模式

所有 Python 脚本采用**纯渲染器**模式（cleaner/research/review_toolkit）——不做 LLM 调用，只将 JSON 输入渲染为 Markdown 文件。JSON 由调用方（Agent/LLM）生成，脚本仅负责格式化落盘。`archive.py` 和 `visualize.py` 例外，它们包含文件系统操作和外部服务调用。

| 脚本 | 用法 |
|------|------|
| `config_check.py` | `python .claude/skills/wechat-writer/scripts/config_check.py` |
| `cleaner.py` | `python .claude/skills/wechat-writer/scripts/cleaner.py /path/to/_temp_cleaner.json` |
| `research.py` | `python .claude/skills/wechat-writer/scripts/research.py /path/to/_temp_research.json` |
| `review_toolkit.py` | `python .claude/skills/wechat-writer/scripts/review_toolkit.py --mode critique\|directive\|feedback /path/to/_temp_*.json` |
| `archive.py` | `python .claude/skills/wechat-writer/scripts/archive.py /path/to/_temp_archive.json` |
| `archive_daily.py` | `python .claude/skills/wechat-daily/scripts/archive_daily.py /path/to/_temp_daily.json` |
| `visualize.py` | `python .claude/skills/wechat-director/scripts/visualize.py --brief Storyboard.md --draft Draft.md` |

JSON 输入格式详见 `references/io_schema.md`。输出文件落在输入 JSON 同目录（即项目目录 `To-be-used/Project_[Title]/`）。

**重要**：所有脚本必须从**仓库根目录**调用，脚本路径和 JSON 路径都相对于根目录。如果 shell 的 CWD 不在根目录，请使用绝对路径或先 `cd` 回根目录。

> **Windows 环境注意**: 本机 `python3` 被 Windows App Execution Alias 拦截（exit code 49），所有 Python 命令请使用 `python` 而非 `python3`。Windows 控制台默认 GBK 编码会导致 emoji/中文输出报 `UnicodeEncodeError`，所有 `python` 和 `python -c` 命令请加 `PYTHONIOENCODING=utf-8` 前缀：
> ```
> PYTHONIOENCODING=utf-8 python .claude/skills/wechat-writer/scripts/review_toolkit.py --mode critique /path/to/_temp.json
> ```

## 工作目录约定

- **原始日记**: `diary/YYYY-MM-DD.md`（纯文本，无 frontmatter，daily 和 writer 的共同素材源）
- **进行中的 writer 项目**: `To-be-used/Project_[Title]/`
- **进行中的 daily 项目**: `To-be-used/Project_Daily_标题/`
- **发布成品**: `published/YYYYMMDD_[Title].md`（writer 和 daily 共用此目录）
- **归档**: `conductor/archive/YYYYMMDD_[Title]/`（writer）/ `conductor/archive/YYYYMMDD_Daily_标题/`（daily）
- **图片**: 项目 `img/` 目录 → 发布时移到 `published/img/`
- **历史清理**: `published/` 和 `diary/` 中非当天的文件 → 自动移入 `history/YYYY-MM/`
- **目录先于文件**: 往项目目录复制文件前，先用 `mkdir -p` 确保目标目录存在，再执行 `cp`。不要写成 `cp xxx newdir/ && mkdir -p newdir`，目录不存在时 cp 会失败且 mkdir 不会执行

## 工作流

### wechat-writer（深度文章）

Stage 0 (Interview) → Stage 1 (Plan) → Stage 2 (Draft) → Stage 3 (Production) → Stage 4 (Archive)

可通过 `/write "Title" --from-stage N` 从任意阶段继续。

### wechat-daily（轻日更）

Step 0 (素材采集) → Step 1 (成文) → Step 2 (用户确认 ★ 唯一人工门禁) → Step 3 (配图·可选) → Step 4 (发布归档) → Step 5 (选题雷达)

详细流程见 `references/daily_beauty_routine.md`。

## 开发相关

- Python 3.8+，无 requirements.txt，依赖均为可选（Pillow、tinify、cos-sdk）
- 运行测试:
  - `python -m pytest .claude/skills/wechat-writer/tests/test_archive.py -v`
  - `python -m pytest .claude/skills/wechat-writer/tests/test_review_toolkit.py -v`
  - `python -m pytest .claude/skills/wechat-daily/tests/test_archive_daily.py -v`
- 仓库预期作为 Obsidian vault 使用（脚本会通过 `.obsidian/` 目录检测 vault 根路径）
