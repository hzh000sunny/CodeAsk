import type { FeatureRead } from "../../types/api";
import type { WikiDrawer } from "../../lib/wiki/routing";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { Tabs } from "../ui/tabs";
import { FeatureSettings } from "./FeatureSettings";
import { KnowledgePanel } from "./KnowledgePanel";
import { ReportsPanel } from "./ReportsPanel";
import { ReposPanel } from "./ReposPanel";

export interface FeatureWikiOpenOptions {
  drawer?: Exclude<WikiDrawer, "detail" | "history"> | null;
  nodeId?: number | null;
}

const tabs = [
  { id: "settings", label: "设置" },
  { id: "knowledge", label: "知识库" },
  { id: "reports", label: "问题报告" },
  { id: "repos", label: "关联仓库" },
  { id: "skill", label: "特性分析策略" },
];

export function FeatureTabs({
  activeTab,
  feature,
  onChange,
  onOpenWiki,
  selectedReportId,
}: {
  activeTab: string;
  feature: FeatureRead | null;
  onChange: (tab: string) => void;
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  selectedReportId: number | null;
}) {
  return (
    <Tabs tabs={tabs} value={activeTab} onChange={onChange}>
      <FeatureTabContent
        activeTab={activeTab}
        feature={feature}
        onOpenWiki={onOpenWiki}
        selectedReportId={selectedReportId}
      />
    </Tabs>
  );
}

function FeatureTabContent({
  activeTab,
  feature,
  onOpenWiki,
  selectedReportId,
}: {
  activeTab: string;
  feature: FeatureRead | null;
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  selectedReportId: number | null;
}) {
  if (activeTab === "settings") {
    return <FeatureSettings feature={feature} />;
  }
  if (activeTab === "knowledge") {
    return (
      <KnowledgePanel
        featureId={feature?.id}
        onOpenWiki={(featureId, options) => onOpenWiki(featureId, options)}
      />
    );
  }
  if (activeTab === "reports") {
    return (
      <ReportsPanel
        featureId={feature?.id}
        selectedReportId={selectedReportId}
      />
    );
  }
  if (activeTab === "repos") {
    return <ReposPanel featureId={feature?.id} />;
  }
  return (
    <AnalysisPolicyManager
      description="特性策略只在该特性的上下文中注入，用于补充业务术语、排查习惯和输出要求。"
      featureId={feature?.id}
      scope="feature"
      title="特性分析策略"
    />
  );
}
