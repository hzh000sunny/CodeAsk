# 12 指标 & 可观测性

## 1. 模块概览

OpenViking 拥有三层可观测性系统：操作遥测 (telemety)、指标收集与导出 (metrics)、以及可观测性基础设施 (observability)。

| 子模块 | 用途 |
|---|---|
| `metrics/` | Prometheus 指标收集与导出, OTel 集成 |
| `telemetry/` | 操作级遥测 (Span, Execution, Snapshot) |
| `observability/` | HTTP 中间件, 事件总线, 使用审计 |

---

## 2. 指标系统 (metrics/)

### 2.1 架构层次

```
DataSources (数据源)           →  原始事件/状态
    ↓
Collectors (收集器)            →  转换为 Prometheus 指标
    ↓                                  (Counter/Gauge/Histogram)
Exporters (导出器)             →  暴露指标端点
    ├── PrometheusExporter     →  /api/v1/metrics
    └── OTelExporter           →  OTLP gRPC/HTTP
```

### 2.2 核心组件 (metrics/core/)

| 组件 | 说明 |
|---|---|
| `MetricRegistry` | 全局指标注册表 (Gauge/Counter/Histogram) |
| `MetricRuntime` | 运行时指标刷新调度 (APScheduler) |
| `RefreshScheduler` | 周期性指标刷新 (可配置间隔) |
| `MetricTypes` | 指标类型定义 |

### 2.3 数据源 (metrics/datasources/)

| 数据源 | 监控对象 |
|---|---|
| `HttpDataSource` | HTTP 请求/响应计数, 延迟, 状态码 |
| `QueueDataSource` | 队列深度, 处理速率, 错误率 |
| `SessionDataSource` | 会话创建/提交计数, 消息量 |
| `CacheDataSource` | 缓存命中/未命中, 大小 |
| `ModelUsageDataSource` | VLM/Embedding/Rerank token 使用量 |
| `EmbeddingDataSource` | 嵌入请求计数, 延迟, 维度 |
| `RerankDataSource` | 重排序请求计数, 文档量 |
| `TaskDataSource` | 任务计数, 状态分布 |
| `EncryptionDataSource` | 加密操作计数, 有效载荷大小 |
| `ResourceDataSource` | 资源添加计数, 类型分布 |
| `RetrievalDataSource` | 检索查询计数, 结果数, 延迟, 零结果率 |
| `ObserverStateDataSource` | 观察者健康状态 |
| `TelemetryBridgeDataSource` | 操作遥测 → 指标桥接 |
| `ProbeDataSource` | 服务/存储/模型提供商/检索后端探针 |

### 2.4 收集器 (metrics/collectors/)

每个数据源对应一个收集器, 将数据源事件转换为 Prometheus 指标:

| 收集器 | 指标示例 |
|---|---|
| `HTTPCollector` | `ov_http_requests_total`, `ov_http_request_duration_seconds` |
| `QueueCollector` | `ov_queue_depth`, `ov_queue_processed_total` |
| `SessionCollector` | `ov_sessions_total`, `ov_session_messages_total` |
| `CacheCollector` | `ov_cache_hits_total`, `ov_cache_size_bytes` |
| `ModelUsageCollector` | `ov_vlm_tokens_total`, `ov_embedding_tokens_total` |
| `EmbeddingCollector` | `ov_embedding_requests_total`, `ov_embedding_latency_seconds` |
| `TaskTrackerCollector` | `ov_tasks_total{status="completed"}` |
| `EncryptionCollector` | `ov_encryption_ops_total`, `ov_encryption_payload_bytes` |
| `ResourceCollector` | `ov_resources_added_total{type="git"}` |
| `RetrievalCollector` | `ov_retrieval_queries_total`, `ov_retrieval_zero_result_rate` |
| `TelemetryBridgeCollector` | 将操作级遥测桥接到 Prometheus |
| `FeedbackCollector` | `ov_feedback_events_total{type="thumbs_up"}` |
| `ServiceProbe` / `StorageProbe` 等 | 健康探针 (up/down) |

### 2.5 导出器 (metrics/exporters/)

```python
class PrometheusExporter:
    """暴露 /api/v1/metrics 端点 (Prometheus 文本格式)"""
    # 由 prometheus_client 库生成

class OTelExporter:
    """通过 OpenTelemetry SDK 导出到 OTLP 收集器"""
    # 支持: OTLP gRPC 和 OTLP HTTP
    # 环境变量:
    #   OTEL_EXPORTER_OTLP_ENDPOINT
    #   OTEL_EXPORTER_OTLP_HEADERS
    #   OTEL_SERVICE_NAME
```

### 2.6 账户维度 (metrics/account_dimension.py)

```python
# 多租户指标支持:
# 每个指标自动附 account_id 标签
# 通过 AccountDimensionManager 管理
```

---

## 3. 遥测系统 (telemetry/)

### 3.1 核心概念

```python
# OperationSpan: 操作跨度模型
@dataclass
class OperationSpan:
    operation: str                    # 操作名称
    stage: str                        # 阶段 (request/processing/complete)
    start_time: float                 # 开始时间
    end_time: Optional[float]
    attributes: Dict[str, Any]        # 跨度属性
    events: List[SpanEvent]           # 跨度事件
    parent_id: Optional[str]

# RootSpanAttributes / OperationSpanAttributes
```

### 3.2 执行上下文 (telemetry/execution.py)

```python
async def run_with_telemetry(operation, ctx, **kwargs) -> Dict:
    """使用遥测包装操作执行"""
    # 1. 创建 OperationSpan
    # 2. 设置 OTel 跨度上下文
    # 3. 执行操作
    # 4. 记录成功/失败
    # 5. 更新指标 (通过 TelemetryBridge)
    # 6. 返回结果
```

### 3.3 追踪器 (telemetry/tracer.py)

```python
class Tracer:
    """OpenTelemetry 追踪器包装器"""
    def start_span(name, attributes) -> Span
    def get_current_span() -> Optional[Span]
    def set_attribute(key, value)
    def add_event(name, attributes)
```

### 3.4 其他遥测组件

| 组件 | 说明 |
|---|---|
| `telemetry/registry.py` | 追踪器注册表 |
| `telemetry/request.py` | 请求级遥测上下文 |
| `telemetry/request_wait_tracker.py` | 请求等待时间追踪 |
| `telemetry/resource_summary.py` | 资源摘要遥测 |
| `telemetry/runtime.py` | 运行时遥测状态 |
| `telemetry/snapshot.py` | 遥测快照 |
| `telemetry/span_models.py` | 操作跨度数据模型 |
| `telemetry/backends/memory.py` | 内存遥测后端 |
| `telemetry/operation.py` | 操作遥测 (摘要事件) |

---

## 4. 可观测性基础设施 (observability/)

### 4.1 HTTP 中间件 (observability/http_observability_middleware.py)

```python
class HttpObservabilityMiddleware:
    """FastAPI 中间件: 注入追踪上下文, 记录请求指标"""
    # 每个 HTTP 请求:
    # 1. 提取/生成 request_id
    # 2. 创建 RootSpanAttributes
    # 3. 记录 HttpDataSource 事件
    # 4. 注入响应头 (X-Request-ID, X-Process-Time)
```

### 4.2 事件总线 (observability/events.py)

```python
class EventBus:
    """全局事件总线, 解耦生产者和消费者"""
    
    # 事件类型:
    # - http.request_start / http.request_end
    # - queue.enqueue / queue.dequeue
    # - session.created / session.committed
    # - model.usage.updated
    # - retrieval.query_executed
    
    def publish(event_type, payload)
    def subscribe(event_type, callback)
    def unsubscribe(event_type, callback)
```

### 4.3 使用审计 (observability/usage_audit/)

```python
# 审计流水线:
#   Event → UsageAuditSubscriber → Inventory → Projection → SQLiteStore

class UsageAuditSubscriber:
    """订阅事件总线, 提取使用数据"""

class Inventory:
    """资源使用清单 (账户/用户/Agent 维度)"""

class Projection:
    """时间窗口聚合投影 (小时/天/月)"""

class SQLiteStore:
    """审计数据持久化 (SQLite)"""

class UsageAuditWorker:
    """后台审计处理工作器"""
```

### 4.4 其他可观测性组件

| 组件 | 说明 |
|---|---|
| `observability/context.py` | 可观测性上下文传播 |
| `observability/log_trace_bridge.py` | 日志 ↔ 追踪桥接 |
