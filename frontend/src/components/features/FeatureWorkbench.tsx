import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createFeature, deleteFeature, listFeatures } from "../../lib/api";
import type { FeatureRead } from "../../types/api";
import { DeleteFeatureDialog } from "./FeatureDialogs";
import { FeatureListPanel } from "./FeatureListPanel";
import { FeatureTabs, type FeatureWikiOpenOptions } from "./FeatureTabs";
import { mergeById, messageFromError } from "./feature-utils";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface FeatureWorkbenchProps {
  onOpenWiki: (featureId: number, options?: FeatureWikiOpenOptions) => void;
  reportTarget?: ReportTarget | null;
}

export function FeatureWorkbench({
  onOpenWiki,
  reportTarget,
}: FeatureWorkbenchProps) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("settings");
  const [selectedId, setSelectedId] = useState<number | null>(null);
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
    isLoading,
  } = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const features = mergeById(fetchedFeatures, createdFeatures).filter(
    (feature) => !deletedFeatureIds.includes(feature.id),
  );

  useEffect(() => {
    if (!reportTarget) {
      return;
    }
    setQuery("");
    setSelectedId(reportTarget.featureId);
    setActiveTab("reports");
  }, [reportTarget]);

  const createMutation = useMutation({
    mutationFn: () =>
      createFeature({
        name: featureName.trim(),
        description: featureDescription.trim() || undefined,
      }),
    onSuccess: (feature) => {
      setCreatedFeatures((current) => mergeById(current, [feature]));
      setSelectedId(feature.id);
      setShowCreate(false);
      setFeatureName("");
      setFeatureDescription("");
      void queryClient.invalidateQueries({ queryKey: ["features"] });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (featureId: number) => deleteFeature(featureId),
    onSuccess: (_unused, featureId) => {
      setDeletedFeatureIds((current) => [...new Set([...current, featureId])]);
      setCreatedFeatures((current) =>
        current.filter((feature) => feature.id !== featureId),
      );
      if (selectedId === featureId) {
        setSelectedId(null);
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
    visibleFeatures.find((item) => item.id === selectedId) ??
    visibleFeatures[0] ??
    null;

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
          hasFeaturesError
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
        onSelect={setSelectedId}
        onShowCreateChange={setShowCreate}
        onToggleCollapsed={() => setListCollapsed((value) => !value)}
        pendingDelete={deleteMutation.isPending}
        query={query}
        selectedFeatureId={selected?.id ?? null}
        showCreate={showCreate}
        visibleFeatures={visibleFeatures}
      />

      <section className="detail-panel">
        <div className="page-header">
          <div>
            <h1>{selected?.name ?? "选择或创建特性"}</h1>
            <p>
              {selected?.description ??
                "特性内统一管理设置、知识库、问题报告、仓库关联和专属 Skill。"}
            </p>
          </div>
          <div className="header-actions">
            {selected ? (
              <button
                className="button button-secondary"
                onClick={() => onOpenWiki(selected.id)}
                type="button"
              >
                打开 Wiki
              </button>
            ) : null}
          </div>
        </div>

        <FeatureTabs
          activeTab={activeTab}
          feature={selected}
          onChange={setActiveTab}
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
