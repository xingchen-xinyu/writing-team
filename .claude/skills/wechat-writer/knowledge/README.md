# Knowledge Base (知识库)

此目录存放 "星辰 Writing Team - Wechat-writer" 的共享知识、规则标准和参考文档。

## 🎯 用途 (Purpose)
为 Skill 提供统一的、静态的**上下文 (Context)** 和 **标准 (Standards)**。

## 🚫 边界 (Boundaries)
*   **不存放代码**: 可执行脚本请放入 `Skills/<skill-name>/scripts/`。
*   **不存放人设**: Agent 的 Prompt 请放入 `references/`。
*   **不存放 SOP**: 具体的操作步骤 (Routine) 请放入 `Skills/<skill-name>/references/`。

## 📂 文档列表
1.  **`style_guide.md`**: 星辰个人写作风格指南 (真诚、自然、有温度)。
2.  **`ai_smell_guide.md`**: 降 AI 味操作指南与必删词表。
3.  **`team_memory.md`**: 团队长期记忆 Layer 2：活跃经验 (持续积累踩坑经验)。Stage 1 必读。
4.  **`team_memory_archive.md`**: 团队长期记忆 Layer 3：历史档案 (不自动读取)。
5.  **`published_article_index.md`**: 历史文章索引 (用于内链推荐和旧文延续性检查)。
6.  **`brand_positioning.md`**: 编码人生.lab 品牌定位（Stage 1 策划必读）。
7.  **`reader_profiles.md`**: 读者画像（四画像体系：陈思远/张建国/林小满/苏青）。价值主张卡制定必须参考。
8.  **`wechat_index_keywords.md`**: 微信指数关键词积累库（SEO 调研参考）。
9.  **`素材库.md`**: 可复用资产：场景·隐喻·金句·框架 (按类型维度组织，Stage 1 必读)。
10. **`article_cards/`**: 已发布文章的 L2 详细卡片（Stage 1 旧文延续性检查时按需加载）。

## 🔗 引用方式
在 Skill 或 Agent 文件中引用时，请使用相对路径：
`knowledge/style_guide.md` (从 Skill 根目录引用)
