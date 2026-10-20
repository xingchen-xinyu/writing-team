# Visual Prompts & Style Guide (v3.0 - Chinese)

> **Source**: `Prompt/文章配图（含 IP 形象） - Prompt.md`
> **Role**: 张艺谋 (Visual Director)
> **Engine**: Flux / Nano Banana Pro (中优)

## 🎨 核心风格 (Core Style)

**扁平矢量贴纸风格 (Flat Vector Illustration with Sticker Style)**

*   **Global Style Lock**: 确保这组关键词在所有 Prompt 中出现。
*   **Keywords**: `扁平矢量插画`, `白色贴纸描边`, `极简主义`, `鲜艳配色`, `干净的矢量线条`, `白底`, `商业插画`, `Dribbble风格`, `无阴影`, `2D扁平`.

## 👤 IP 形象 (Character Reference)

> **The "IP Rule"**: 当 `(IP形象: 是)` 时，必须强制包含以下核心描述。参考图 `assets/IP_Reference.jpg` 为 6 格角色转身参考图。

### 1. IP 判断规则
*   `(IP形象: 是)` — 画面主体是作者本人（写作、思考、运动等场景）
*   `(IP形象: 否)` — 抽象概念 / 纯物体 / 第三方人物
*   主视觉 Part A 默认 `(IP形象: 否)`，保持意境优先

### 2. 核心特征 (Base)
```
一个中国男性(40岁)，短碎发层次纹理、平整服帖，戴黑色细框眼镜，面容干净整洁，脸型偏瘦有轮廓感，气质阳光有朝气。体型匀称结实(身高168cm，约72kg)，有运动习惯。人物全身轮廓有粗白色描边(贴纸风格)。

A Chinese male (40 years old), short textured layered hairstyle neatly combed flat, wearing thin black-framed glasses, clean and neat appearance, slim defined face with lean jawline, energetic and sunny disposition. Athletic build (168cm, ~72kg), physically active. Thick white outlines around the entire silhouette (sticker style).
```

### 3. 动态换装 (Dynamic Clothing)
*   **Context Aware**: 根据场景自动选择着装：
    *   *代码/写作/思考*: 橙红色休闲T恤，深色运动休闲长裤
    *   *运动/户外*: 橙红色运动T恤，运动短裤，橙红色系带运动鞋
    *   *日常/居家*: 橙红色休闲T恤，休闲长裤

## 📐 构图规范 (Composition)

### 1. 主视觉封面 (Cover Main) --ar 2.35:1
*   **Prompt Structure**:
    ```text
    [场景描述], [IP核心特征] 穿着 [场景对应服装], [背景环境], 扁平矢量插画, 白色贴纸描边, 极简主义, 鲜艳配色, 干净线条, 白底, --ar 2.35:1
    ```

### 2. 侧边栏 (Cover Sidebar) --ar 1:1

> ⚠️ **已废弃 (Deprecated)** — 此 Part B 模板已被 `sidebar_design_system.md` 取代。
> 侧边栏现已统一为**文字镂空**设计（毛笔书法体 + 白色描边 + 底色同色填充），不再使用物体/图标 + 无文字的设计。
> 完整规范见 [`sidebar_design_system.md`](./sidebar_design_system.md)。

**旧版模板（不再使用）**:
```text
纯色 [暖色系颜色] 背景, 画面中心是一个 [代表主题的物体/图标], 极简主义, 扁平矢量插画, 白色贴纸描边, 无文字, --ar 1:1
```

### 3. 内文配图 (Insert) --ar 3:4
*   **Prompt Structure**:
    ```text
    [具体动作/交互], [IP核心特征 (如需)] 穿着 [场景对应服装], [简单背景], 扁平矢量插画, 白色贴纸描边, 极简主义, --ar 3:4
    ```

## 🚫 负向提示 (Negative Prompt)
```text
照片, 真实感, 3d, 阴影, 渐变, 复杂细节, 凌乱, 文字, 水印, 签名, 模糊, 低质量, 素描
```
