# OpenCode UI 组件库 (@opencode-ai/ui) 架构文档

## 概述

`@opencode-ai/ui` 是 OpenCode 项目的核心 UI 组件库，基于 **SolidJS** 框架构建，包含 80+ 个可复用组件。组件库采用 `[data-component]` 属性进行样式隔离，配合 Tailwind CSS 实现原子化样式，并通过 `@kobalte/core` 提供无样式（headless）UI 原语。

**包名**: `@opencode-ai/ui`
**版本**: 1.14.48
**许可证**: MIT
**类型**: ES Module (`"type": "module"`)

---

## 1. 项目结构

```
packages/ui/
├── package.json              # 包配置与导出映射
├── vite.config.ts            # Vite 构建配置
├── tsconfig.json             # TypeScript 配置
├── script/
│   ├── colors.txt            # 颜色定义
│   └── tailwind.ts           # Tailwind 生成脚本
└── src/
    ├── assets/
    │   ├── icons/            # SVG 图标资源
    │   │   ├── file-types/   # 文件类型图标
    │   │   └── provider/     # AI 服务商图标
    │   ├── fonts/            # 字体资源
    │   └── audio/            # 音频资源
    ├── components/           # 所有 UI 组件
    ├── context/              # 全局上下文
    ├── hooks/                # 可复用 Hooks
    ├── i18n/                 # 国际化字典
    ├── pierre/               # Diff 引擎集成层
    ├── styles/               # CSS 样式
    └── theme/                # 主题系统
```

### 包导出映射

包采用精细的导出映射（package.json `exports` 字段），支持按路径导入：

| 导出路径 | 说明 |
|----------|------|
| `./*` | 组件（指向 `src/components/*.tsx`） |
| `./i18n/*` | 国际化字典 |
| `./pierre` | Diff 引擎入口 |
| `./pierre/*` | Diff 引擎子模块 |
| `./hooks` | 可复用 Hooks |
| `./context` | 全局上下文 |
| `./context/*` | 上下文子模块 |
| `./styles` | 全局 CSS |
| `./styles/tailwind` | Tailwind CSS |
| `./theme` | 主题系统 |
| `./theme/context` | 主题上下文 Provider |
| `./icons/provider` | 服务商图标类型 |
| `./icons/file-type` | 文件类型图标 |
| `./icons/app` | 应用图标 |
| `./fonts/*` | 字体文件 |
| `./audio/*` | 音频文件 |

---

## 2. 组件分类体系

### 2.1 基础原语 (Primitives)

基于 `@kobalte/core` 的无样式组件封装，提供完整的可访问性支持（WAI-ARIA）。

| 组件 | 文件 | 说明 |
|------|------|------|
| **Accordion** | `accordion.tsx` | 手风琴折叠面板，支持多选模式 |
| **Avatar** | `avatar.tsx` | 头像组件，支持颜色编码 |
| **Button** | `button.tsx` | 通用按钮（primary/secondary/ghost 变体） |
| **Card** | `card.tsx` | 卡片容器 |
| **Checkbox** | `checkbox.tsx` | 复选框 |
| **Collapsible** | `collapsible.tsx` | 可折叠区域 |
| **ContextMenu** | `context-menu.tsx` | 右键上下文菜单 |
| **Dialog** | `dialog.tsx` | 模态对话框 |
| **DropdownMenu** | `dropdown-menu.tsx` | 下拉菜单 |
| **HoverCard** | `hover-card.tsx` | 悬停卡片（Tooltip 增强版） |
| **IconButton** | `icon-button.tsx` | 图标按钮 |
| **InlineInput** | `inline-input.tsx` | 内联输入框（原地编辑） |
| **List** | `list.tsx` | 列表组件 |
| **Popover** | `popover.tsx` | 弹出框 |
| **Progress** | `progress.tsx` | 进度条 |
| **ProgressCircle** | `progress-circle.tsx` | 环形进度 |
| **RadioGroup** | `radio-group.tsx` | 单选按钮组 |
| **ResizeHandle** | `resize-handle.tsx` | 拖动调整大小手柄 |
| **ScrollView** | `scroll-view.tsx` | 滚动容器（支持虚拟滚动） |
| **Select** | `select.tsx` | 下拉选择 |
| **Switch** | `switch.tsx` | 开关切换 |
| **Tabs** | `tabs.tsx` | 标签页 |
| **Tag** | `tag.tsx` | 标签/徽章 |
| **TextField** | `text-field.tsx` | 文本输入框 |
| **Toast** | `toast.tsx` | 轻提示/通知 |
| **Tooltip** | `tooltip.tsx` | 工具提示 |

另有 **StickyAccordionHeader** (`sticky-accordion-header.tsx`) 提供粘性定位的手风琴头部，用于文件列表等场景。

### 2.2 Markdown 渲染

Markdown 渲染是 UI 库的核心能力之一，包含两套渲染引擎：

#### 2.2.1 完整渲染器 (`markdown.tsx`)

完整的 Markdown 到 HTML 渲染管道：

```
原始 Markdown 文本
    │
    ▼
markdown-stream.ts (流式分块)
    │  根据是否 streaming 模式，将文本切分为 Block[]
    │  每个 Block 包含 raw(原文) 和 src(处理后文本)
    │
    ▼
marked.parse() (解析渲染)
    │  使用 marked 库，配置了以下扩展：
    │  - marked-katex-extension: KaTeX 数学公式支持
    │  - marked-shiki: Shiki 代码语法高亮
    │  - 自定义 link renderer: 自动添加 target="_blank" 和 rel="noopener noreferrer"
    │
    ▼
DOMPurify.sanitize() (安全净化)
    │  配置项：
    │  - USE_PROFILES: { html: true, mathMl: true }
    │  - 允许 SVG 标签 (ADD_TAGS: ["svg", "path"])
    │  - 禁止 <style> 标签和内容
    │  - SANITIZE_NAMED_PROPS: true
    │
    ▼
后处理装饰 (decorate)
    │  - 代码块添加复制按钮 (ensureCodeWrapper)
    │  - URL-like 代码内联链接 (markCodeLinks)
    │
    ▼
morphdom 高效 DOM 更新
    │  - 仅更新变化的部分
    │  - 保留复制按钮的交互状态
    │
    ▼
最终 DOM 输出
```

**特性**：
- **代码高亮**: 通过 Shiki WASM 高亮器，注册了自定义的 "OpenCode" 主题，使用 CSS 变量引用主题 Token
- **数学公式**: 支持 `$inline$` 和 `$$display$$` 两种 KaTeX 语法
- **代码复制**: 每个代码块自动添加复制按钮，支持 i18n
- **链接处理**: 外部链接自动添加安全属性；URL-like 代码文本自动转换为链接
- **缓存**: 基于内容哈希的缓存机制（LRU，最多 200 条）
- **流式支持**: 与 `markdown-stream.ts` 配合，支持 AI 实时输出场景

#### 2.2.2 流式渲染器 (`markdown-stream.ts`)

专为 AI 实时输出设计的流式 Markdown 处理：

```typescript
export function stream(text: string, live: boolean): Block[]
```

**工作流程**：
1. 使用 `remend` 库修复不完整的 Markdown 语法（如未闭合的链接）
2. 使用 `marked.lexer()` 将文本解析为 Token 流
3. 检测最后一个 Token：如果是未闭合的代码块（fence block），则将其分离为独立的 Block
4. 返回 `Block[]`，前部分为已完成内容（标记为 "live"），代码块独立渲染避免闪烁

**应用场景**：当 AI 正在生成 Markdown 内容时，先渲染已完成部分，代码块等待闭合后再渲染。

### 2.3 Diff 可视化

#### DiffChanges 组件 (`diff-changes.tsx`)

展示文件修改的增删统计：

```tsx
<DiffChanges changes={{ additions: 42, deletions: 7 }} variant="default" />
```

支持两种变体：
- **default**: 显示 `+N -M` 数字格式
- **bars**: 显示可视化的增减比例条（5 段式）

核心算法根据增删比例动态计算显示段数，对小规模修改（<=10 行）进行比例压缩。

#### Pierre 集成 (`src/pierre/`)

UI 库内置了 `@pierre/diffs` 的深度集成层，提供：

| 模块 | 文件 | 说明 |
|------|------|------|
| `index.ts` | 入口 | 导出 DiffProps 类型、`createDefaultOptions`、`styleVariables` |
| `virtualizer.ts` | 虚拟化 | 大文件 Diff 的虚拟滚动支持 |
| `comment-hover.ts` | 评论悬停 | 行内评论的悬停交互 |
| `commented-lines.ts` | 评论行 | 已评论行的状态管理 |
| `worker.ts` | Web Worker | 在 Worker 中执行 Diff 计算 |
| `file-selection.ts` | 文件选择 | Diff 文件选择逻辑 |
| `file-find.ts` | 文件搜索 | Diff 内容搜索 |
| `selection-bridge.ts` | 选择桥接 | 行选择跨层级通信 |
| `diff-selection.ts` | Diff 选择 | 选择范围高亮 |
| `file-runtime.ts` | 文件运行时 | 文件渲染运行时 |
| `media.ts` | 媒体 | 图片等媒体文件支持 |

**默认 Diff 配置**：
- 主题: "OpenCode"（CSS 变量驱动）
- 样式: unified
- 行号: 启用
- 行悬停高亮: both（两侧）
- 背景: 启用
- 折叠展开行数: 20
- 文件头: 禁用
- 字级差异: 在 split 模式下使用 word-alt

### 2.4 文件显示

| 组件 | 文件 | 说明 |
|------|------|------|
| **File** | `file.tsx` | 文件内容渲染 |
| **FileIcon** | `file-icon.tsx` | 文件类型图标（支持 50+ 文件类型） |
| **FileSearch** | `file-search.tsx` | 文件搜索界面，使用 fuzzysort 模糊匹配 |
| **FileSSR** | `file-ssr.tsx` | 服务端渲染文件显示 |
| **FileMedia** | `file-media.tsx` | 图片/媒体文件预览 |

**文件图标系统**：通过 `vite-plugin-icons-spritesheet` 在构建时从 `src/assets/icons/file-types/` 生成 SVG sprite 和 TypeScript 类型定义。

### 2.5 会话 UI (Session)

OpenCode 的核心交互单元是"会话"（Session），每个会话包含多个"轮次"（Turn）。

| 组件 | 文件 | 说明 |
|------|------|------|
| **SessionReview** | `session-review.tsx` | 会话回顾界面，展示完整对话历史 |
| **SessionTurn** | `session-turn.tsx` | 单个对话轮次，包含用户消息和 AI 响应 |
| **SessionDiff** | `session-diff.ts` | 会话级别 Diff 计算逻辑 |
| **SessionRetry** | `session-retry.tsx` | AI 回复重试功能 |

### 2.6 消息显示 (Message)

消息系统负责渲染对话中的各个部分（Part），采用可插拔的组件注册机制。

#### 消息部分类型

| Part 类型 | 说明 |
|-----------|------|
| `text` | 文本消息（Markdown 渲染） |
| `tool` | 工具调用（可展开查看详情） |
| `reasoning` | 推理过程（思维链展示） |
| `file` | 文件引用 |
| `agent` | 子 Agent 引用 |
| `compaction` | 上下文压缩分隔线 |

#### 可注册扩展机制

```typescript
// 注册自定义 Part 渲染器
PART_MAPPING["custom_type"] = (props) => <CustomRenderer ... />

// 注册自定义 Tool 渲染器
ToolRegistry.register({
  name: "tool_name",
  render: (props) => <CustomToolDisplay ... />
})
```

#### 内置 Tool 渲染器

| Tool 名称 | 图标 | 说明 |
|-----------|------|------|
| `read` | glasses | 文件读取（支持 offset/limit 参数） |
| `list` | bullet-list | 目录列表 |
| `glob` | magnifying-glass-menu | 文件匹配搜索 |
| `grep` | magnifying-glass-menu | 文本内容搜索 |
| `webfetch` | window-cursor | 网页抓取 |
| `websearch` | window-cursor | 网络搜索（支持 Exa/Parallel） |
| `task` | task | 子 Agent 任务（支持导航到子会话） |
| `bash` | console | Shell 命令执行 |
| `edit` | code-lines | 文件编辑（展示 Diff） |
| `write` | code-lines | 文件写入 |
| `apply_patch` | code-lines | 应用补丁（支持多文件） |
| `todowrite` | checklist | 待办事项列表 |
| `question` | bubble-5 | 提问回答 |
| `skill` | brain | 技能调用 |

**上下文工具分组**：`read`、`glob`、`grep`、`list` 四种工具会被自动分组到 "收集上下文" 折叠面板中。

**流式文本动画**：文本消息支持 `PacedMarkdown` 逐段渲染，使用 `createPacedValue` Hook 控制渲染速度（24ms/步，在标点处智能断句），模拟 AI 打字效果。

### 2.7 文本动画

| 组件 | 文件 | 说明 |
|------|------|------|
| **Typewriter** | `typewriter.tsx` | 打字机动画效果，逐字符显示文本，完成后闪烁光标 |
| **TextReveal** | `text-reveal.tsx` | 文本渐显效果 |
| **TextShimmer** | `text-shimmer.tsx` | 闪烁加载效果（用于工具运行中状态） |
| **TextStrikethrough** | `text-strikethrough.tsx` | 删除线动画 |
| **AnimatedNumber** | `animated-number.tsx` | 数字滚动动画（类似里程表效果） |

**数字滚动动画详情**：

`AnimatedNumber` 组件实现了类似机械里程表的数字翻转效果：
- 维护一个 30 位的循环数字条（3 组 0-9）
- 通过 CSS `--animated-number-offset` 变量控制向上/向下滚动
- 根据增/减方向选择滚动方向
- 使用 `transitionEnd` 事件在动画完成后重置位置

### 2.8 图标系统

#### 内联 SVG 图标 (`icon.tsx`)

内置 70+ 个手绘 SVG 图标，存储在 `icon.tsx` 的 `icons` 对象中。图标使用 `stroke="currentColor"` 继承文字颜色，支持 4 种尺寸（small/normal/medium/large）。

```tsx
<Icon name="check" size="small" />
<Icon name="glasses" size="normal" />
```

#### 服务商图标 (`provider-icons/`)

70+ 个 AI 服务商的 SVG 图标，通过构建时插件从远程 API 动态获取。支持的服务商包括：

- Anthropic, OpenAI, Google, DeepSeek, Mistral, Cohere, Groq, Meta (Llama)
- 中国厂商: 智谱 AI (zhipuai), 月之暗面 (moonshotai/kimi), 阿里 (alibaba), 字节跳动, 百度, Minimax, StepFun, DeepSeek
- 平台: Amazon Bedrock, Azure, GitHub Models, HuggingFace, Vertex AI, Cloudflare Workers AI
- 更多: Together AI, Fireworks, Perplexity, Cerebras, Novita AI, 等

#### 文件类型图标 (`file-icons/`)

通过 SVG sprite 技术管理，支持按文件扩展名匹配图标。

#### 应用图标 (`app-icons/`)

应用级别的导航图标（sidebar, status, file-tree, review 等），支持 active 状态变体。

### 2.9 Dock UI

| 组件 | 文件 | 说明 |
|------|------|------|
| **DockPrompt** | `dock-prompt.tsx` | 输入提示区的底部停靠组件 |
| **DockSurface** | `dock-surface.tsx` | 停靠面板的容器/表面 |

### 2.10 特殊组件

| 组件 | 文件 | 说明 |
|------|------|------|
| **Font** | `font.tsx` | 字体加载管理（确保等宽字体就绪） |
| **Spinner** | `spinner.tsx` | 加载动画旋转器 |
| **MotionSpring** | `motion-spring.tsx` | 基于 motion 库的弹簧动画 Hook |
| **LineComment** | `line-comment.tsx` | 内联代码评论（与 Pierre Diff 集成） |
| **ThinkingHeading** | `thinking-heading.stories.tsx` | AI 思考状态指示器 |
| **Keybind** | `keybind.tsx` | 键盘快捷键显示 |
| **ImagePreview** | `image-preview.tsx` | 图片预览（在 Dialog 中全屏展示） |
| **Logo** | `logo.tsx` | OpenCode 品牌 Logo |
| **AppIcon** | `app-icon.tsx` | 应用图标 |
| **Favicon** | `favicon.tsx` | 网站 Favicon |
| **ToolErrorCard** | `tool-error-card.tsx` | 工具错误信息卡片 |
| **ToolStatusTitle** | `tool-status-title.tsx` | 工具状态标题（运行中/完成切换） |
| **ToolCountSummary** | `tool-count-summary.tsx` | 工具调用统计摘要 |
| **ToolCountLabel** | `tool-count-label.tsx` | 工具调用数量标签 |

---

## 3. 主题系统 (`src/theme/`)

### 3.1 架构概览

主题系统采用 **种子色生成**（seed-based）和 **调色板直接指定**（palette-based）两种模式，支持 36 个内置主题。

### 3.2 核心类型

```typescript
// 种子色模式：只需指定关键色彩，其他色阶自动生成
interface ThemeSeedColors {
  neutral: HexColor      // 中性色
  primary: HexColor      // 主色
  success: HexColor      // 成功色
  warning: HexColor      // 警告色
  error: HexColor        // 错误色
  info: HexColor         // 信息色
  interactive: HexColor  // 交互色
  diffAdd: HexColor      // Diff 新增色
  diffDelete: HexColor   // Diff 删除色
}

// 调色板模式：精确指定每个语义色
interface ThemePaletteColors {
  neutral: HexColor
  ink: HexColor          // 墨水色（用于紧凑主题）
  primary: HexColor
  success: HexColor
  warning: HexColor
  error: HexColor
  info: HexColor
  accent?: HexColor
  interactive?: HexColor
  diffAdd?: HexColor
  diffDelete?: HexColor
}

// 主题定义
interface DesktopTheme {
  name: string           // 显示名称
  id: string             // 唯一标识
  light: ThemeVariant    // 浅色变体
  dark: ThemeVariant     // 深色变体
}
```

### 3.3 颜色生成引擎 (`theme/color.ts`)

核心颜色处理函数：

| 函数 | 说明 |
|------|------|
| `generateScale(seed, isDark)` | 从种子色生成 12 阶色阶（OKLCH 色彩空间） |
| `generateNeutralScale(seed, isDark)` | 生成 12 阶中性灰色阶 |
| `generateAlphaScale(scale, isDark)` | 生成半透明色阶 |
| `hexToOklch()` | Hex -> OKLCH 色彩空间转换 |
| `oklchToHex()` | OKLCH -> Hex 转换（含色域检查 fitOklch） |
| `shift(color, {l, c, h})` | 在 OKLCH 空间中偏移颜色 |
| `blend(fg, bg, alpha)` | RGB 混合 |
| `mixColors(c1, c2, amount)` | OKLCH 空间色彩混合 |
| `withAlpha(color, alpha)` | 添加 Alpha 通道（输出 rgba） |

**关键技术**：全部使用 OKLCH 色彩空间，提供感知均匀的颜色渐变，避免传统 HSL/RGB 色彩空间中常见的亮度不均问题。

### 3.4 Token 解析 (`theme/resolve.ts`)

`resolveThemeVariant(variant, isDark)` 函数将主题变体解析为 300+ 个 CSS Token（`ResolvedTheme = Record<ThemeToken, ColorValue>`）。

**Token 类别**：

| 类别 | Token 前缀 | 数量 | 说明 |
|------|-----------|------|------|
| background | `background-*` | 4 | 背景色（base/weak/strong/stronger） |
| surface | `surface-*` | 60+ | 表面色（base/interactive/success/warning/critical/info/diff/brand 等） |
| text | `text-*` | 30+ | 文本色（base/weak/weaker/strong/invert/on-*） |
| border | `border-*` | 40+ | 边框色（base/strong/weak/interactive/success/warning/critical/info 等） |
| icon | `icon-*` | 50+ | 图标色（base/strong/weak/brand/interactive/success 等，含 agent 专用色） |
| input | `input-*` | 6 | 输入框色 |
| button | `button-*` | 6 | 按钮色 |
| syntax | `syntax-*` | 20+ | 语法高亮色（comment/string/keyword/type/constant 等） |
| markdown | `markdown-*` | 15 | Markdown 渲染色（heading/link/code/block-quote 等） |
| avatar | `avatar-*` | 12 | 头像色（6 种色调 x 背景+文字） |
| diff | `text-diff-*`, `surface-diff-*` | 20+ | Diff 色彩 |

### 3.5 内置主题列表（36 个）

| ID | 显示名称 | 风格 |
|----|---------|------|
| `oc-2` | OC-2 | OpenCode 默认主题 |
| `amoled` | AMOLED | 纯黑 OLED |
| `aura` | Aura | 紫色调 |
| `ayu` | Ayu | 暖色调 |
| `carbonfox` | Carbonfox | 灰蓝调 |
| `catppuccin` | Catppuccin | 柔和的粉彩色 |
| `catppuccin-frappe` | Catppuccin Frappe | Catppuccin 变体 |
| `catppuccin-macchiato` | Catppuccin Macchiato | Catppuccin 变体 |
| `cobalt2` | Cobalt2 | 蓝色高亮 |
| `cursor` | Cursor | Cursor 编辑器风格 |
| `dracula` | Dracula | 经典的紫灰 |
| `everforest` | Everforest | 自然绿色调 |
| `flexoki` | Flexoki | 米色暖色调 |
| `github` | GitHub | GitHub 风格 |
| `gruvbox` | Gruvbox | 复古暖色 |
| `kanagawa` | Kanagawa | 日式蓝调 |
| `lucent-orng` | Lucent Orng | 橙色高亮 |
| `material` | Material | Material Design 风格 |
| `matrix` | Matrix | 黑客帝国绿 |
| `mercury` | Mercury | 浅灰调 |
| `monokai` | Monokai | 经典代码主题 |
| `nightowl` | Night Owl | 深夜蓝紫 |
| `nord` | Nord | 极简蓝灰 |
| `one-dark` | One Dark | Atom 经典 |
| `onedarkpro` | One Dark Pro | One Dark 增强版 |
| `opencode` | OpenCode | OpenCode 品牌色 |
| `orng` | Orng | 橙色主题 |
| `osaka-jade` | Osaka Jade | 翡翠绿色 |
| `palenight` | Palenight | 紫罗兰夜 |
| `rosepine` | Rose Pine | 玫瑰粉 |
| `shadesofpurple` | Shades of Purple | 紫色渐变 |
| `solarized` | Solarized | 著名的 Solarized |
| `synthwave84` | Synthwave '84 | 80 年代合成波 |
| `tokyonight` | Tokyonight | 东京夜空 |
| `vercel` | Vercel | Vercel 品牌 |
| `vesper` | Vesper | 暗紫调 |
| `zenburn` | Zenburn | 经典低对比度 |

### 3.6 Theme Context 功能

(`theme/context.tsx`) 提供完整的主题管理：

- **存储持久化**: 使用 `localStorage` 存储当前主题 ID、色彩方案（light/dark/system）、预计算 CSS
- **动态加载**: 通过 `import.meta.glob` 懒加载主题 JSON 文件
- **预览机制**: 支持 `previewTheme`/`previewColorScheme` 和 `commitPreview`/`cancelPreview`
- **系统跟随**: 监听 `prefers-color-scheme` 媒体查询自动切换
- **跨 Tab 同步**: 监听 `storage` 事件实现多标签页主题同步
- **自定义主题注册**: 通过 `registerTheme()` 注册第三方主题

---

## 4. 国际化系统 (`src/i18n/`)

采用 Context 模式提供国际化支持：

```typescript
// 使用示例
const i18n = useI18n()
const label = i18n.t("ui.message.copy")           // "Copy"
const dynamic = i18n.t("ui.message.duration.seconds", { count: "5" })  // "5 seconds"
```

**模板语法**: 使用 `{{key}}` 双花括号占位符，通过 `resolveTemplate` 函数替换参数。

**默认回退**: 当未提供 I18nProvider 时，自动回退到英文（en）字典。

**I18nProvider 配置**:
```typescript
<I18nProvider value={{ locale: () => "zh", t: (key, params) => translationFn(key, params) }}>
  {children}
</I18nProvider>
```

---

## 5. 全局上下文 (`src/context/`)

### 5.1 Marked Context (`context/marked.tsx`)

提供共享的 `marked` 解析器实例：

- **JS Parser 模式**: 使用 marked + marked-katex-extension + marked-shiki 组合
- **Native Parser 模式**: 外部注入原生 Markdown 解析器（用于桌面端性能优化）
- **自定义主题注册**: 使用 `registerCustomTheme("OpenCode", ...)` 注册自定义 Shiki 主题
- **代码高亮策略**: 优先使用 `shiki-wasm` 高亮器

**关键配置**:
- 链接渲染：自动添加 `target="_blank"` 和 `rel="noopener noreferrer"`
- KaTeX 非标准模式：`nonStandard: true`
- MathML 支持：`USE_PROFILES: { html: true, mathMl: true }`

### 5.2 Data Context (`context/data.tsx`)

提供全局数据存储访问：

```typescript
interface Data {
  agent?: { name: string; color?: string }[]     // 可用 Agent 列表
  provider?: ProviderListResponse                  // 服务商列表
  session: Session[]                               // 会话列表
  session_status: Record<string, SessionStatus>    // 会话状态
  session_diff: Record<string, SnapshotFileDiff[]> // 会话 Diff
  message: Record<string, Message[]>               // 消息列表
  part: Record<string, Part[]>                     // Part 列表
}
```

提供 `navigateToSession` 和 `sessionHref` 回调，支持 SPA 导航和外部链接两种模式。

### 5.3 Dialog Context (`context/dialog.tsx`)

全局对话框管理系统：

- 基于 `@kobalte/core/dialog` 实现模态对话框
- 支持键盘 Esc 关闭
- 自动管理动画生命周期（closing 状态 + 100ms 延迟清理）
- 通过 `useDialog()` Hook 在任意组件中调用

```typescript
const dialog = useDialog()
dialog.show(() => <MyDialog onClose={() => dialog.close()} />)
```

### 5.4 File Context (`context/file.tsx`)

提供文件渲染组件的依赖注入：

```typescript
const fileComponent = useFileComponent()
// 用于 edit/write/apply_patch 工具中渲染文件内容/Diff
```

### 5.5 Helper Context (`context/helper.tsx`)

工厂函数 `createSimpleContext`：

```typescript
const { use: useMyContext, provider: MyProvider } = createSimpleContext({
  name: "MyContext",    // 用于错误提示
  init: (props) => {    // 初始化上下文值
    return { ... }
  }
})
```

所有上下文组件均基于此工厂创建，提供统一的错误处理和类型安全。

---

## 6. Hooks (`src/hooks/`)

### 6.1 useFilteredList (`use-filtered-list.tsx`)

使用 `fuzzysort` 实现模糊搜索过滤列表：

```typescript
const { results, search } = useFilteredList(items, {
  keys: ["name", "path"],
  limit: 20
})
```

### 6.2 createAutoScroll (`create-auto-scroll.tsx`)

自动滚动到底部的 Hook，用于聊天消息等场景。

---

## 7. 样式系统 (`src/styles/`)

### 7.1 样式文件

| 文件 | 说明 |
|------|------|
| `base.css` | CSS Reset（Tailwind 风格），重置所有浏览器默认样式 |
| `colors.css` | 颜色 CSS 变量 |
| `theme.css` | 主题相关 CSS 变量 |
| `animations.css` | 关键帧动画定义 |
| `utilities.css` | 通用工具类 |
| `index.css` | 主入口，汇总以上所有样式 |

### 7.2 动画定义 (`animations.css`)

| 动画名称 | 说明 | 用途 |
|---------|------|------|
| `pulse-opacity` | 透明度脉冲 (0.4 -> 1 -> 0.4) | Spinner/加载指示器 |
| `pulse-scale` | 缩放脉冲 (1 -> 0.67 -> 1) | 活动指示器 |
| `pulse-opacity-dim` | 微弱透明度脉冲 (0.15 -> 0.35 -> 0.15) | 微妙加载状态 |
| `fadeUp` | 从下方淡入 (translateY + opacity) | 列表项入场动画 |
| `.fade-up-text` | 级联淡入（子元素依次延迟） | 多段落依次出现 |

### 7.3 组件样式约定

所有组件采用 `data-component` 属性作为样式作用域：

```css
[data-component="button"] { ... }
[data-slot="button-icon"] { ... }
[data-variant="primary"] { ... }
[data-size="small"] { ... }
```

这种命名约定避免了 CSS 类名冲突，同时保持了样式的可读性。

### 7.4 Tailwind CSS

使用 Tailwind CSS v4（`@tailwindcss/vite`），通过 `tailwindcss` 和 `@tailwindcss/vite` 插件集成到 Vite 构建中。同时有 `script/tailwind.ts` 脚本用于生成自定义 Tailwind 配置。

---

## 8. 动画原语

### 8.1 MotionSpring (`motion-spring.tsx`)

基于 `motion` 库的弹簧动画 Hook：

```typescript
const animatedValue = useSpring(
  () => targetValue(),
  () => ({ visualDuration: 0.3, bounce: 0.2 })
)
```

**功能**：
- 数值平滑过渡（spring 物理模型）
- 动态切换动画参数
- 自动重配置：当配置变化时重新创建弹簧
- 资源清理：`onCleanup` 中销毁所有 motion 对象

### 8.2 Motion 动画集成

组件中使用 `motion` 库实现微交互动画：

```typescript
// Shell 子消息动画
animate(widthRef, { width: "auto" }, { type: "spring", visualDuration: 0.25, bounce: 0 })
animate(valueRef, { opacity: 1, filter: "blur(0px)" }, { duration: 0.32, ease: [0.16, 1, 0.3, 1] })
```

---

## 9. 与 App 和 Desktop 包的集成

### 9.1 集成架构

```
Desktop 包 (Tauri/Electron)
    │
    ├── 提供 MarkdownParser (原生层)
    │   └── 通过 MarkedProvider 的 nativeParser prop 注入
    │
    ├── 提供 FileComponent (代码编辑器)
    │   └── 通过 FileProvider 注入，用于 edit/write/apply_patch 展示
    │
    ├── 提供 DataProvider
    │   └── 注入会话数据、消息数据、Provider 列表
    │
    ├── 提供 I18nProvider
    │   └── 注入本地化字典和语言设置
    │
    └── 提供 ThemeProvider
        └── 配置默认主题和主题切换回调
```

### 9.2 关键集成点

1. **Markdown 渲染桥接**: Marked Context 支持 `nativeParser` 模式，桌面端可在原生层（Rust/Node）完成 Markdown 解析，UI 层仅负责数学公式后处理和代码高亮。

2. **文件组件注入**: 通过 `useFileComponent()` Hook，桌面端可注入 Monaco Editor 等重量级编辑器组件来渲染 Diff、文件内容。

3. **数据流**: App/Desktop 包通过 `DataProvider` 注入 `session`、`message`、`part` 等响应式数据，组件内部通过 `useData()` 读取。

4. **导航集成**: `navigateToSession` 和 `sessionHref` 回调让 UI 库在新 Tab 打开和 SPA 导航之间灵活切换，适配 Web 和 Desktop 两种运行环境。

5. **主题持久化**: Theme Context 内置 localStorage 存储和跨 Tab 同步，与桌面端的系统主题检测无缝配合。

6. **图标资源**: 构件时通过 `vite-plugin-icons-spritesheet` 将 SVG 图标编译为内联 sprite，Provider 图标从配置的 API 端点动态获取最新图标。

### 9.3 依赖关系

```
@opencode-ai/ui
├── @opencode-ai/sdk (类型定义和数据结构)
├── @opencode-ai/core (工具函数: encode/path)
├── solid-js (UI 框架)
├── @kobalte/core (Headless UI 原语)
├── @pierre/diffs (Diff 引擎)
├── marked + marked-katex-extension + marked-shiki (Markdown 解析)
├── shiki + @shikijs/transformers (语法高亮)
├── katex (数学公式渲染)
├── motion + motion-dom + motion-utils (动画引擎)
├── dompurify (HTML 净化)
├── fuzzysort (模糊搜索)
├── luxon (日期时间处理)
├── virtua (虚拟滚动)
├── solid-list (SolidJS 列表优化)
├── morphdom (高效 DOM diff 更新)
├── strip-ansi (ANSI 转义序列清理)
├── remend (Markdown 语法自动修复)
└── remeda (函数式工具库)
```

---

## 10. 技术亮点总结

1. **Headless 架构**: 基于 @kobalte/core 的无样式组件，完全通过 CSS 变量控制外观，实现主题解耦。

2. **流式渲染**: 专为 AI 实时输出设计的 Markdown 流式渲染器，通过分块策略避免代码块闪烁。

3. **高级颜色引擎**: 全部使用 OKLCH 色彩空间，提供感知均匀的颜色插值和自动色域裁剪。

4. **可扩展消息系统**: Part/Tool 均采用注册制，第三方可以方便地扩展自定义消息类型和工具渲染器。

5. **安全优先**: 所有 Markdown HTML 输出经过 DOMPurify 净化，外部链接自动添加 noopener/noreferrer。

6. **微动画**: 通过 motion 库实现的弹簧动画和 CSS 关键帧动画，提供细腻的交互反馈（数字翻转、打字机效果、闪烁状态等）。

7. **40+ 主题**: 从经典编辑器主题（Monokai, Dracula, Nord, One Dark）到品牌主题（Vercel, GitHub），满足不同用户偏好。

8. **跨平台适配**: 同一套组件库同时支持 Web（SolidJS Router）和 Desktop（Tauri drag region、原生文件系统）两种运行环境。
