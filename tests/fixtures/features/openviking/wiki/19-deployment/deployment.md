# 19 部署

## 1. Docker 部署

### 1.1 Dockerfile

多阶段构建:
```dockerfile
# 阶段 1: 构建 (Rust + C++ + Python)
FROM python:3.12-slim AS builder
# 安装: curl, gcc, g++, cmake, pkg-config, libssl-dev
# 安装 Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# 构建: make build

# 阶段 2: 运行
FROM python:3.12-slim
# 复制 Python 包 + 编译好的 .so 文件
# 复制 Rust CLI 二进制
# 安装运行时依赖
```

### 1.2 docker-compose.yml

```yaml
services:
  openviking:
    build: .
    ports:
      - "1933:1933"     # OpenViking API
      - "8020:8020"     # Web 控制台
      - "5000:5000"     # VikingDB HTTP 服务
    volumes:
      - openviking_data:/data/openviking_workspace
      - ./ov.conf:/root/.openviking/ov.conf
    environment:
      - OPENVIKING_CONFIG_FILE=/root/.openviking/ov.conf
      - OPENVIKING_WITH_BOT=1
    restart: unless-stopped

volumes:
  openviking_data:
```

### 1.3 Caddyfile

```caddyfile
# 反向代理配置
openviking.example.com {
    reverse_proxy localhost:1933
    encode gzip
}
```

### 1.4 容器内辅助服务

```python
# docker/pending_health_server.py
# 启动期间的占位符健康检查服务器
# 在实际服务就绪前返回 503

# docker/openviking-console-entrypoint.sh
# 控制台容器入口脚本
```

---

## 2. Helm Charts (deploy/helm/)

### 2.1 Chart 结构

```
deploy/helm/openviking/
├── Chart.yaml              # Chart 元数据
├── values.yaml             # 默认值
├── .helmignore
└── templates/
    ├── _helpers.tpl        # 模板助手
    ├── configmap.yaml      # 配置 ConfigMap
    ├── deployment.yaml     # Kubernetes Deployment
    ├── service.yaml        # Service
    ├── ingress.yaml        # Ingress
    ├── pvc.yaml            # 持久卷声明
    └── NOTES.txt           # 安装后提示
```

### 2.2 核心模板

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: openviking
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          ports:
            - containerPort: 1933
              name: http
            - containerPort: 8020
              name: console
            - containerPort: 5000
              name: vikingdb
          volumeMounts:
            - name: data
              mountPath: /data/openviking_workspace
            - name: config
              mountPath: /root/.openviking
          env:
            - name: OPENVIKING_CONFIG_FILE
              value: /root/.openviking/ov.conf
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {{ include "openviking.fullname" . }}-data
        - name: config
          configMap:
            name: {{ include "openviking.fullname" . }}-config

# service.yaml
apiVersion: v1
kind: Service
spec:
  ports:
    - port: 1933
      targetPort: 1933
      name: http
    - port: 8020
      targetPort: 8020
      name: console

# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
spec:
  rules:
    - host: {{ .Values.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "openviking.fullname" . }}
                port:
                  number: 1933

# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
```

---

## 3. VikingBot 部署

### 3.1 Docker

```bash
# bot/deploy/docker/
./build-image.sh              # 构建 VikingBot 镜像
./build-multiarch.sh          # 多架构构建 (amd64 + arm64)
./deploy.sh                   # 启动部署
./stop.sh                     # 停止服务

# 可选: Langfuse 可观测性
./deploy_langfuse.sh          # 启动 Langfuse (docker-compose)
```

### 3.2 ECS 部署

```bash
# bot/deploy/ecs/
# README.md 包含 ECS 部署说明
```

### 3.3 VKE (火山引擎 K8s) 部署

```bash
# bot/deploy/vke/
./deploy.sh                   # 部署到 VKE

# K8s 资源:
# - deployment.yaml: VikingBot Deployment
# - pvc-nas-example.yaml: NAS PVC 示例
# - pvc-tos-example.yaml: TOS PVC 示例
# - pvc-tos.yaml: TOS PVC 配置
```

---

## 4. K8s Helm (示例, examples/k8s-helm/)

```yaml
# examples/k8s-helm/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── secret.yaml      # 加密配置 Secret
    ├── _helpers.tpl
    └── NOTES.txt
```

---

## 5. 管理脚本 (bot/scripts/)

| 脚本 | 用途 |
|---|---|
| `restart_openviking_server.sh` | 重启 OpenViking 服务器 |
| `kill_openviking_server.sh` | 停止 OpenViking 服务器 |
| `test_restart_openviking_server.sh` | 测试重启流程 |
| `clean_vikingbot.sh` | 清理 VikingBot 数据 |
| `start_vikingbot_in_ecs.sh` | ECS 启动脚本 |
| `install_local_openclaw_plugin.sh` | 安装本地 OpenClaw 插件 |
| `test_all.sh` | 运行所有测试 |

---

## 6. 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `OPENVIKING_CONFIG_FILE` | `~/.openviking/ov.conf` | 服务器配置文件路径 |
| `OPENVIKING_CLI_CONFIG_FILE` | `~/.openviking/ovcli.conf` | CLI 配置文件路径 |
| `OPENVIKING_PROMPT_TEMPLATES_DIR` | (内置) | 自定义提示词模板目录 |
| `OPENVIKING_UPLOAD_MODE` | `shared` | 上传模式 (shared/local) |
| `OV_ENGINE_VARIANT` | (自动) | 向量引擎变体 (x86_sse3/x86_avx2/...) |
| `VIKINGBOT_ENDPOINT` | - | VikingBot 端点 (ov chat 使用) |
| `VIKINGBOT_API_KEY` | - | VikingBot API Key |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTel 导出端点 |
| `OPENVIKING_WITH_BOT` | `1` | Docker 中是否启用 VikingBot |
