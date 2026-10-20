# WeChat Writer I/O Schema

## 📁 目录规范

**项目根目录**: `To-be-used/Project_[Title]/`

## 📄 核心交付物 (Artifacts)

| 阶段           | 文件名                    | 描述                                                                                              | Checkpoint        |
| :----------- | :--------------------- | :---------------------------------------------------------------------------------------------- | :---------------- |
| **Step 1**   | `01_Plan.md`           | **策划案**。<br>包含：`✨ 闪亮点`、`📍 落点`、素材摘要、`选题质检卡`、`人机边界卡`、文章结构大纲（含故事标签 `[障碍]/[行动]/[转折]/[结果]`）、主线回扣设计、`Research_Report.md` 中的事实核查表，以及固定区块 `SEO 决策卡`。<br>用途：确保方向正确、事实无误，并作为 Stage 2 / Stage 3 唯一允许消费的 SEO 输入源。 | 审核大纲结构<br>审核事实来源  |
| **Step 1.5** | `SEO_Report.md`         | **SEO 关键词报告**（Stage 1 中间产物）。<br>包含：种子词、候选词（指数/趋势/适合位置）、新词更新到积累库的记录，以及本轮 `采用 / weak-signal / skip SEO化` 的原始判断依据。<br>用途：留存调研证据；下游不得绕过 `01_Plan.md` 直接消费本文件。 |
| **Step 2**   | `02_Draft.md`          | **正文稿**。<br>包含：完整文章正文，并按 `01_Plan.md` 的 `SEO 决策卡` 自然吸收关键词约束。<br>*注：批评意见和修改指令可作为批注附在文末。*<br>用途：内容质量验收。                                 | 审核文章内容<br>检查 AI 味 |
| **Step 2.5** | `Directive_*.md`       | **综改指令**。<br>包含：主编针对初稿的修改指令。<br>用途：指导主笔进行修改。                                                    | 确认修改方向            |
| **Step 3**   | `03_Production.md`     | **制作包**。<br>包含：<br>- `金句提炼`表格（原文 → 打磨后 → 手法 → 用途）<br>- `排版设计卡`（强视觉停顿 / 开头引语 / 相关阅读）<br>- 3-5 个标题草案（3 原则 · 3 红线筛查）<br>- 最终选定标题 + slug<br>- 摘要 (Excerpt)<br>- Tags<br>并基于 `01_Plan.md` 的 `SEO 决策卡` 完成包装。<br>用途：发布前的包装准备。                         | 选定标题              |
| **Step 4**   | `published/YYYYMMDD_[Title].md` | **发布稿**。<br>包含：Frontmatter + 最终正文。文件名带日期前缀，方便识别发布顺序。                                                            | 确认归档成功            |

## 📝 草稿元数据标准 (Draft Header)

`02_Draft.md` 文件头部通常包含以下元信息引用块，用于流转追踪。**归档时将由 `archive.py` 自动根据关键词清洗**。

> **版本**: v1.0
> **主笔**: [Persona Name]
> **创建时间**: YYYY-MM-DD

---

*注意：`archive.py` 仅在检测到上述关键词时才会执行头部清洗，避免误删正文引言。*

## 🧭 `01_Plan.md` 必填区块

`01_Plan.md` 必须包含 `选题质检卡`、`人机边界卡` 与 `SEO 决策卡`。
推荐结构如下：

```markdown
## 选题质检卡

- 好奇感: 强 | 中 | 弱
- 具体钩子: ...
- 信息增量: 强 | 中 | 弱
- 新增价值: ...
- 共鸣感: 强 | 中 | 弱
- 对应读者处境: ...
- 结论: 继续 | 补素材 | 调整角度

## 人机边界卡

- 星辰 原话与亲历: ...
- AI 可辅助: ...
- 禁止虚构: ...
```

为防止 SEO 结果停留在中间产物，`SEO 决策卡` 供 Stage 2 与 Stage 3
统一消费。推荐结构：

```markdown
## SEO 决策卡

- 状态: 采用 | weak-signal | skip SEO化
- 标题主词: ...
- 正文/摘要辅助词: ...
- Tags 候选: ...
- 放置计划: 标题 / 摘要 / 开头段 / Tags
- 禁用或降级词: ...
- 备注: 查无结果 / 仅下降词 / 主题不适合 SEO 化时的原因
```

约束：
- Stage 2 / Stage 3 只允许从这里读取 SEO 约束，不直接读取 `SEO_Report.md`
- 若状态为 `skip SEO化`，标题、摘要、正文均不得为了完成流程硬塞关键词
- 若状态为 `weak-signal`，可轻量吸收稳定相关词，但不强制标题承载
- `选题质检卡` 若结论为 `补素材` 或 `调整角度`，不得直接进入 Stage 2
- `人机边界卡` 中列为 `禁止虚构` 的内容，不得出现在正文里

```markdown
## ✨ 闪亮点
> 这篇文章最亮的那个瞬间/画面/洞察是什么？（1-2 句）

## 📍 落点
> 读者读完最后一段，带走什么感觉？
```

**目标画像锚定区块**（v6.0.0 已被价值主张卡吸收，见下方）：

## 🎯 价值主张卡（v6.0.0 新增）

```markdown
## 价值主张卡

- **写给谁**：[张建国 / 陈思远 / 林小满 / 苏青 / 全向]
  （全向时，"什么场景下""什么需求"可拆为 2-3 个短句，每个画像一句）
- **ta 在什么场景下**：[一句话，具体的处境/时刻]
- **满足 ta 什么需求**：[一句话，ta 在这个场景下的内在驱动力]
- **读完能带走什么**：[一句话]
```

## 🧩 `01_Plan.md` 示例样本

若需要参考常见章节顺序与颗粒度，可查看
`references/template_01_plan.md`。

说明：
- 这是**半空白示例样本**，用于帮助 AI 或人工起草 `01_Plan.md`
- 它**不是强制模板**，章节顺序、详略和命名都可按题目调整

## 🏷️ Frontmatter 标准 (Step 4)

```yaml
---
title: "文章标题"
date: "YYYY-MM-DD"
slug: "english-slug-for-url"
excerpt: "一句话摘要，用于列表页展示"
cover: "Wechat/published/img/cover-combined.jpg"
tags: [Tag1, Tag2]
status: published
---
```

`cover` 仅用于公众号封面，脚本只会自动匹配 `cover-combined` 或
`cover-main`。若不存在则留空。`excerpt` 需在 Stage 3 控制为：建议 `<=45` 字，硬上限 `<=120` 字。

**⚠️ 格式要求**: Frontmatter `---` 结束后直接接正文第一段，不要空行，不要一级标题。

## 📝 临时文件规范

脚本输入的 JSON 文件统一放在项目目录下：
- 命名格式：`_temp_{script_name}.json`
- 脚本执行后可保留或删除（推荐保留用于调试）

## 🛠️ 脚本 I/O 契约 (Script Contracts)

为确保 AI Agent 正确调用脚本，请遵循以下 JSON 格式。

### 1. Research (`scripts/research.py`)
*   **Input**: JSON File
    ```json
    {
      "data": {
        "fact_checks": [
          { "claim": "...", "verdict": "Verified", "truth": "...", "source": "..." }
        ]
      }
    }
    ```
*   **Output**: `[Directory]/Research_Report.md`

### 3. Review (`scripts/review_toolkit.py`)

**Mode: Critique**
*   **Input**: JSON File
    ```json
    {
      "source_file": "path/to/02_Draft.md",
      "critic_persona": "罗永浩",
      "meta": {
        "score": 85,
        "verdict": "Pass",  // Pass, Needs Work, Fail
        "writing_mode": "native"  // 固定为 native（v5.0.0 唯一写作模式）
      },
      "overall_comment": "整体评价...",
      "critique_points": {
        "hard_rules": [
          { "rule": "≥800字必须有子标题结构", "status": "Pass" },
          { "rule": "子标题不超过5个", "status": "Pass" }
        ],
        "structure_check": {
          "word_count": 1200,
          "subtitle_count": 3,
          "structure_compliant": true
        },
        "style_consistency": [
          { "check_item": "体感叙事五锚点", "finding": "感官锚+读者锚覆盖完整" },
          { "check_item": "开头检查", "finding": "从具体场景切入，符合原生模式" }
        ],
        "logic_flaws": [
          { "point": "逻辑不通...", "severity": "High" }
        ],
        "ai_smell": {
            "score": 90,
            "evidence": ["滥用'综上所述'", "缺乏细节"]
        },
        "content_depth": {
            "status": "Needs Work",
            "score": 75,
            "evidence": ["第二节观点缺少具体场景支撑"],
            "priorities": ["补一个来自原始素材的真实动作"]
        },
        "xingchen_layer": {
            "status": "Pass",
            "score": 88,
            "evidence": ["整体像第一人称分享，没有营销腔"],
            "priorities": []
        }
      }
    }
    ```
*   **Output**: `[Critique_Report]*.md`

**Mode: Directive**
*   **Input**: JSON File
    ```json
    {
      "title": "Article Title",
      "status": "PENDING",
      "conflict_resolution": { "has_conflict": false, "details": "" },
      "critique_summary": [
          { "source": "罗永浩", "point": "逻辑漏洞", "action": "修改第三段" }
      ],
      "editorial_suggestions": [
        { "original": "...", "suggestion": "..." }
      ]
    }
    ```
*   **Output**: `Directive_*.md`

**Mode: Feedback**
*   **Input**: JSON File
    ```json
    {
      "overall_verdict": "Pass",
      "best_quote": "...",
      "tests": {
        "click_test": { "decision": "Yes", "reason": "..." },
        "finish_test": { "decision": "Yes", "drop_point": "..." }
      }
    }
    ```
*   **Output**: `[User_Feedback]*.md`

### 4.5 Format (`scripts/format.py`)

*   **Input**: JSON File
    ```json
    {
      "draft_file": "published/YYYYMMDD_[Title].md",
      "production_file": "conductor/archive/YYYYMMDD_[Title]/03_Production.md",
      "output_path": "published/YYYYMMDD_Title.html"
    }
    ```
    - `draft_file`: 发布版正文 Markdown 源文件（`published/YYYYMMDD_[Title].md`，已由 archive.py 追加 footer 和 frontmatter）。**必须在 archive.py 之后运行**，确保 footer 为最新版本。
    - `production_file`: 归档后的 Stage 3 产出（`conductor/archive/.../03_Production.md`），含金句表格和排版设计卡。若不存在则跳过金句渲染和排版设计卡。
    - `output_path`: 输出 HTML 路径，命名规则 `{date_prefix}_{safe_title}.html`，与 archive.py 一致
*   **Output**:
    1. `{output_path}` — 含 inline style 的完整 HTML 文件，浏览器打开后 Ctrl+A → Ctrl+C → 粘贴到微信编辑器
    2. 终端输出：金句/排版设计卡加载摘要 + 图片插入清单
*   **渲染规则**: 品牌色 `#FF6B35`，行间距 1.75，段后距 10px。详见 `docs/superpowers/specs/2026-06-17-stage3-typography-design.md`

### 4. Archive (`scripts/archive.py`)
*   **Input**: JSON File
    ```json
    {
      "source_file": "path/to/02_Draft.md", 
      "frontmatter": {
        "title": "Final Title",
        "slug": "url-slug",
        "tags": ["tag1"],
        "excerpt": "Summary...",
        "cover": "Wechat/published/img/cover-combined.jpg"
      },
    }
    ```
    `card` 为可选字段。当提供时，archive.py 会在归档时自动生成 L2 文章索引卡（`knowledge/article_cards/Card_YYYYMMDD_Title.md`）并以宽格式更新 L1 索引。不提供时行为不变。

    完整 schema 见 `docs/superpowers/specs/2026-06-24-article-index-card-design.md`。
    
    ```json
    "card": {
      "series": "微习惯系列",
      "writing_mode": "原生",
      "article_type": "方法论文",
      "core_insight": "微习惯三步法只是种下种子...",
      "key_scenes": ["教练对话中的画面浮现"],
      "metaphor_system": "种子→破土→阳光→花园",
      "characters": [],
      "framework": "进阶三要素：灯塔→阳光→舒适区边缘",
      "title_design": {
        "selected": { "path": "场景代入", "title": "...", "c": 5, "e": 5, "v": 2 },
        "alternative_paths": ["列新奇反问", "包装核心观点"]
      },
      "golden_quotes": ["金句1", "金句2"],
      "image_plan": [
        { "seq": 1, "theme": "走向灯塔", "position": "第一节后", "has_ip": true, "ip_style": "星辰剪影" }
      ]
    }
    ```

*   **Output**: 
    1. `published/[Title].md` (Final Article)
    2. Moved Project to `conductor/archive/YYYYMMDD_[Title]/`
    3. Move project `img/` to fixed path `published/img` (old one backed up as `img_prev_*`)
    4. If `frontmatter.cover` is empty, auto-pick from `published/img` by:
       `cover-combined` > `cover-main` (no other fallback)

### 5. 选题雷达候选池 (`knowledge/topic_radar_pool.md`)

**用途**：`wechat-daily` 扫描 `diary/`（原始日记）和自己的已发内容，把有深挖价值的素材写成候选，供 `wechat-writer` 消费。这是一份持续累积的 Markdown 文件，不是脚本输入/输出，由 Agent 直接 Read/Edit，没有 JSON 契约。

**结构**（两个区块，固定标题，按需追加条目）：

```markdown
## 选题候选（供 writer 深挖）
### [YYYY-MM-DD] 候选：<一句话概括>
- 来源: <diary/YYYY-MM-DD.md 或 daily 文章文件名>
- 方向: <教练技术 / 微习惯 / 正念冥想 / 技术思维应用，可多选>
- 成熟度: <"够成熟，可直接写" 或 "有苗头，缺XX → 建议访谈">
- 状态: 待选 | 已完成（关联：<产出文章文件名>）

## 素材库候选（待批量整理进素材库.md）
- [YYYY-MM-DD] 隐喻苗头/可复用金句/方法论苗头："<内容>" —— 来源：<daily YYYYMMDD 文章>
```

**读写分工**：

| 动作 | 执行方 | 时机 |
|------|--------|------|
| 追加候选（选题候选 / 素材库候选） | `wechat-daily` | `/daily` 流程顺带执行，按"来源"字段去重，不重复扫描同一天素材 |
| 查看候选池 | 用户 | 随时，直接问"最近雷达发现了什么" |
| 按成熟度分流入口 | `wechat-writer` | `/interview` `/write` 启动时 |
| 标记候选"已完成"并关联产出文章 | `wechat-writer` | Stage 4 归档时，把对应条目的"状态"改为"已完成（关联：...）" |
| 批量整理"素材库候选"进 `素材库.md` | `wechat-writer` | 建议每两周一次，整理后从候选池清除已归位的条目 |
