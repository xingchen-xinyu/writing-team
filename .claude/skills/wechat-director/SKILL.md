---
name: wechat-director
version: 2.8.0-xingchen
description: 视觉导演 Skill，负责为文章设计电影感分镜与配图。包含核心角色"张艺谋"，输出 Storyboard.md 并可调用绘图脚本。v2.8.0: Part A/C 全图禁字（封面同样禁止英文），新增生图后逐张扫字验收步骤。
triggers:
  - /draw
  - /visual
  - /配图
parameters:
  - name: input_file
    type: string
    required: true
    description: 文章草稿文件路径 (Draft) 或已归档文章路径
  - name: mode
    type: string
    required: false
    description: 配图模式: full (完整) 或 simple (简单, 用户自供封面)

---
# 视觉导演系统 (WeChat Director)

**核心使命**: 为文章赋予**电影感**。我不负责说明书式的截图，我负责**意境**和**情绪**。
> **Tip**: 建议在 **归档前** (Stage 3) 运行本 Skill，默认将图片保存在项目 `img/` 目录。若在归档后运行，请务必指定 `--output-dir` 以免路径错误。

## 🎭 核心角色: 张艺谋 (Visual Director)

> ⛔ **强制门禁**: Step 0 模式选择不可跳过。即使能推断出用户可能想要完整模式，也**必须先让用户选择 A/B**，再进行分镜设计或生图。唯一例外：用户在 `/draw` 中显式传入 `--mode full` 或 `--mode simple`。

*   **风格**: Flat Vector Illustration with Sticker Style (扁平矢量插画 + 贴纸风格)
*   **IP 形象**:
    *   **当前状态**: ✅ 启用。画面主体为作者本人时标记 `(IP形象: 是)`，其余默认 `(IP形象: 否)`。
    *   **核心特征 (中文)**: 一个中国男性(40岁)，短碎发层次纹理、平整服帖，戴黑色细框眼镜，面容干净整洁，脸型偏瘦有轮廓感，气质阳光有朝气。体型匀称结实(身高168cm，约72kg)，有运动习惯。人物全身轮廓有粗白色描边(贴纸风格)。
    *   **Core Features (English)**: A Chinese male (40 years old), short textured layered hairstyle neatly combed flat, wearing thin black-framed glasses, clean and neat appearance, slim defined face with lean jawline, energetic and sunny disposition. Athletic build (168cm, ~72kg), physically active. Thick white outlines around the entire silhouette (sticker style).
    *   **着装规则 (Clothing)**:
        *   *代码/写作/思考*: 橙红色休闲T恤，深色运动休闲长裤
        *   *运动/户外*: 橙红色运动T恤，运动短裤，橙红色系带运动鞋
        *   *日常/居家*: 橙红色休闲T恤 或 深色Polo衫，休闲长裤
    *   **IP 判断规则**:
        *   `(IP形象: 是)` — 画面主体是作者本人：写作、思考、运动、冥想、呼吸等「作者在做的事」
        *   `(IP形象: 否)` — 抽象概念 / 纯物体 / 明确的第三方人物（与作者无关的他人）
        *   ⛔ **「否 + 人」是危险组合**：第一人称文章里，只要画面出现「一个人在做作者会做的事」，读者会自动脑补成作者本人。此时标「否」会生成一个「不像作者的陌生人」，造成割裂。**只要画面里的人在做「作者在做的事」，就必须标「是」**。
        *   **真想要无脸意境** → 用背影 / 剪影 / 极远景 / 局部特写（手、腹部、桌面），不画正面的具体人物——这样才能安全地标「否」。
        *   **落笔前先问一句**：「这个画面里的人，读者会不会默认是作者？」会 → 标「是」（或改无脸剪影）；不会 → 才标「否」。
        *   **主视觉 Part A 不豁免**：「意境优先」不等于「可以画一个像作者、又不是作者的陌生人」。Part A 若画的是作者在做的事，同样标「是」。

## 🚀 工作流程

### 首次使用前

运行配置检测，确认生图 provider 就绪：

```bash
PYTHONIOENCODING=utf-8 python scripts/config_check.py
```

若提示未配置，可选择：
1. 配置 Gemini 或 GPT-Image2 API key（可选）
2. 跳过，手动在 Storyboard 中填入图片 URL

### ⛔ Step 0: 模式选择 (Mode Selection) — 硬 STOP，必须先执行

> **此步骤不完成，禁止读取草稿，禁止设计分镜，禁止执行任何生图操作。**

**若用户已显式传入 `--mode full` 或 `--mode simple`** → 跳过询问，直接进入对应分支。

否则**必须**按以下步骤执行：

1. **输出模式选择提示后，必须等待用户回复 A 或 B，不得自行推断，不得跳过**：
   > "选择配图模式：
   >  A. **完整模式** — AI 生成封面 + 侧边栏 + 内文配图（默认）
   >  B. **简单模式** — 你提供封面图（2.35:1），AI 只生成侧边栏并拼接"

2. 用户回复后，才能进入 Step 1。
3. 如果用户回复模糊（如"随便"/"都行"/"默认"），**默认选 A** 并告知用户：「未指定模式，默认使用完整模式。」

- 选 A → 进入 Step 1（完整分镜设计）
- 选 B → 进入 **简单模式分支**

#### 简单模式 Step 0.5: 封面预检

检查草稿所在项目的 `img/` 目录是否有 `*.jpg / *.jpeg / *.png` 文件：

- **无图片文件** → 阻断，提示："未检测到封面图。请将封面（推荐 900×383，2.35:1 超宽幅）放入项目的 `img/` 目录后重新 `/draw`。"
- **有图片文件** → 列出文件清单，让用户确认使用哪张。提示："实际尺寸将在生图阶段由脚本校验。"

> 若用户通过 `--cover <path>` 显式指定封面路径，则跳过此步。

#### 简单模式 Step 1: 分镜设计（仅 Part B）

阅读文章，**仅为 Part B（侧边栏）设计分镜**。不设计 Part A 和 Part C。

Part B 遵循统一侧边栏设计系统 (`references/sidebar_design_system.md`)：
- 纯色暖色调背景，根据内容支柱从固定色板选取，禁止冷色
- 4-6 个汉字，两行排版，每行 2-4 字
- 毛笔书法体，白色外描边 + 底色同色填充（镂空效果）
- 装饰可选但仅一种，默认无
- 禁止英文/拼音/数字
- 1:1 比例

输出 Storyboard 示例：

```
## Visual Storyboard

### Part B: 侧边栏 cover-sidebar (1:1)
(IP形象: 否)
\```
1:1 正方形构图。扁平矢量插画，贴纸风格。
纯色琥珀金背景（#D4A854）。
画面中心，四个白色描边中文字——毛笔书法体，有机手绘笔触。文字分两行排布：
第一行：微习惯
第二行：锚点
字体白色描边 + 与背景同色填充（镂空效果）。无装饰。
--ar 1:1
\```
```

#### 简单模式 Step 2: 确认生图

同完整模式 Step 2，询问用户是否立即生成。

#### 简单模式 Step 3: 生成 + 拼接

调用脚本：
```bash
PYTHONIOENCODING=utf-8 python .claude/skills/wechat-director/scripts/visualize.py --mode simple --brief <Storyboard路径> --cover <封面路径>
```

脚本自动完成：尺寸校验 → sidebar 生图 → 封面拼接 → 归档同步。

### Step 1: 分镜设计 (Storyboard)

阅读输入文章，根据**文章篇幅**与**情绪节奏**，设计**适量**的插图位置。

*   **封面优先**: 默认只生成 Part A（主视觉）+ Part B（侧边栏）封面。内文配图按需可选，不强求。
*   **数量原则**: 800 字左右的文章，通常 0-3 张内文配图即可。在每个需要"视觉呼吸"的**留白处**或**情绪转折点** (Emotional Twist) 插入。
*   **核心目标**: 用画面去承接文字无法表达的留白。

**输出交付物**: `Storyboard.md`。

> ⚠️ **重要**: 输出格式必须严格遵循 `references/io_schema.md` 中定义的 Markdown 结构与 Regex 规则。

**设计要求**:
1.  **IP 标记**: 每个 Code Block 前必须根据内容判断是否需要 IP 形象 (`(IP形象: 是/否)`)。
    *   **重要**: 若标记为 `(IP形象: 是)`，则生成的 Prompt **必须包含**上方定义的完整 IP 形象描述（短碎发、黑框眼镜、橙红色着装等）。
2.  **尺寸规范 (Aspect Ratio)**:
    *   **Part A (主视觉)**: 必须在开头标明 `movie composition, 2.35:1 aspect ratio`，并在结尾使用 `--ar 2.35:1`。**禁止提供 Context 字段** (No Context needed)。
    *   **Part B (侧边栏)**: 纯色背景 (需提取主视觉主色)，必须标明 `1:1 aspect ratio`。**禁止提供 Context 字段** (No Context needed)。
    *   **Part C (配图)**: 必须在开头标明 `portrait composition, 3:4 aspect ratio`。这是手机阅读最佳比例。
    *   **Context (锚点)**: 每一张**内文配图 (Part C)** 都必须提供 `Context` 字段。
        *   **定义**: 该图片应插入位置的**上一段落的最后一句话**。
        *   **要求**: 必须是原文中的原句，确保唯一性。
        *   **格式**: `> Context: "原文句子..."`

3.  **侧边栏内容 (Part B)**: 纯色暖色调背景 + **必须使用中文**，遵循统一的侧边栏设计系统。
    *   **设计系统**: 详见 `references/sidebar_design_system.md`。所有 Part B 必须严格遵循该规范。
    *   **色彩**: 根据文章**内容支柱**从固定色板选取（详见 `references/sidebar_design_system.md`）。**禁止**使用蓝、靛、青、紫等冷色变体。
    *   **字数限制**: 总共 **4-6 个汉字**的核心短语。按语义拆为**上下两行**，每行 **2-4 字**。
    *   **字体**: 毛笔书法体/有机手绘感，**白色外描边 + 底色同色填充**（镂空/阴刻效果）。
    *   **装饰**: 可选，但每次仅一种，不超过画面 5% 面积。默认无装饰。
    *   **禁止**: 英文单词、拼音、数字、冷色背景、超过 6 个汉字、单行超过 4 字、多种装饰叠加、西文印刷字体、照片或复杂插画。

4.  **⛔ 全图禁字 (No Text in Any Part)** — Part A / C 同样适用

    **Part A（主视觉）与 Part C（内文配图）禁止出现任何文字**：中文、英文、拼音、数字，一律不允许。唯一例外是 Part B 的镂空书法字——那是设计本身。

    *   **为什么必须写死**：AI 生图会**自发往物件上"填字"**。书皮、笔记本封面、水杯、海报、招牌、衣服、包装、标牌，都是高频翻车点。不上约束就一定出英文。
    *   **Prompt 里必须显式加一段**（放在 Part A / Part C 的 prompt 末尾、`--ar` 之前）：
        > ⛔ 画面中不出现任何文字、字母、数字。书本的书页画成空白或纯色块，封面上不写字；笔记本页面画成空白横线；杯具、包装、招牌、衣物一律保持素面无字。不要任何可读的印刷内容。
    *   **反面案例（2026-09-11 实测）**：封面 prompt 未加禁字约束，Gemini 在书皮生成 `STORIES UNTOLD`、笔记本生成 `NOTES & SKETCHES`、水杯生成 `STAY CURIOUS`；同批内文插图书脊生成 `NOTES / ESSAYS / WRITING`。四处英文，全部作废重生成。
    *   **验收步骤（必做）**：生图后**逐张放大扫字**，检查画面内每一处可读面——书、纸、杯、袋、牌、衣、墙。发现任何字母或数字 → 该图判定作废，补上禁字约束后重生成。**不要因为"字很小"就放过。**

### Step 2: 决策 (Check)

**询问用户**: "分镜表已生成。是否立即生成图片？(Run generation?)"
*   **Yes**: 进入 Step 3。
*   **No**: 任务结束，用户可手动使用 Prompt。

### Step 3: 执行 (Execution) - Optional

调用 `scripts/visualize.py` 脚本批量生成图片。

*   **全流程自动化**: 推荐同时传入 `--draft` 参数，脚本将自动完成 "生成 -> 压缩 -> 上传COS -> 插入正文 -> 清理本地" 的完整闭环。
*   **脚本逻辑**: 默认优先使用 **Gemini Web**（HTTP → CDP 两级回退）；若不可用，再回退到 **Gemini API** → **GPT-Image2**，最后尝试 **SiliconFlow API**。
*   **批量会话**: 当本轮优先 provider 为 `gemini-web` 时，脚本会先用单次 Gemini Web 会话批量生成本轮缺失图片，再进入压缩、上传和注入流程，减少 5~6 张图场景下的重复初始化。
*   **首次登录**: 首次使用 `gemini-web` 前，先运行 `PYTHONIOENCODING=utf-8 python scripts/visualize.py --gemini-web-login` 完成独立登录初始化。
*   **配置检测**: 运行 `PYTHONIOENCODING=utf-8 python scripts/config_check.py` 检查生图配置是否就绪。
*   **隔离原则**: `gemini-web` 会使用仓库根目录下 `.gemini/wechat-director/gemini-web/` 的独立 runtime，不复用日常 Chrome Profile。
*   **IP 增强**: 脚本会自动识别 Storyboard 中的 `(IP形象: 是)` 标记。若启用，将自动读取 `assets/IP_Reference.jpg` 作为 Gemini Web / Gemini API 的参考图输入。

## 🛠️ 脚本工具箱

| 脚本 | 功能 | I/O 规范 |
|:---|:---|:---|
| `scripts/visualize.py` | 批量调用生图后端 | 读取 `Storyboard.md` 中的 Prompt 代码块 |
| `scripts/visualize.py` (simple) | 简单模式: 仅生成 sidebar + 拼接用户封面 | 读取 Storyboard Part B + `--cover` 参数 |
