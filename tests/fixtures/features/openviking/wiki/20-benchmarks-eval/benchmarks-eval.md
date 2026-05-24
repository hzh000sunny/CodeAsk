# 20 基准测试 & 评估

## 1. 模块概览

OpenViking 包含完整的基准测试和评估框架，用于衡量上下文记忆系统的性能。

| 目录 | 用途 |
|---|---|
| `benchmark/` | 性能基准测试 |
| `openviking/eval/` | RAG 评估框架 |

---

## 2. LoCoMo 基准 (benchmark/locomo/)

### 2.1 概述

基于 [LoCoMo10](https://github.com/snap-research/locomo) 长期对话数据集 (1,540 个测试用例) 的评估。

### 2.2 比较系统

| 目录 | 系统 |
|---|---|
| `claudecode/` | Claude Code + OpenViking |
| `mem0/` | Mem0 |
| `openclaw/` | OpenClaw + OpenViking |
| `supermemory/` | SuperMemory |
| `vikingbot/` | VikingBot + OpenViking |

### 2.3 Claude Code 评估流程

```bash
# ingest.py:      将 LoCoMo 对话导入 OpenViking
# eval.py:        运行评估 (问答)
# judge.py:       评判结果 (LLM-as-judge)
# stat_judge_result.py: 统计分析
# import_to_ov.py: 将结果导入 OpenViking 进行追踪

# 运行脚本:
# run_e2e.sh      端到端评估
# run_prompted.sh  提示式评估
# run_sdk_iso.sh   SDK 隔离评估
# run_sdk_noiso.sh SDK 非隔离评估
```

### 2.4 OpenClaw 评估

```bash
# run_full_eval.sh -- 完整评估
# eval.py → judge.py → stat_judge_result.py
```

### 2.5 VikingBot 评估

```python
# preflight_eval_config.py  # 评估配置验证
# preflight_eval_runtime.py # 运行时检查
# run_eval.py               # 运行评估
# judge.py                  # 评判
# stat_judge_result.py      # 统计
# run_full_eval.sh          # 完整流程
```

---

## 3. RAG 基准 (benchmark/RAG/)

### 3.1 支持的数据集

| 数据集 | 配置文件 | 说明 |
|---|---|---|
| FinanceBench | `config/financebench_config.yaml` | 金融文档问答 |
| LoCoMo | `config/locomo_config.yaml` | 长期对话 |
| QASPER | `config/qasper_config.yaml` | 学术论文问答 |
| SyllabusQA | `config/syllabusqa_config.yaml` | 教学大纲问答 |

### 3.2 架构

```
scripts/
├── download_dataset.py     # 下载数据集
├── prepare_dataset.py      # 准备 (转换为统一格式)
├── sample_dataset.py       # 采样
└── run_sampling.py         # 运行采样

src/
├── adapters/               # 数据集适配器
│   ├── base.py             # 适配器基类
│   ├── financebench_adapter.py
│   ├── locomo_adapter.py
│   ├── qasper_adapter.py
│   └── syllabusqa_adapter.py
├── core/                   # 核心组件
│   ├── llm_client.py       # LLM 客户端
│   ├── vector_store.py     # 向量存储
│   ├── judge_util.py       # 评判工具
│   ├── metrics.py          # 指标
│   ├── monitor.py          # 监控
│   └── logger.py           # 日志
├── pipeline.py             # 主评估管道
└── run.py                  # 运行入口
```

---

## 4. SkillsBench (benchmark/skillsbench/)

```python
# skill_bench_eval.py
# 评估 Agent 技能记忆的有效性
# 测试: 技能调用准确率, 技能参数匹配度, 技能使用频率
```

---

## 5. Tau2 基准 (benchmark/tau2/)

### 5.1 配置

```yaml
# config/baseline.yaml   # 基线配置
# config/official.yaml   # 官方配置  
# config/prewrite.yaml   # 预写入配置
```

### 5.2 评估流程

```bash
./run_full_eval.sh

# scripts/
# ├── setup_tau2_repo.sh      # 设置 Tau2 仓库
# ├── run_eval.py             # 运行评估
# ├── run_memory_v2_eval.py   # 记忆 v2 评估
# └── tau2_common.py          # 公共工具
```

---

## 6. Vaka 基准 (benchmark/vaka/)

```python
# vikingbot/
# ├── import_to_ov.py     # 导入到 OpenViking
# ├── judge.py            # 评判
# ├── run_eval.py         # 运行评估
# ├── run_full_eval.sh    # 完整流程
# ├── stat_judge_result.py # 统计
# └── vaka_utils.py       # 工具函数
```

---

## 7. 自定义基准 (benchmark/custom/)

```python
# session_contention_benchmark.py
# 测试: 多会话并发写入, 锁竞争, 吞吐量
```

---

## 8. RAGAS 评估框架 (openviking/eval/)

### 8.1 架构

```
eval/
├── ragas/                     # RAGAS 集成
│   ├── base.py                # 抽象基类
│   ├── ragas_eval.py          # RAGAS 评估器
│   ├── generator.py           # 数据集生成器
│   ├── pipeline.py            # RAG 查询管道
│   ├── types.py               # 数据类型 (EvalSample, EvalResult, SummaryResult)
│   ├── playback.py            # IO 重放
│   ├── play_recorder.py       # 重放 CLI
│   ├── record_analysis.py     # 记录分析
│   └── analyze_records.py     # 分析 CLI
├── recorder/                  # IO 录制系统
│   ├── types.py               # IORecord, AGFSCallRecord
│   ├── recorder.py            # IORecorder (单例, JSONL)
│   ├── recording_client.py    # RecordingAGFSClient
│   ├── async_writer.py        # 异步写入器
│   ├── playback.py            # (已弃用)
│   └── wrapper.py             # RecordingVikingFS, RecordingVikingDB
└── datasets/                  # 评估数据集
    └── local_doc_example_glm5.jsonl
```

### 8.2 RAGAS 评估器 (ragas/ragas_eval.py)

```python
class RagasEvaluator(BaseEvaluator):
    """基于 RAGAS 库的评估器"""
    
    # 默认指标:
    # - Faithfulness (忠实度)
    # - AnswerRelevancy (答案相关性)
    # - ContextPrecision (上下文精确度)
    # - ContextRecall (上下文召回率)
    
    def evaluate_dataset(dataset) -> SummaryResult:
        """
        1. 将 EvalSample 转换为 HuggingFace Dataset
        2. 调用 ragas.evaluate(...)
        3. 配置 RunConfig (max_workers, timeout, batch_size)
        4. Pandas DataFrame → EvalResult 映射
        5. 计算平均分
        """
```

### 8.3 RAG 查询管道 (ragas/pipeline.py)

```python
class RAGQueryPipeline:
    """文档/代码仓库评估的完整管道"""
    
    def __init__(config_path, data_path):
        ...
    
    def add_documents(docs_dirs, wait, timeout) -> List[str]:
        """添加文档到 OpenViking"""
    
    def query(question, top_k, generate_answer) -> dict:
        """
        1. client.search(question, top_k)
        2. 提取上下文 + URI
        3. 可选: LLM 生成答案
        """
```

### 8.4 IO 录制器 (recorder/)

```python
class IORecorder:
    """线程安全的 IO 操作录制器, JSONL 持久化"""
    
    def record_fs(operation, request, response, latency_ms, ...) -> None:
        """录制文件系统操作"""
    
    def record_vikingdb(operation, request, response, latency_ms, ...) -> None:
        """录制向量数据库操作"""
    
    def get_records() -> List[IORecord]:
        """读取所有已录制的记录"""
    
    def get_stats() -> dict:
        """聚合统计"""

class RecordContext:
    """上下文管理器: 自动计时 + AGFS 调用收集"""
    # with RecordContext(recorder, "READ", io_type=IOType.FS):
    #     result = viking_fs.read(uri)
```

### 8.5 IO 重放 (ragas/playback.py)

```python
class IOPlayback:
    """重放录制的 IO 操作, 比较不同后端的性能"""
    
    def play(record_file, limit, offset, io_type, operation) -> PlaybackStats:
        """
        1. 读取 JSONL 记录文件
        2. 过滤记录 (io_type / operation)
        3. 逐条重放
        4. 比较响应
        5. 统计 (成功/失败/延迟/加速比)
        """

@dataclass
class PlaybackStats:
    total_records: int
    success_count: int
    error_count: int
    total_original_latency_ms: float
    total_playback_latency_ms: float
    speedup_ratio: float            # 加速比
    fs_stats: Dict                  # 按文件系统操作统计
    vikingdb_stats: Dict            # 按向量数据库操作统计
```

---

## 9. Grafana 仪表板 (examples/grafana/)

```json
// 预构建的 Grafana 仪表板:
// - openviking_demo_dashboard.json        # 演示仪表板
// - openviking_token_demo_dashboard.json  # Token 使用仪表板
// - openviking_feedback_baseline_dashboard.json # 反馈基线仪表板

// 部署:
// examples/grafana/docker-compose.yml      # Grafana + Prometheus
// examples/grafana/prometheus.yml          # Prometheus 抓取配置
```

---

## 10. 环境变量配置

| 变量 | 默认值 | 用途 |
|---|---|---|
| `RAGAS_LLM_API_KEY_ENV` | - | RAGAS 评估 LLM API Key |
| `RAGAS_LLM_API_BASE_ENV` | - | RAGAS 评估 LLM API Base |
| `RAGAS_LLM_MODEL_ENV` | - | RAGAS 评估 LLM 模型 |
| `RAGAS_MAX_WORKERS_ENV` | `16` | 最大并发工作线程 |
| `RAGAS_BATCH_SIZE_ENV` | `10` | 批处理大小 |
| `RAGAS_TIMEOUT_ENV` | `180` | 超时时间 (秒) |
| `RAGAS_MAX_RETRIES_ENV` | `3` | 最大重试次数 |
