# 06 — 部署与运维

## 概述

AnythingLLM 支持多种部署方式，从单机 Docker 到 Kubernetes 集群。

## Docker 部署

**文件**: `docker/`

### Dockerfile
- 基于 Node.js 的多阶段构建
- 包含 Server + Frontend + Collector
- Healthcheck 支持

### docker-compose.yml
- 单命令启动完整应用栈
- 环境变量通过 `.env` 文件配置
- 持久化存储卷

### 入口脚本
- `docker-entrypoint.sh`: 初始化配置
- `docker-healthcheck.sh`: 健康检查

## 云平台部署

### AWS CloudFormation
**文件**: `cloud-deployments/aws/cloudformation/`

- `cloudformation_create_anythingllm.json`: 完整 AWS 资源栈
- 支持一键部署到 AWS
- 自动配置 EC2、安全组、存储

### Google Cloud Platform
**文件**: `cloud-deployments/gcp/deployment/`

- `gcp_deploy_anything_llm.yaml`: GCP 部署模板
- Deployment Manager 配置

### DigitalOcean
**文件**: `cloud-deployments/digitalocean/terraform/`

- `main.tf`: Terraform 主配置
- `outputs.tf`: 输出定义
- `user_data.tp1`: Droplet 初始化脚本

### OpenShift
**文件**: `cloud-deployments/openshift/`

- OpenShift 兼容的 Dockerfile
- 自定义入口脚本
- Red Hat 容器平台说明

### HuggingFace Spaces
**文件**: `cloud-deployments/huggingface-spaces/`

- HuggingFace Spaces 专用 Dockerfile
- 免费 GPU 推理支持

### Kubernetes (Helm)
**文件**: `cloud-deployments/helm/charts/anythingllm/`

| 模板 | 用途 |
|------|------|
| `deployment.yaml` | Kubernetes Deployment 定义 |
| `serviceaccount.yaml` | Service Account |
| `configmap.yaml` | ConfigMap 配置 |
| `pvc.yaml` | 持久卷声明 |
| `ingress.yaml` | Ingress 路由 |
| `httproute.yaml` | HTTPRoute (Gateway API) |
| `extra-objects.yaml` | 额外自定义资源 |
| `_helpers.tpl` | 命名和标签助手 |

### 通用 K8s 清单
**文件**: `cloud-deployments/k8/manifest.yaml`

标准 Kubernetes YAML 清单。

## 裸机部署

**文件**: `BARE_METAL.md`
- 手动安装指南
- Node.js 环境要求
- 生产环境配置

## VSCode / 开发容器

**文件**: `.devcontainer/devcontainer.json`
- GitHub Codespaces 支持
- 预配置开发环境

## 环境变量配置

关键环境变量文件:
- `server/.env.example`: Server 环境变量模板
- `collector/.env.example`: Collector 环境变量模板
- `frontend/.env.example`: Frontend 环境变量模板
- `docker/.env.example`: Docker 环境变量模板

## 安全扫描

**文件**: `docker/vex/`
- CVE 豁免文件（VEX 格式）
- 覆盖的安全漏洞: CVE-2024-29415, CVE-2019-10790, CVE-2024-4068, CVE-2024-37890
