# 13 — 文本分割系统

## 概述

文本分割器将文档内容分割成适合嵌入和检索的块，基于 LangChain 的递归字符分割器实现。

## TextSplitter 类

**文件**: `server/utils/TextSplitter/index.js` (207 行)

### 构造函数参数

| 参数 | 说明 |
|------|------|
| `chunkPrefix` | 块前缀（某些嵌入器需要，如 `search_document: `） |
| `chunkSize` | 每块大小（token 数） |
| `chunkOverlap` | 块之间重叠大小 |
| `chunkHeaderMeta` | 元数据头信息 |

### 静态方法

| 方法 | 功能 |
|------|------|
| `determineMaxChunkSize(preferred, embedderLimit)` | 确保请求的块大小不超过嵌入器限制 |
| `buildHeaderMeta(metadata)` | 从元数据提取标题/发布日期/来源 |

### 实例方法

| 方法 | 功能 |
|------|------|
| `#applyPrefix(text)` | 为文本块添加前缀 |
| `stringifyHeader()` | 生成元数据头字符串 |
| `#setSplitter(config)` | 创建 RecursiveSplitter 实例 |
| `splitText(documentText)` | 分割文本并返回块数组 |

### 元数据头格式

```
<document_metadata>
sourceDocument: {title}
published: {date}
source: {url}
</document_metadata>

{chunk content}
```

## RecursiveSplitter 内部类

包装 LangChain 的 `RecursiveCharacterTextSplitter`：
- `_splitText(documentText)`:
  - 无 `chunkHeader` → 直接调用 `engine.splitText()`
  - 有 `chunkHeader` → `engine.splitText()` → `engine.createDocuments(strings, [], {chunkHeader})` → 过滤空 `pageContent`

## 块大小管理

### 最大块长度
`maximumChunkLength()` 确定嵌入的最大字符数：
- 默认：1000 字符
- 可通过 `EMBEDDING_MODEL_MAX_CHUNK_LENGTH` 环境变量覆盖
- 最小值：2

### 块大小确定
```javascript
TextSplitter.determineMaxChunkSize(requestedSize, embedderLimit)
```
- 确保不超过嵌入器限制
- 如果超过限制，夹紧到嵌入器限制并警告
- 默认使用嵌入器限制

## 与嵌入引擎的集成

每个嵌入引擎定义自己的 `embeddingMaxChunkLength`：

| 嵌入器 | 最大块长度 |
|--------|-----------|
| OpenAI | 8191 |
| Azure OpenAI | 2048 |
| Gemini | 2048 |
| Native (MiniLM) | 1000 |
| Native (nomic) | 16000 |
| Native (multilingual) | 1000 |
| Cohere | 1945 |
| Voyage AI | 4000-32000（按模型） |
| 其他 | 1000（默认） |

## 块前缀

某些嵌入模型需要前缀来区分查询和文档：
- `nomic-embed-text-v1`: `search_document: ` / `search_query: `
- `multilingual-e5-small`: `passage: ` / `query: `

## 文档处理流程中的使用

```
文件上传
  → Collector 提取文本
  → TextSplitter.splitText() 分割文本
  → 每个块添加元数据头
  → EmbeddingEngine.embedChunks() 嵌入
  → VectorDB.addDocumentToNamespace() 存储
  → 缓存向量到 vector-cache/
```
