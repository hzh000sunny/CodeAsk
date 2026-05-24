# 07 — 向量数据库系统

## 概述

AnythingLLM 支持 10 个向量数据库后端，通过统一的 `VectorDatabase` 抽象基类接口，默认使用 LanceDB。

## 工厂函数

`getVectorDbClass(getExactly)` — 根据 `VECTOR_DB` 环境变量实例化，支持：
pinecone, chroma, chromacloud, lancedb, weaviate, qdrant, milvus, zilliz, astra, pgvector

## 抽象基类接口（`base.js`）

所有向量数据库必须实现的方法：

| 方法 | 说明 |
|------|------|
| `connect()` | 连接数据库客户端 |
| `heartbeat()` | 健康检查 |
| `totalVectors()` | 总向量数 |
| `namespaceCount(namespace)` | 命名空间向量数 |
| `hasNamespace(namespace)` | 命名空间是否存在 |
| `addDocumentToNamespace(namespace, data, path, skipCache)` | 嵌入并存储文档 |
| `deleteDocumentFromNamespace(namespace, docId)` | 删除文档向量 |
| `performSimilaritySearch({namespace, input, LLMConnector, similarityThreshold, topN, filterIdentifiers, rerank})` | 完整搜索管线 |
| `similarityResponse({client, namespace, queryVector, similarityThreshold, topN, filterIdentifiers})` | 原始相似度搜索 |
| `deleteVectorsInNamespace(client, namespace)` | 删除命名空间所有向量 |
| `reset()` | 清除所有数据 |
| `curateSources(sources)` | 规范化来源元数据 |

## 各向量数据库详解

### 1. LanceDB（默认）
**文件**: `vectorDbProviders/lance/index.js` (506 行)

- 本地文件型向量数据库
- 存储路径: `storage/lancedb/`
- 距离转相似度公式: `1 - distance`（余弦距离）
- **唯一支持重排序搜索** `rerankedSimilarityResponse()`:
  - 第一阶段：向量搜索（top 10-50 结果）
  - 第二阶段：NativeEmbeddingReranker 重排序
- 表操作: `updateOrCreateCollection()`, `countRows()`
- 元数据清理: 去除 `vector`, `_distance` 内部字段

### 2. Pinecone
**文件**: `vectorDbProviders/pinecone/index.js` (317 行)

- 云服务向量数据库
- 使用 `@pinecone-database/pinecone` SDK
- 需配置: `PINECONE_API_KEY`, `PINECONE_INDEX`
- 特性:
  - 批量 upsert（100 条/批）
  - 批量删除（1000 条/批）
  - `namespace()` 获取命名空间统计
  - 结果通过 `match.score` 过滤

### 3. Chroma
**文件**: `vectorDbProviders/chroma/index.js` (484 行)

- 开源向量数据库（可自托管）
- 使用 `chromadb` SDK
- 需配置: `CHROMA_ENDPOINT`
- 可选认证: `CHROMA_API_HEADER` / `CHROMA_API_KEY`
- 特性:
  - 严格的集合命名规则（3-63 字符，字母数字）
  - `normalize()` 强制执行命名规则
  - `hnsw:space: cosine` 索引配置
  - L2 距离转余弦相似度

### 4. ChromaCloud
**文件**: `vectorDbProviders/chromacloud/index.js` (158 行)

- 继承 Chroma，覆盖连接和批量操作
- 使用 `CloudClient`
- 需配置: `CHROMACLOUD_API_KEY`, `CHROMACLOUD_TENANT`, `CHROMACLOUD_DATABASE`
- 限制: maxEmbeddingDim 4096, maxDocumentBytes 16384, maxMetadataBytes 4096, maxRecordsPerWrite 300
- 批量写入分块（300 条/批）

### 5. Qdrant
**文件**: `vectorDbProviders/qdrant/index.js` (442 行)

- 高性能向量数据库
- 使用 `@qdrant/js-client-rest` SDK
- 需配置: `QDRANT_ENDPOINT`，可选 `QDRANT_API_KEY`
- 特性:
  - 集合自动创建（距离: Cosine）
  - 批量 upsert（500 条/批）
  - 结果通过 `response.score` 过滤
  - 集群状态检查

### 6. Milvus
**文件**: `vectorDbProviders/milvus/index.js` (434 行)

- 云原生向量数据库
- 使用 `@zilliz/milvus2-sdk-node` SDK
- 需配置: `MILVUS_ADDRESS`, `MILVUS_USERNAME`, `MILVUS_PASSWORD`
- 特性:
  - 自动索引创建（AUTOINDEX + COSINE 度量）
  - 字段结构: id (VarChar PK), vector (FloatVector), metadata (JSON)
  - `flushSync()` 确保数据持久化

### 7. Zilliz
**文件**: `vectorDbProviders/zilliz/index.js` (36 行)

- 继承 Milvus
- 使用 `ZILLIZ_ENDPOINT` + `ZILLIZ_API_TOKEN`（而非用户名/密码）
- 所有其他行为与 Milvus 一致

### 8. Weaviate
**文件**: `vectorDbProviders/weaviate/index.js` (510 行)

- 开源向量数据库
- 使用 `weaviate-ts-client` SDK
- 需配置: `WEAVIATE_ENDPOINT`，可选 `WEAVIATE_API_KEY`
- 特性:
  - GraphQL 查询（`nearVector`, `aggregate`）
  - 对象批处理（`batch.objectsBatcher()`）
  - 元数据扁平化（点标记法，跳过数组对象）
  - 使用 `certainty`（余弦相似度）过滤

### 9. AstraDB
**文件**: `vectorDbProviders/astra/index.js` (475 行)

- DataStax 云向量数据库
- 使用 `@datastax/astra-db-ts` SDK
- 需配置: `ASTRA_DB_APPLICATION_TOKEN`, `ASTRA_DB_ENDPOINT`
- 特性:
  - 命名空间前缀 `ns_`
  - 集合维度检查
  - 批量插入（20 条/批）
  - HTTP POST 绕过 SDK 限制获取所有命名空间

### 10. PGVector
**文件**: `vectorDbProviders/pgvector/index.js` (850 行)

- PostgreSQL 向量扩展
- 使用 `pg` 原生客户端
- 需配置: `PGVECTOR_CONNECTION_STRING`，可选 `PGVECTOR_TABLE_NAME`
- 特性:
  - **最复杂的实现**（850 行）
  - 完整的事务管理（BEGIN/COMMIT/ROLLBACK）
  - 模式验证（检查列类型）
  - JSONB 数据净化（移除 NUL 和控制字符）
  - 支持 6 种距离操作符（l2, innerProduct, cosine, l1, hamming, jaccard）
  - 向量 L2 归一化
  - 连接验证（30 秒超时）

## 文档存储流程

所有向量数据库遵循统一的文档存储流程：

```
1. 检查向量缓存（vector-cache/）
2. 如果有缓存 → 直接读取缓存的向量块
3. 如果没有缓存 → 
   a. TextSplitter 分割文本
   b. EmbeddingEngine 嵌入每个块
   c. 保存向量缓存
4. 将向量块存入向量数据库
5. 在 SQLite 中创建 workspace_documents 记录
```

## 相似度搜索流程

```
1. 嵌入用户查询文本
2. 调用 similarityResponse() 执行向量搜索
3. 通过相似度阈值过滤结果
4. 通过 filterIdentifiers 排除已固定文档
5. 规范化来源元数据（curateSources）
6. 可选：重排序（rerank）
7. 返回 contextTexts + sources
```

## 向量存储重置

**文件**: `vectorStore/resetAllVectorStores.js`

当向量配置更改时：
1. 清除所有向量缓存文件
2. 删除 SQLite 中的 Document 和 DocumentVectors 记录
3. **PGVector**: 删除整个表（因为维度更改不可修改列）
4. **其他**: 逐个删除每个工作区的命名空间
