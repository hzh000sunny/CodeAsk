import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";

import { createFeature, deleteFeature, listFeatures } from "../../lib/api";
import type { FeatureRead } from "../../types/api";
import type { FeatureRouteState, FeatureTabId } from "../../lib/wiki/routing";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { DeleteFeatureDialog } from "./FeatureDialogs";
import { FeatureListPanel } from "./FeatureListPanel";
import { FeatureTabs, type FeatureWikiOpenOptions } from "./FeatureTabs";
import { mergeById, messageFromError } from "./feature-utils";
import { useFeaturePermissions } from "./useFeaturePermissions";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface FeatureWorkbenchProps {
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  onRouteChange: (patch: Partial<FeatureRouteState>) => void;
  reportTarget?: ReportTarget | null;
  routeFeatureId: number | null;
  routeNodeId: number | null;
  routeTab: FeatureTabId | null;
}

export function FeatureWorkbench({
  onOpenWiki,
  onRouteChange,
  reportTarget,
  routeFeatureId,
  routeNodeId,
  routeTab,
}: FeatureWorkbenchProps) {
  const queryClient = useQueryClient();
  const { showError } = useAppFeedback();
  const [query, setQuery] = useState("");
  // 选中的特性与子 tab 改由路由驱动（AppRouteState.features），跨页面切换/刷新都能恢复。
  const activeTab = routeTab ?? "settings";
  const [listCollapsed, setListCollapsed] = useState(false);
  const [createdFeatures, setCreatedFeatures] = useState<FeatureRead[]>([]);
  const [deletedFeatureIds, setDeletedFeatureIds] = useState<number[]>([]);
  const [deleteCandidate, setDeleteCandidate] = useState<FeatureRead | null>(
    null,
  );
  const [deleteError, setDeleteError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [featureName, setFeatureName] = useState("");
  const [featureDescription, setFeatureDescription] = useState("");
  const {
    data: fetchedFeatures = [],
    error: featuresError,
    isError: hasFeaturesError,
    isFetching: isFetchingFeatures,
    isLoading,
  } = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  // 进入本页时若缓存里躺着一条旧错误（比如会话页早先拉 features 失败过），
  // react-query 会立刻在后台重拉；重拉期间不把旧错误弹给用户，
  // 只有这一轮真的失败落定（isFetching 归 false）才提示。
  const settledFeaturesError = hasFeaturesError && !isFetchingFeatures;
  const features = mergeById(fetchedFeatures, createdFeatures).filter(
    (feature) => !deletedFeatureIds.includes(feature.id),
  );

  // 选中特性 + reports tab 由 AppShell 在打开报告时写入路由；这里只需清空搜索，
  // 保证目标特性一定出现在过滤后的列表里。
  useEffect(() => {
    if (!reportTarget) {
      return;
    }
    setQuery("");
  }, [reportTarget]);

  const createMutation = useMutation({
    mutationFn: () =>
      createFeature({
        name: featureName.trim(),
        description: featureDescription.trim() || undefined,
      }),
    onSuccess: (feature) => {
      setCreatedFeatures((current) => mergeById(current, [feature]));
      onRouteChange({ featureId: feature.id, nodeId: null });
      setShowCreate(false);
      setFeatureName("");
      setFeatureDescription("");
      void queryClient.invalidateQueries({ queryKey: ["features"] });
    },
    onError: (error) => {
      showError(`创建特性失败：${messageFromError(error)}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (featureId: number) => deleteFeature(featureId),
    onSuccess: (_unused, featureId) => {
      setDeletedFeatureIds((current) => [...new Set([...current, featureId])]);
      setCreatedFeatures((current) =>
        current.filter((feature) => feature.id !== featureId),
      );
      if (routeFeatureId === featureId) {
        onRouteChange({ featureId: null, nodeId: null });
      }
      setDeleteCandidate(null);
      setDeleteError("");
      void queryClient.invalidateQueries({ queryKey: ["features"] });
    },
    onError: (error) => {
      setDeleteError(`删除特性失败：${messageFromError(error)}`);
    },
  });

  const visibleFeatures = useMemo(() => {
    return features.filter((feature) => {
      const haystack =
        `${feature.name} ${feature.slug} ${feature.description ?? ""}`.toLowerCase();
      return haystack.includes(query.toLowerCase());
    });
  }, [features, query]);
  const selected =
    visibleFeatures.find((item) => item.id === routeFeatureId) ??
    visibleFeatures[0] ??
    null;
  const { canCreateFeature, isAdmin } = useFeaturePermissions(selected?.id);

  // 当路由没有指向有效特性（首次进入、或 localStorage 里是已删除的旧 id）时，
  // 把自动选中的第一个特性写回路由，使 URL/持久化反映真实选中。
  // 路由指向的特性只是被搜索过滤掉时不覆盖（features 里仍存在）。
  useEffect(() => {
    if (selected == null || routeFeatureId === selected.id) {
      return;
    }
    if (routeFeatureId != null && features.some((item) => item.id === routeFeatureId)) {
      return;
    }
    onRouteChange({ featureId: selected.id });
  }, [features, onRouteChange, routeFeatureId, selected]);

  return (
    <section
      className="workspace feature-workspace"
      data-list-collapsed={listCollapsed}
      aria-label="特性工作台"
    >
      <FeatureListPanel
        createPending={createMutation.isPending}
        featureDescription={featureDescription}
        featureName={featureName}
        loadErrorMessage={
          settledFeaturesError
            ? `加载特性失败：${messageFromError(featuresError)}`
            : ""
        }
        isLoading={isLoading}
        listCollapsed={listCollapsed}
        onCreateSubmit={() => createMutation.mutate()}
        onDelete={(feature) => {
          setDeleteCandidate(feature);
          setDeleteError("");
        }}
        onFeatureDescriptionChange={setFeatureDescription}
        onFeatureNameChange={setFeatureName}
        onQueryChange={setQuery}
        onSelect={(featureId) => onRouteChange({ featureId, nodeId: null })}
        onShowCreateChange={(value) => {
          if (value && !canCreateFeature) {
            showError("请联系管理员添加", { title: "无权创建特性" });
            return;
          }
          setShowCreate(value);
        }}
        onToggleCollapsed={() => setListCollapsed((value) => !value)}
        pendingDelete={deleteMutation.isPending}
        query={query}
        selectedFeatureId={selected?.id ?? null}
        showCreate={showCreate}
        visibleFeatures={visibleFeatures}
        canDeleteFeatures={isAdmin}
      />

      <section className="detail-panel">
        <div className="page-header feature-header">
          <div className="feature-header-main">
            <h1>{selected?.name ?? "选择或创建特性"}</h1>
            {/* slug 不进报头（沿用既有产品决策，见 feature-workbench 测试）。
                去掉旧的每特性重复样板话：有描述才显示描述，没选中时给一句引导，
                选中但无描述时不占位（设置页可补描述）。 */}
            {selected ? (
              selected.description ? (
                <p className="feature-header-description">
                  {selected.description}
                </p>
              ) : null
            ) : (
              <p className="feature-header-description">
                从左侧选择一个特性，或点击 + 新建。
              </p>
            )}
          </div>
          {selected ? (
            <div className="header-actions">
              <Button
                icon={<BookOpen aria-hidden="true" size={15} />}
                onClick={() => onOpenWiki(selected.id)}
                type="button"
                variant="secondary"
              >
                打开 Wiki
              </Button>
            </div>
          ) : null}
        </div>

        <FeatureTabs
          activeTab={activeTab}
          feature={selected}
          knowledgeNodeId={routeNodeId}
          onChange={(tab) => onRouteChange({ tab: tab as FeatureTabId })}
          onKnowledgeNodeChange={(nodeId) => onRouteChange({ nodeId })}
          onOpenWiki={onOpenWiki}
          selectedReportId={reportTarget?.reportId ?? null}
        />
      </section>
      {deleteCandidate ? (
        <DeleteFeatureDialog
          errorMessage={deleteError}
          featureName={deleteCandidate.name}
          isDeleting={deleteMutation.isPending}
          onCancel={() => {
            if (!deleteMutation.isPending) {
              setDeleteCandidate(null);
              setDeleteError("");
            }
          }}
          onConfirm={() => deleteMutation.mutate(deleteCandidate.id)}
        />
      ) : null}
    </section>
  );
}
