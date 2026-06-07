import type { FeatureRead } from "../../types/api";
import type { WikiDrawer } from "../../lib/wiki/routing";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { Tabs } from "../ui/tabs";
import { FeatureAdminsPanel } from "./FeatureAdminsPanel";
import { FeatureSettings } from "./FeatureSettings";
import { KnowledgePanel } from "./KnowledgePanel";
import { ReportsPanel } from "./ReportsPanel";
import { ReposPanel } from "./ReposPanel";
import { useFeaturePermissions } from "./useFeaturePermissions";

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
  { id: "admins", label: "管理员" },
];

export function FeatureTabs({
  activeTab,
  feature,
  knowledgeNodeId,
  onChange,
  onKnowledgeNodeChange,
  onOpenWiki,
  selectedReportId,
}: {
  activeTab: string;
  feature: FeatureRead | null;
  knowledgeNodeId: number | null;
  onChange: (tab: string) => void;
  onKnowledgeNodeChange: (nodeId: number | null) => void;
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  selectedReportId: number | null;
}) {
  const { canManageFeature } = useFeaturePermissions(feature?.id);
  return (
    <Tabs tabs={tabs} value={activeTab} onChange={onChange}>
      <FeatureTabContent
        activeTab={activeTab}
        canManageFeature={canManageFeature}
        feature={feature}
        knowledgeNodeId={knowledgeNodeId}
        onKnowledgeNodeChange={onKnowledgeNodeChange}
        onOpenWiki={onOpenWiki}
        selectedReportId={selectedReportId}
      />
    </Tabs>
  );
}

function FeatureTabContent({
  activeTab,
  canManageFeature,
  feature,
  knowledgeNodeId,
  onKnowledgeNodeChange,
  onOpenWiki,
  selectedReportId,
}: {
  activeTab: string;
  canManageFeature: boolean;
  feature: FeatureRead | null;
  knowledgeNodeId: number | null;
  onKnowledgeNodeChange: (nodeId: number | null) => void;
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  selectedReportId: number | null;
}) {
  if (activeTab === "settings") {
    return <FeatureSettings canManageFeature={canManageFeature} feature={feature} />;
  }
  if (activeTab === "knowledge") {
    return (
      <KnowledgePanel
        featureId={feature?.id}
        featureName={feature?.name ?? null}
        onOpenWiki={(featureId, options) => onOpenWiki(featureId, options)}
        onSelectedNodeChange={onKnowledgeNodeChange}
        selectedNodeId={knowledgeNodeId}
      />
    );
  }
  if (activeTab === "reports") {
    return (
      <ReportsPanel
        canManageFeature={canManageFeature}
        featureId={feature?.id}
        selectedReportId={selectedReportId}
      />
    );
  }
  if (activeTab === "repos") {
    return <ReposPanel canManageFeature={canManageFeature} featureId={feature?.id} />;
  }
  if (activeTab === "admins") {
    return <FeatureAdminsPanel featureId={feature?.id} />;
  }
  return (
    <AnalysisPolicyManager
      description="特性策略只在该特性的上下文中注入，用于补充业务术语、排查习惯和输出要求。"
      featureId={feature?.id}
      readOnly={!canManageFeature}
      scope="feature"
      title="特性分析策略"
    />
  );
}
