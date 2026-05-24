# 07 — 附加工具

## 概述

项目附加工具，包括多语言翻译、构建脚本和云部署配置生成器。

## 翻译工具

### 翻译器
**文件**: `extras/translator/index.mjs`

- 自动翻译前端国际化文件
- 基于 AI 的大规模翻译
- 支持全量翻译（`--all` 参数）
- 环境变量: `.env.example`

### 翻译验证和规范化
脚本位于前端 `frontend/src/locales/`:

| 脚本 | 功能 |
|------|------|
| `verifyTranslations.mjs` | 验证翻译文件完整性 |
| `normalizeEn.mjs` | 规范化英文翻译 |
| `findUnusedTranslations.mjs` | 查找未使用的翻译键（可选 `--delete`） |

### 本地化 README
`locales/` 目录包含多语言 README：
- 中文 (zh-CN)
- 日文 (ja-JP)
- 土耳其文 (tr-TR)
- 波斯文 (fa-IR)

## 构建脚本

### 包版本验证
**文件**: `extras/scripts/verifyPackageVersions.mjs`

验证各子项目（server, frontend, collector）的包版本一致性。

## 云部署生成器

| 脚本 | 功能 |
|------|------|
| `generate::cloudformation` | 生成 AWS CloudFormation 模板 |
| `generate::gcp_deployment` | 生成 GCP 部署配置 |

这些脚本从根 `package.json` 中定义。

## 多语言 README

| 文件 | 语言 |
|------|------|
| `locales/README.zh-CN.md` | 简体中文 |
| `locales/README.ja-JP.md` | 日语 |
| `locales/README.tr-TR.md` | 土耳其语 |
| `locales/README.fa-IR.md` | 波斯语 |

## 项目配置文件

| 文件 | 用途 |
|------|------|
| `.editorconfig` | 编辑器配置 |
| `.prettierrc` | 代码格式化规则 |
| `.prettierignore` | 格式化忽略 |
| `eslint.config.js` | ESLint 配置（根级） |
| `.hadolint.yaml` | Dockerfile Linter 配置 |
| `.gitattributes` | Git 属性配置 |
| `.gitignore` | Git 忽略规则 |
| `.gitmodules` | Git 子模块 |
| `.nvmrc` | Node.js 版本指定 |
