# OpenViking 集成边界声明

> 版本归属：v1.0.5
> 状态：Recorded
> 性质：边界承诺记录，不是合规审查
> 关联：[PRD](../prd/rag-knowledge.md) · [SDD](../design/openviking-integration.md)

---

## 1. 上游许可证

OpenViking 仓库 LICENSE 为 GNU Affero General Public License v3（AGPL-3.0）；部分 CLI / 示例文件为 Apache-2.0。本文记录 CodeAsk v1.0.5 集成 OpenViking 时的稳定边界，确保 AGPL 的强 copyleft 条款不会被无意触发。

> 用户判断：当前 CodeAsk 不修改 OpenViking 任何内容，也不规划做 SaaS，因此 AGPL 不会对 CodeAsk 构成风险。本文档只用于把这一边界写成可追溯的承诺，不再走正式合规审查。

---

## 2. CodeAsk 的两项承诺

| 承诺 | 落地证据 |
|---|---|
| **不修改 OpenViking 源码** | v1.0.5 不 fork、不复制、不打补丁；CodeAsk 仓库内不出现任何 OpenViking 源文件；适配代码全部在 `src/codeask/rag/openviking/` |
| **不内嵌 OpenViking 源码** | CodeAsk 通过 `uvx --from openviking==0.3.17` 拉起独立 `openviking-server` 子进程；适配层只通过 HTTP / MCP 调用，不把 OpenViking 作为 Python 业务依赖导入 |

进一步的隔离约定（技术上倾向，非强制）：

- CodeAsk 与 OpenViking 以**独立进程**形式通过 HTTP / MCP 调用，不在 CodeAsk 进程内 `import openviking` 作为业务代码
- CodeAsk 不重新分发 OpenViking 二进制；INSTALL 文档指向官方 PyPI 包

---

## 3. 文档披露项

- `README.md` 在"开源参考"小节追加 OpenViking 行，标注：上游链接、许可证 AGPL-3.0、CodeAsk 不修改源码
- `INSTALL.md`（或 v1.0.5 部署说明）注明：OpenViking 是外部子进程组件，由 CodeAsk 通过 `uvx --from openviking==0.3.17` 启动；不随 CodeAsk 主包默认安装，也不在业务代码中 `import openviking`
- `docs/v1.0.5/README.md` 末尾"引用"小节保留 OpenViking 仓库路径

---

## 4. 何时回访本文档

如果未来出现以下任何情况，再回到本文档评估：

- CodeAsk 决定 fork 或修改 OpenViking 源码
- CodeAsk 决定以 SaaS / 托管服务形式对外提供
- CodeAsk 把 OpenViking 一并打包进 docker / 安装件直接分发
- OpenViking 自身许可证发生变化

在以上情况发生前，本文档保持当前状态即可。

---

## 5. 参考资料

- OpenViking 本地路径：`/home/hzh/wiki/OpenViking`
- OpenViking 上游仓库：`github.com/volcengine/OpenViking`
- AGPL-3.0 原文：`https://www.gnu.org/licenses/agpl-3.0.html`
- FSF 关于"socket / pipe / RPC 是否构成衍生作品"的官方立场：mere aggregation 一般不视为衍生作品
- 设计前史许可证段落：[`../../future/rag-knowledge-pipeline.md`](../../future/rag-knowledge-pipeline.md) §11
