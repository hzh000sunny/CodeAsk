# 06 — 嵌入引擎系统

## 概述

AnythingLLM 支持 15 个嵌入模型提供商，用于将文本转换为向量表示。通过 `getEmbeddingEngineSelection()` 工厂函数实例化。

## 统一接口

所有嵌入器实现：
- `embedTextInput(text)`: 嵌入单个文本
- `embedChunks(textChunks)`: 批量嵌入文本块
- `maxConcurrentChunks`: 最大并发块数
- `embeddingMaxChunkLength`: 每块最大长度

## 提供商详解

### 1. Native Embedder（本地嵌入）
**模型**: Xenova/all-MiniLM-L6-v2（默认）

| 参数 | 值 |
|------|-----|
| maxConcurrentChunks | 25 |
| embeddingMaxChunkLength | 1000 |

**支持的模型**:

| 模型 | 并发 | 块长度 | 大小 | 前缀 |
|------|------|--------|------|------|
| Xenova/all-MiniLM-L6-v2 | 25 | 1000 | 23MB | 无 |
| Xenova/nomic-embed-text-v1 | 5 | 16000 | 139MB | search_document/search_query |
| MintplexLabs/multilingual-e5-small | 5 | 1000 | 487MB | passage/query |

**特点**:
- 使用 `@xenova/transformers`（浏览器端 ML）
- 无需 API Key，完全本地运行
- 内存优化：分批写入临时文件，避免 OOM
- 双层回退下载：HuggingFace → CDN (`cdn.anythingllm.com`)
- 模型缓存到 `storage/models/`

### 2. OpenAI Embedder
- 模型：`text-embedding-ada-002`（默认）
- maxConcurrentChunks: 500
- embeddingMaxChunkLength: 8191
- 使用原生 OpenAI SDK

### 3. Azure OpenAI Embedder
- 需配置 `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_KEY`
- maxConcurrentChunks: 16（Azure 限制）
- embeddingMaxChunkLength: 2048
- API 版本: `2024-12-01-preview`

### 4. Ollama Embedder
- 需配置 `EMBEDDING_BASE_PATH` + `EMBEDDING_MODEL_PREF`
- maxConcurrentChunks: 可配置 (`OLLAMA_EMBEDDING_BATCH_SIZE`，默认 1)
- 使用原生 Ollama SDK
- 批量处理，通过 `num_ctx` 控制上下文
- 支持 `OLLAMA_AUTH_TOKEN` Bearer 认证

### 5. Gemini Embedder
- 模型：`gemini-embedding-001`（默认）
- maxConcurrentChunks: 4
- embeddingMaxChunkLength: 2048
- 使用 OpenAI 兼容端点 (`generativelanguage.googleapis.com/v1beta/openai/`)
- 支持 `EMBEDDING_OUTPUT_DIMENSIONS` 维度配置

### 6. LocalAI Embedder
- maxConcurrentChunks: 50
- 支持 `EMBEDDING_OUTPUT_DIMENSIONS`
- 并发批处理模式

### 7. LM Studio Embedder
- maxConcurrentChunks: 1（顺序处理，LM Studio 不支持并发）
- 使用 `encoding_format: "base64"`
- 每次调用前检查服务可用性

### 8. Cohere Embedder
- 模型：`embed-english-v3.0`（默认）
- maxConcurrentChunks: 96
- embeddingMaxChunkLength: 1945
- 使用原生 Cohere SDK
- 自动设置 `inputType`（search_query/search_document）

### 9. Voyage AI Embedder
- 模型：`voyage-3-lite`（默认）
- batchSize: 128
- 使用 LangChain VoyageEmbeddings
- 根据模型动态确定最大嵌入长度（4000-32000）
- 速率限制错误特殊处理

### 10. Mistral Embedder
- 模型：`mistral-embed`（默认）
- 最简单的实现：单次请求嵌入所有块（无批处理）
- 使用 OpenAI 兼容端点

### 11. LiteLLM Embedder
- maxConcurrentChunks: 500
- 并发批处理模式
- 默认模型：`text-embedding-ada-002`

### 12. Generic OpenAI Embedder
- 最灵活的嵌入器
- maxConcurrentChunks: 可配置（默认 500）
- 顺序处理模式（非并发）
- 支持 `GENERIC_OPEN_AI_EMBEDDING_API_DELAY_MS` 请求延迟
- 自定义 Base URL 和 API Key

### 13. OpenRouter Embedder
- maxConcurrentChunks: 500
- embeddingMaxChunkLength: 8191
- 默认模型: `baai/bge-m3`
- 自动获取可用嵌入模型列表

### 14. Lemonade Embedder
- maxConcurrentChunks: 50
- 顺序处理模式
- 特殊错误处理（嵌套 `details.response.error`）
- 使用 Lemonade 端点解析

## 进度报告机制

`reportEmbeddingProgress(chunksProcessed, totalChunks)`:
- 在子进程（IPC `process.send`）和主进程（`emitProgress`）中工作
- 需要调用者设置 `global.__embeddingProgress` 上下文
- 发送 `chunk_progress` 类型事件

## 嵌入重排序

### Native Embedding Reranker
**文件**: `server/utils/EmbeddingRerankers/native/index.js`

- 模型：`Xenova/ms-marco-MiniLM-L-6-v2`
- 使用 `@xenova/transformers`
- 单例模式缓存模型和分词器
- 双层回退下载
- Sigmoid 评分 → 降序排序 → TopK 切片
- 性能：约 1.6 秒处理 18 个文档
- `rerank(query, documents, {topK})` 方法
