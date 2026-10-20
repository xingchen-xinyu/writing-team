# WeChat Director I/O Schema

> ⚠️ **Storyboard 格式速查**：Part 标题用 `###`（3个#），Part C 内嵌 `#### 插图 N`，Context 用独立引用块 `> Context: "..."`（不放在代码块内）。详见下方示例。

## 📁 输入规范 (Input)

1.  **Draft Article (`02_Draft.md`)**
    *   完整 Markdown 正文内容。
    *   或已归档的 `published/[Title].md`。
    *   用途：提取画面意境、IP 出现的场景。

## 📄 输出规范 (Output)

### 1. Storyboard (`Storyboard.md`)

*   **Path**: 与 Input 同级目录（或指定目录）。
*   **Format**: Strict Markdown Structure (for script parsing).

```markdown
## Visual Storyboard

### Part A: 主视觉 cover-main (2.35:1)
(IP形象: 是)
```
[中文 Prompt: 场景描述, IP特征...]
```

### Part B: 侧边栏 cover-sidebar (1:1)
(IP形象: 否)
```
[中文 Prompt: 纯色背景 + 总结文字...]
```

### Part C: 内文配图 illustration
#### 插图 1: ...
(IP形象: 是)
```
[中文 Prompt: 动作描述...]
```
> Context: "原文上一段落的最后一句（用于定位插入点）"
```

### 简单模式 Storyboard

简单模式下（`--mode simple`），Storyboard 仅包含 Part B，无 Part A 和 Part C：

```markdown
## Visual Storyboard

### Part B: 侧边栏 cover-sidebar (1:1)
(IP形象: 否)
```
[Part B prompt — 按 sidebar_design_system.md 模板填充，1:1 纯色暖色背景 + 毛笔书法体镂空文字]
--ar 1:1
```
```

脚本通过 `--mode simple` 和 `--cover <封面路径>` 参数获得模式与封面信息，Storyboard 本身不携带元数据。

## 🛠️ 脚本契约 (`scripts/visualize.py`)

*   **Invoke**: Manual trigger by user or Agent.
    *   `--mode simple|full`（默认 `full`）：简单模式下仅处理 Part B，跳过 Part A/C 和内文注入。
    *   `--cover <path>`（简单模式）：显式指定用户封面路径；省略时自动检测 `img/` 下 2.35:1 图片。
*   **Input**:
    *   `--brief`: `Storyboard.md` (Must match Regex above).
    *   `--draft`: `02_Draft.md` (Required for Injection & Cleanup).
*   **Logic**:
    1.  **Parse**: Reads tasks and IP flags from Storyboard.
    2.  **Health Check**: Validates each provider's availability; in `auto` mode, skips unavailable providers and tries the next fallback.
    3.  **Generate**: Calls `gemini` API first, then falls back to `gemini-web` / `gpt-image2` / `siliconflow` (injects IP ref if needed).
        *   When `gemini-web` is selected as the preferred provider, missing images in the same article are batch-generated through one Gemini Web session before per-image post-processing.
    4.  **Compress**: Optimizes images via TinyPNG (if configured).
    5.  **Upload**: Puts illustrations to Tencent COS (if configured). covers stay local.
    6.  **Inject**: Inserts COS URLs into `Draft.md` after the `Context` sentence.
    7.  **Cleanup**: Deletes local copies of uploaded & injected illustrations.
*   **Provider Notes**:
    *   `--provider auto`: `gemini-web` → `gemini-web-browser` → `gemini` → `gpt-image2` → `siliconflow`
    *   `--gemini-web-login`: opens isolated Gemini Web login flow and exits
    *   `gemini-web` health check: validates cached login before generation; `auto` mode skips unhealthy `gemini-web`
    *   `gemini-web` batch mode: one article can reuse a single Gemini Web client session for all missing images
    *   `gemini-web` runtime path: `/.gemini/wechat-director/gemini-web/`
*   **Output**:
    *   **Files**: `img/[Title]-cover-main.jpg` (Local retained).
    *   **Artifact**: `02_Draft.md` updated with image links.
