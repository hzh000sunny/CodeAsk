import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { LlmConfigManager } from "./llm/LlmConfigManager";
import { RepoManager } from "./repos/RepoManager";

export function GlobalSettings() {
  return (
    <div className="settings-stack">
      <LlmConfigManager scope="global" />
      <RepoManager />
      <AnalysisPolicyManager
        description="全局策略会注入 Agent 上下文，约束问题定位、代码调查和最终回答。"
        scope="global"
        title="全局分析策略"
      />
    </div>
  );
}
