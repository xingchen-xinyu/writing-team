# 写作 Agent 重构设计：xingchen-writer

- **日期**：2026-10-20
- **状态**：已确认，待实施
- **范围**：写作流程、平台发布、风格体系、脚本与归档

## 1. 背景与目标

当前仓库包含三个 Skill：`wechat-writer`（深度长文，6 角色、5 阶段）、`wechat-daily`（轻日更，独立 4 步流程）、`wechat-director`（配图）。存在四个问题：

1. 同一件事有两套写作流程，用户需要判断"这篇该走 daily 还是 writer"。
2. 整条链路假设只发公众号：HTML、封面比例、标题/摘要/排版规则都是公众号口径。
3. 风格规则越写越多，写作和审校变成逐条应试；`team_memory` 持续积压，维护成本大于收益。
4. 发布后需要手动归档和提交，容易漏掉。

本次重构的目标：

1. **一个写作流程**：删除 daily 和 interview，只保留 `/write`。
2. **多平台发布**：一份笔记正文，同时产出公众号和小红书成品。
3. **星辰风格**：以最小必守规则起步，通过实际写作逐步完善。
4. **发布即归档**：发布完成后自动 git commit。

### 非目标

- 不做平台自动登录或自动发布；只产出可直接粘贴的成品。
- 不做 SEO / 微信指数调研。
- 不保留 team_memory 机制。
- 不追求长文写作；统一为 300-600 字笔记体。
- 第一阶段不接入第三个平台，但平台层按可扩展方式组织。

## 2. 核心决策

| 维度 | 决策 |
|------|------|
| 流程形态 | 固定完整流程，所有内容走同一套阶段 |
| 内容形态 | 300-600 字笔记体，一篇只讲一个点 |
| 正文 | 公众号和小红书共用同一份正文 |
| 平台差异 | 只存在于标题、摘要、标签、封面、排版 |
| 平台范围 | 微信公众号 + 小红书，默认双平台 |
| 发布方式 | 产出可粘贴成品，人工发布 |
| 平台适配实现 | Agent 创作 + `platform_check.py` 校验 + `archive.py` 落盘 |
| 角色 | 4 角色：主编、主笔、审校、制作人 |
| 人工门禁 | 3 个：策划、内容定稿、成品发布 |
| 风格 | 最小 voice_core，详细 style guide 降为可选参考 |
| 团队记忆 | 删除机制，一次性归并 |
| 发布归档 | 一文一目录，自动 git commit（不 push） |

## 3. 目录与架构

### 3.1 Skill 目录

```
.claude/skills/xingchen-writer/        # 由 wechat-writer 重命名
├── SKILL.md                           # 单入口 /write
├── knowledge/
│   ├── voice_core.md                  # 最小必守规则（每篇必读）
│   ├── ai_smell_guide.md              # L1-L4 完整清单（审校参考）
│   ├── brand_positioning.md           # 品牌定位（去掉"公众号"限定）
│   ├── reader_profiles.md             # 读者画像
│   ├── published_article_index.md     # 已发布索引
│   └── 素材库.md                       # 可复用场景、隐喻、金句
├── references/
│   ├── core_personas.md               # 4 角色
│   ├── routine_plan.md                # 策划流程
│   ├── platform_wechat.md             # 公众号形式规则
│   ├── platform_xiaohongshu.md        # 小红书形式规则
│   ├── title_design.md                # 双平台标题规则
│   ├── style_reference.md             # 原 style_guide，可选参考
│   ├── bio_footer.md                  # 公众号文末介绍
│   └── io_schema.md                   # 脚本 I/O 契约
├── scripts/
│   ├── config_check.py
│   ├── review_toolkit.py
│   ├── platform_check.py              # 新增
│   ├── format.py
│   └── archive.py
└── tests/
```

`wechat-director/` 目录名保持不变，内部改为平台无关的视觉能力。

### 3.2 项目目录

```
To-be-used/Project_[Title]/
├── 00_Source.md          # 可选：素材整理；日记可直接原地使用
├── 01_Plan.md            # 笔记角度卡 + 系列信息 + 人机边界
├── 02_Note.md            # 300-600 字笔记正文（唯一事实源）
├── 03_Package.md         # 双平台标题、摘要、标签、图片计划
├── Platform_Check.md     # 平台硬约束校验报告
├── Storyboard.md         # 一份分镜，含公众号与小红书两节
├── img/
│   ├── wechat/           # 2.35:1 封面 + 1:1 侧边栏
│   └── xiaohongshu/      # 3:4 封面 + 2-4 张内页
└── _temp_*.json
```

### 3.3 发布与归档目录

```
published/YYYYMMDD_[Title]/
├── note.md               # 笔记正文存档
├── wechat.md             # 公众号发布稿（正文 + 文末介绍）
├── wechat.html           # 可粘贴 HTML
├── xiaohongshu.md        # 小红书文案 + 话题标签 + 签名
└── img/
    ├── wechat/
    └── xiaohongshu/

conductor/archive/YYYYMMDD_[Title]/
├── 00_Source.md
├── 01_Plan.md
├── 02_Note.md
├── 03_Package.md
├── Storyboard.md
└── img/
```

旧 `published/` 平铺文件不迁移、不改名；索引同时兼容旧格式。

## 4. 工作流

### 4.1 阶段总览

| 阶段 | 角色 | 做什么 | 产出 | 门禁 |
|------|------|--------|------|------|
| S0 素材 | 主编 | 读 `diary/` 或用户输入；素材不足时就地追问 2-3 个具体问题 | `00_Source.md`（可选） | — |
| S1 策划 | 主编 | 确定这一篇只讲哪个点、钩子方向、内容支柱、系列与序号、人机边界 | `01_Plan.md` | CP1 策划确认 |
| S2 笔记写作 | 主笔 → 审校 → 主编 | 写 300-600 字；审校做硬检查与软建议；主编出综改指令；主笔修改 | `02_Note.md` | CP2 内容定稿确认 |
| S3 包装与视觉 | 制作人 + director | 双平台标题、摘要、标签、签名；一份 Storyboard 产出两套比例图片 | `03_Package.md` + `Storyboard.md` + `img/` | CP3 成品确认 |
| S4 发布归档 | 制作人 | CP3 通过后执行：平台校验 → 落盘 → HTML → 索引 → 项目归档 → 自动 commit | `published/YYYYMMDD_[Title]/` | — |

### 4.2 入口

- 主入口：`/write "标题"`，触发 `xingchen-writer`。
- 恢复：`/write "标题" --from-stage N`，N 为 0-4。
- 平台选择：默认双平台；可用 `--platform wechat|xiaohongshu|all` 限制。
- 日记桥接：用户说"用日记写""用今天/昨天的日记写"时，直接从 `diary/` 读取，不强制复制到 `00_Source.md`。
- 删除 `/daily`、`/interview`、`/访谈` 触发器。

### 4.3 四个角色

| 角色 | 职责 |
|------|------|
| 主编（呼延雷锋） | S0 素材、S1 策划、系列规划、综改指令、门禁把关 |
| 主笔（冰清） | S2 笔记正文写作 |
| 审校（罗永浩） | 硬检查：编造、禁词、说教/营销腔、口语感；软建议：节奏、感官、隐喻、金句 |
| 制作人（马可婷） | 标题、摘要、标签、排版、视觉协调、归档、commit message |

### 4.4 三个人工确认点

1. **CP1 策划确认**：这一篇只讲什么、钩子往哪走、是否属于系列。
2. **CP2 内容定稿确认**：300-600 字笔记是否 OK；此时不做平台包装。
3. **CP3 成品确认**：双平台标题、标签、摘要、图片一起确认。图片门禁并入此处，选项为"生成图片 / 跳过图片 / 去改文案"。

### 4.5 系列规则

- 单篇严格 300-600 字；装不下的内容在 S1 拆成系列，而不是写长。
- 一个系列由多个独立笔记项目组成，每篇独立走完整流程、独立归档。
- `01_Plan.md` 记录系列名、序号、上一篇/下一篇；索引按系列聚合展示。
- 系列序号重复或缺失时给出警告，不阻塞发布。

## 5. 风格体系

### 5.1 voice_core.md（最小必守，约 30 行）

必守 5 条：

1. 只写真实经历和真实感受，不编造场景、对话、数据、观点。
2. 第一人称，像跟朋友说话；不端着、不说教、不装作权威。
3. 从具体场景或细节切入；不宏大叙事，不总结式开头。
4. 不用营销腔和互联网黑话：干货、痛点、底层逻辑、搞定、炸裂、颠覆等。
5. 结尾轻收，不升华、不喊口号、不"综上所述"。

笔记体建议：

- 300-600 字，空行分段，默认无子标题。
- 一篇只讲一个点：具体场景 → 一个转折 → 轻收尾。
- 不写清单体、教程体、金句堆叠体。

暂不写入规则：五锚点、氛围感三技法、口语梯度、金句数量、开头/结尾手法清单。原 `style_guide.md` 保留为 `references/style_reference.md`，只在需要时参考，不作为每篇必读或打回理由。

### 5.2 审校标准

**硬检查（不通过就改）**：

- 是否有编造的场景、对话、数据、观点。
- 是否命中最小禁词表。
- 是否有说教感或营销腔。
- 读起来是否像人在说话。

**软建议（不阻塞）**：

- 节奏、感官细节、隐喻、金句、回环呼应。

完整 L1-L4 清单保留在 `ai_smell_guide.md`，供审校参考，不再要求逐层全跑。

### 5.3 平台层

| 维度 | 公众号 | 小红书 |
|------|--------|--------|
| 正文 | 与 `02_Note.md` 完全一致 | 与 `02_Note.md` 完全一致 |
| 标题 | ≤ 35 字，允许叙述型标题 | ≤ 20 字，前 6-10 字承担钩子 |
| 摘要 | 建议 ≤45 字，硬上限 120 字 | 不需要 |
| 标签 | 3-5 个，用于索引 | 5-8 个话题标签，放在正文末尾 |
| 文末 | `bio_footer.md` 个人介绍 | 一行轻签名，不带导流话术 |
| 图片 | 2.35:1 封面 + 1:1 侧边栏 | 3:4 封面 + 2-4 张 3:4 内页 |
| 输出 | Markdown + 可粘贴 HTML | Markdown 文案 + 图片清单 |

平台层只改形式，不改语气、句子密度和叙事方式。同一篇笔记换平台，必须读起来像同一个人写的。

## 6. 脚本与数据契约

### 6.1 脚本清单

| 脚本 | 状态 | 职责 |
|------|------|------|
| `config_check.py` | 改造 | 去掉 SEO 检查，保留生图 provider 检测 |
| `review_toolkit.py` | 精简 | 去掉 SEO 与长文结构字段；保留 critique/directive/feedback |
| `platform_check.py` | 新增 | 校验双平台硬约束，输出 `Platform_Check.md` |
| `format.py` | 保留 | 笔记正文 → 公众号可粘贴 HTML |
| `archive.py` | 改造 | 多平台归档、索引更新、历史清理、自动 commit |
| `visualize.py` | 改造 | 解析双平台分镜，分别产出 2.35:1 / 3:4 图片 |

删除：`research.py`、`wechat-daily/scripts/*`。

### 6.2 platform_check.py 校验规则

| 检查 | 公众号 | 小红书 |
|------|--------|--------|
| 正文字数 | 300-600 | 300-600 |
| 标题长度 | ≤ 35 字 | ≤ 20 字 |
| 摘要 | ≤ 120 字 | 不适用 |
| 标签数量 | 3-5 个 | 5-8 个 |
| 图片 | 封面 2.35:1 存在（可跳过） | 3:4 封面 + 2-4 张内页（可跳过） |
| 正文一致性 | 与 `02_Note.md` 完全一致 | 与 `02_Note.md` 完全一致 |
| 禁词 | 最小禁词表扫描 | 同左 |

字数口径：中文字符数，不含空白、标点、Markdown 标记和话题标签。

图片比例通过 Pillow 读取实际尺寸校验；未安装 Pillow 时只校验文件存在并给出警告。

正文一致性口径：`wechat.md` 去掉 frontmatter 和文末介绍、`xiaohongshu.md` 去掉话题标签和签名后，必须与 `02_Note.md` 的主体逐字一致。

校验失败时 exit code 非 0，并在 `Platform_Check.md` 中列出具体违规项。

### 6.3 01_Plan.md 必填区块

```markdown
## 笔记角度卡
- 这一篇只讲：<一个具体场景/洞察>
- 钩子方向：<第一句往哪走>
- 内容支柱：<微习惯 / 正念冥想 / 教练体感 / 读书分享>
- 系列：<系列名或"单篇">，序号：<01 或无>
- 人机边界：<哪些内容必须由星辰提供，哪些禁止编造>
```

### 6.4 03_Package.md 结构

```markdown
## 公众号
- 标题：
- 摘要：
- 标签：
- 封面图片计划：

## 小红书
- 标题：
- 话题标签： #xx #xx ...
- 签名：
- 图片计划：封面 + 2-4 张内页

## 系列
- 系列名 / 序号 / 上一篇 / 下一篇
```

### 6.5 _temp_archive.json

```json
{
  "project_dir": "To-be-used/Project_xxx",
  "note_file": "02_Note.md",
  "package_file": "03_Package.md",
  "date": "20261020",
  "series": { "name": "", "seq": 1 },
  "platforms": {
    "wechat": {
      "title": "",
      "excerpt": "",
      "tags": [],
      "cover": "img/wechat/cover-combined.jpg"
    },
    "xiaohongshu": {
      "title": "",
      "tags": [],
      "signature": "",
      "images": []
    }
  },
  "git": {
    "commit": true,
    "message": "发布：《标题》（公众号 + 小红书）"
  }
}
```

`archive.py` 只做确定性操作：生成 `note.md` / `wechat.md` / `wechat.html` / `xiaohongshu.md`、搬迁图片、更新索引、移动项目、执行 commit。

### 6.6 自动 Git Commit

- **触发**：CP3 确认后，`archive.py` 成功落盘即自动提交，不再额外询问。
- **提交信息**：由 Agent 生成并传入 `git.message`。默认格式：
  - 双平台：`发布：《标题》（公众号 + 小红书）`
  - 单平台：`发布：《标题》（公众号）` / `发布：《标题》（小红书）`
  - 系列：`发布：《标题》｜系列名 01（公众号 + 小红书）`
- **提交范围**：只 stage 本次发布相关路径：
  - `published/YYYYMMDD_[Title]/`
  - `conductor/archive/YYYYMMDD_[Title]/`
  - `.claude/skills/xingchen-writer/knowledge/published_article_index.md`
  - 本次历史清理移动的文件（`published/history/`、`diary/history/`）
- **禁止** `git add -A` 或 `git add .`，避免带入工作区无关改动。
- **不 push**。
- **失败处理**：commit 失败不回滚已发布文件；脚本返回非 0 并输出错误，由 Agent 告知用户。

### 6.7 图片与分镜

`Storyboard.md` 按平台分节：

```markdown
## WeChat
### Part A: 主视觉 (2.35:1)
### Part B: 侧边栏 (1:1)

## Xiaohongshu
### Cover (3:4)
### Inner 01 (3:4)
### Inner 02 (3:4)
```

- 公众号图片注入 `wechat.md` / HTML。
- 小红书图片以清单形式写入 `03_Package.md` 和 `xiaohongshu.md`，不内嵌正文。
- 图片缺失时 CP3 可选择跳过；归档正常进行，封面字段留空，并在 `Platform_Check.md` 标注"无图发布"。

## 7. 迁移与清理

1. `git mv .claude/skills/wechat-writer .claude/skills/xingchen-writer`。
2. 删除 `.claude/skills/wechat-daily/`。
3. 一次性归并后删除 `team_memory.md`、`team_memory_archive.md`：
   - 文风规则 → `voice_core.md`
   - AI 味规则 → `ai_smell_guide.md`
   - 可复用场景/隐喻/金句 → `素材库.md`
   - 其余流程性、历史性条目丢弃。
4. 删除 SEO 资产：`research.py`、`wechat_index_keywords.md`、`topic_radar_pool.md`、SEO 决策卡与 schema。
5. `style_guide.md` → `references/style_reference.md`。
6. 重写 `SKILL.md`、`core_personas.md`（4 角色）、`routine_plan.md`、`title_design.md`、`io_schema.md`。
7. 更新 `CLAUDE.md` 与 `README.md`，校正漂移的文件名与流程描述。
8. 删除 `/daily`、`/interview`、`/访谈` 触发器。

### 兼容性

- 旧 `published/` 平铺文件不迁移、不改名；索引兼容旧格式。
- 旧 `conductor/archive/` 项目保持原样。
- 新目录结构在 Obsidian 中的可用性，在第一次实际发布时验证。
- `--from-stage N` 保留，阶段编号为 0-4。

## 8. 测试与验收

| 测试 | 覆盖 |
|------|------|
| `test_platform_check.py` | 字数边界、标题长度、标签数量、正文一致性、图片比例、禁词命中 |
| `test_archive.py` | 一文一目录、四个产物、索引更新、项目归档、历史清理、旧格式兼容、commit 路径范围 |
| `test_review_toolkit.py` | 精简后的 critique/directive schema |
| `test_format.py` | 300-600 字笔记的 HTML 输出、图片、文末介绍 |
| `test_visualize.py` | 双平台分镜解析、2.35:1 与 3:4 图片路径 |
| 端到端 | 用一篇真实笔记跑完整流程，断言全部产物存在且 commit 只包含本次文件 |

### 成功标准

- 一条 `/write` 命令跑完 S0-S4，产出 `published/YYYYMMDD_[Title]/` 下的四个文件与图片目录。
- 正文只写一次，两个平台内容完全一致。
- 不再存在 daily、interview、SEO、team_memory 的流程残留。
- 发布后自动生成一次 commit，且不包含无关工作区改动。
- 所有测试通过；Windows 下 `PYTHONIOENCODING=utf-8` 调用正常。

## 9. 风险与应对

| 风险 | 应对 |
|------|------|
| 300-600 字限制过紧 | 超出就拆系列；积累 10-20 篇后回看是否调整区间 |
| voice_core 太薄，写出来不像星辰 | 每 10 篇手动回看一次，只补真正反复出现的问题 |
| 发布目录结构变化影响 Obsidian | 第一次实际发布时验证；索引保留旧格式兼容 |
| director 双比例改造复杂 | 分镜按平台分节，先支持封面，内页图可后置 |
| 自动 commit 误带无关改动 | 只 stage 明确路径；测试覆盖 commit 范围 |
| commit 失败影响发布 | 发布文件不回滚，明确报错；由用户决定后续处理 |

## 10. 实施顺序

1. **基础设施**：重命名 Skill、删除 daily、建立 `voice_core.md` 与平台文档骨架。
2. **核心脚本**：`platform_check.py`、`archive.py`（含自动 commit）、`review_toolkit.py` / `format.py` 精简。
3. **视觉能力**：`Storyboard` 双平台分节与 `visualize.py` 支持两种比例。
4. **流程文档**：`SKILL.md`、4 角色、`routine_plan.md`、`title_design.md`、`io_schema.md`。
5. **迁移与测试**：一次性归并 team_memory、删除 SEO 资产、补齐测试与端到端验证。
6. **文档收尾**：更新 `CLAUDE.md`、`README.md`，清理残留引用。
