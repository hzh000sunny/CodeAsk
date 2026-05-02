import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Database,
  FilePlus2,
  GitBranch,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

import {
  createFeature,
  deleteFeature,
  deleteDocument,
  linkFeatureRepo,
  listFeatureRepos,
  listDocuments,
  listFeatures,
  listRepos,
  listReports,
  unlinkFeatureRepo,
  uploadDocument,
} from "../../lib/api";
import type {
  DocumentRead,
  FeatureRead,
  RepoOut,
  ReportRead,
} from "../../types/api";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { Tabs } from "../ui/tabs";
import { Textarea } from "../ui/textarea";

const tabs = [
  { id: "settings", label: "设置" },
  { id: "knowledge", label: "知识库" },
  { id: "reports", label: "问题报告" },
  { id: "repos", label: "关联仓库" },
  { id: "skill", label: "特性分析策略" },
];

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface FeatureWorkbenchProps {
  reportTarget?: ReportTarget | null;
}

export function FeatureWorkbench({ reportTarget }: FeatureWorkbenchProps) {
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
  const { data: fetchedFeatures = [], isLoading } = useQuery({
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
      <aside
        className="list-panel"
        data-collapsed={listCollapsed}
        role="region"
        aria-label="特性列表"
      >
        <button
          aria-label={listCollapsed ? "展开特性列表" : "收起特性列表"}
          className="edge-collapse-button secondary"
          data-collapsed={listCollapsed}
          onClick={() => setListCollapsed((value) => !value)}
          title={listCollapsed ? "展开特性列表" : "收起特性列表"}
          type="button"
        >
          {listCollapsed ? (
            <ChevronRight aria-hidden="true" size={15} />
          ) : (
            <ChevronLeft aria-hidden="true" size={15} />
          )}
        </button>
        {listCollapsed ? (
          <div className="collapsed-panel-label">特性</div>
        ) : (
          <>
            <div className="list-toolbar">
              <label className="search-field">
                <Search aria-hidden="true" size={16} />
                <Input
                  aria-label="搜索特性"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索特性"
                  value={query}
                />
              </label>
              <Button
                aria-label="添加特性"
                className="icon-only"
                icon={<Plus size={17} />}
                onClick={() => setShowCreate((value) => !value)}
                title="添加特性"
                type="button"
              />
            </div>
            <div className="list-scroll">
              {showCreate ? (
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    createMutation.mutate();
                  }}
                >
                  <label className="field-label compact">
                    特性名称
                    <Input
                      onChange={(event) => setFeatureName(event.target.value)}
                      placeholder="例如：风控策略"
                      value={featureName}
                    />
                  </label>
                  <label className="field-label compact">
                    描述
                    <Textarea
                      onChange={(event) =>
                        setFeatureDescription(event.target.value)
                      }
                      placeholder="补充边界、负责人和常见问题"
                      value={featureDescription}
                    />
                  </label>
                  <Button
                    disabled={!featureName.trim() || createMutation.isPending}
                    type="submit"
                    variant="primary"
                  >
                    创建特性
                  </Button>
                </form>
              ) : null}
              {isLoading ? <p className="empty-note">正在加载特性</p> : null}
              {!isLoading && visibleFeatures.length === 0 ? (
                <div className="empty-block">
                  <p>暂无特性</p>
                  <span>
                    点击右上角加号创建业务特性，再上传 Wiki、报告和仓库关联。
                  </span>
                </div>
              ) : null}
              {visibleFeatures.map((feature) => (
                <FeatureListItem
                  active={selected?.id === feature.id}
                  feature={feature}
                  key={feature.id}
                  onClick={() => setSelectedId(feature.id)}
                  onDelete={() => {
                    setDeleteCandidate(feature);
                    setDeleteError("");
                  }}
                  pendingDelete={deleteMutation.isPending}
                />
              ))}
            </div>
          </>
        )}
      </aside>

      <section className="detail-panel">
        <div className="page-header">
          <div>
            <h1>{selected?.name ?? "选择或创建特性"}</h1>
            <p>
              {selected?.description ??
                "特性内统一管理设置、知识库、问题报告、仓库关联和专属 Skill。"}
            </p>
          </div>
          <Badge>{selected?.slug ?? "feature"}</Badge>
        </div>

        <Tabs tabs={tabs} value={activeTab} onChange={setActiveTab}>
          <FeatureTabContent
            activeTab={activeTab}
            feature={selected}
            selectedReportId={reportTarget?.reportId ?? null}
          />
        </Tabs>
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

function FeatureListItem({
  active,
  feature,
  onClick,
  onDelete,
  pendingDelete,
}: {
  active: boolean;
  feature: FeatureRead;
  onClick: () => void;
  onDelete: () => void;
  pendingDelete: boolean;
}) {
  return (
    <div className="list-row" data-active={active}>
      <button
        className="list-item"
        data-active={active}
        onClick={onClick}
        type="button"
      >
        <span className="item-title">{feature.name}</span>
        <span className="item-meta">{feature.slug}</span>
      </button>
      <button
        aria-label={`删除特性 ${feature.name}`}
        className="list-delete-button"
        disabled={pendingDelete}
        onClick={onDelete}
        title="删除特性"
        type="button"
      >
        <Trash2 aria-hidden="true" size={15} />
      </button>
    </div>
  );
}

function DeleteFeatureDialog({
  errorMessage,
  featureName,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  errorMessage: string;
  featureName: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="delete-feature-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="delete-feature-title">删除特性</h2>
          <p>
            确认删除“{featureName}
            ”？删除后该特性的设置、关联关系和知识资料将不再从特性列表进入。
          </p>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button
              disabled={isDeleting}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={isDeleting}
              onClick={onConfirm}
              type="button"
              variant="danger"
            >
              {isDeleting ? "删除中" : "确认删除"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function FeatureTabContent({
  activeTab,
  feature,
  selectedReportId,
}: {
  activeTab: string;
  feature: FeatureRead | null;
  selectedReportId: number | null;
}) {
  if (activeTab === "settings") {
    return <FeatureSettings feature={feature} />;
  }
  if (activeTab === "knowledge") {
    return <KnowledgePanel featureId={feature?.id} />;
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

function FeatureSettings({ feature }: { feature: FeatureRead | null }) {
  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="section-title">
          <SlidersHorizontal aria-hidden="true" size={18} />
          <h2>特性设置</h2>
        </div>
        <label className="field-label">
          名称
          <Input
            readOnly
            value={feature?.name ?? ""}
            placeholder="选择一个特性后显示"
          />
        </label>
        <label className="field-label">
          描述
          <Textarea
            readOnly
            value={feature?.description ?? ""}
            placeholder="维护特性的业务边界和常见问题"
          />
        </label>
      </section>
      <section className="surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>治理信息</h2>
        </div>
        <dl className="meta-grid">
          <dt>Owner</dt>
          <dd>{feature?.owner_subject_id ?? "未创建"}</dd>
          <dt>更新时间</dt>
          <dd>
            {feature ? new Date(feature.updated_at).toLocaleString() : "-"}
          </dd>
        </dl>
      </section>
    </div>
  );
}

function KnowledgePanel({ featureId }: { featureId?: number }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<DocumentRead | null>(
    null,
  );
  const { data: fetchedDocuments = [] } = useQuery({
    queryKey: ["documents", featureId],
    queryFn: () => listDocuments(featureId),
    enabled: Boolean(featureId),
  });
  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const uploaded: DocumentRead[] = [];
      for (const file of files) {
        const relativePath = file.webkitRelativePath || file.name;
        uploaded.push(
          await uploadDocument({
            feature_id: featureId ?? 0,
            file,
            title: relativePath,
          }),
        );
      }
      return uploaded;
    },
    onSuccess: (documents) => {
      setStatus(`已上传 ${documents.length} 个 Wiki 文件`);
      void queryClient.invalidateQueries({
        queryKey: ["documents", featureId],
      });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      setSelectedDocument(null);
      setStatus("已删除 Wiki 文档");
      void queryClient.invalidateQueries({
        queryKey: ["documents", featureId],
      });
    },
  });

  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="content-toolbar">
          <div className="section-title">
            <Database aria-hidden="true" size={18} />
            <h2>知识库</h2>
          </div>
          <label className="file-button">
            <FilePlus2 aria-hidden="true" size={16} />
            上传 Wiki
            <input
              aria-label="选择 Wiki 文件或目录"
              accept=".md,.markdown,.txt,.pdf,.docx"
              disabled={!featureId || uploadMutation.isPending}
              multiple
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (files.length > 0) {
                  uploadMutation.mutate(files);
                }
              }}
              type="file"
              {...{ webkitdirectory: "" }}
            />
          </label>
        </div>
        {status ? <p className="action-status">{status}</p> : null}
        {fetchedDocuments.length === 0 ? (
          <div className="empty-block wide">
            <p>当前特性还没有上传 Wiki 文档。</p>
          </div>
        ) : (
          <ul className="data-list">
            {fetchedDocuments.map((document) => (
              <li key={document.id}>
                <button
                  className="plain-row-button"
                  onClick={() => setSelectedDocument(document)}
                  type="button"
                >
                  <span>{document.title}</span>
                  <small>
                    {document.kind} · {document.path}
                  </small>
                </button>
                <Button
                  disabled={deleteMutation.isPending}
                  icon={<Trash2 size={15} />}
                  onClick={() => deleteMutation.mutate(document.id)}
                  type="button"
                  variant="quiet"
                >
                  删除
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="surface">
        <div className="section-title">
          <FilePlus2 aria-hidden="true" size={18} />
          <h2>预览</h2>
        </div>
        {selectedDocument ? (
          <dl className="meta-grid">
            <dt>标题</dt>
            <dd>{selectedDocument.title}</dd>
            <dt>路径</dt>
            <dd>{selectedDocument.path}</dd>
            <dt>类型</dt>
            <dd>{selectedDocument.kind}</dd>
            <dt>上传人</dt>
            <dd>{selectedDocument.uploaded_by_subject_id}</dd>
            <dt>更新时间</dt>
            <dd>{new Date(selectedDocument.updated_at).toLocaleString()}</dd>
          </dl>
        ) : (
          <div className="empty-block wide">
            <p>选择左侧文档后预览元信息。</p>
          </div>
        )}
      </section>
    </div>
  );
}

function ReportsPanel({
  featureId,
  selectedReportId,
}: {
  featureId?: number;
  selectedReportId: number | null;
}) {
  const [selectedReport, setSelectedReport] = useState<ReportRead | null>(null);
  const { data: fetchedReports = [] } = useQuery({
    queryKey: ["reports", featureId],
    queryFn: () => listReports(featureId),
    enabled: Boolean(featureId),
  });

  useEffect(() => {
    if (!selectedReportId) {
      return;
    }
    const matched = fetchedReports.find(
      (report) => report.id === selectedReportId,
    );
    if (matched) {
      setSelectedReport(matched);
    }
  }, [fetchedReports, selectedReportId]);

  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>问题报告</h2>
        </div>
        {fetchedReports.length === 0 ? (
          <div className="empty-block wide">
            <p>暂无沉淀的问题报告。</p>
          </div>
        ) : (
          <ul className="data-list">
            {fetchedReports.map((report) => (
              <li key={report.id}>
                <button
                  className="plain-row-button"
                  onClick={() => setSelectedReport(report)}
                  type="button"
                >
                  <span>{report.title}</span>
                  <small>
                    {report.status} ·{" "}
                    {new Date(report.updated_at).toLocaleString()}
                  </small>
                </button>
                <Badge>{report.verified ? "已验证" : "草稿"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>报告详情</h2>
        </div>
        {selectedReport ? (
          <article className="report-preview">
            <div className="report-preview-title">{selectedReport.title}</div>
            <MarkdownRenderer content={selectedReport.body_markdown} />
          </article>
        ) : (
          <div className="empty-block wide">
            <p>选择左侧报告后查看详情。</p>
          </div>
        )}
      </section>
    </div>
  );
}

function ReposPanel({ featureId }: { featureId?: number }) {
  const queryClient = useQueryClient();
  const { data: globalRepos = [] } = useQuery({
    queryKey: ["repos"],
    queryFn: listRepos,
  });
  const { data: fetchedFeatureRepos = [] } = useQuery({
    queryKey: ["feature-repos", featureId],
    queryFn: () => listFeatureRepos(featureId ?? 0),
    enabled: Boolean(featureId),
  });
  const linkedIds = new Set(fetchedFeatureRepos.map((repo) => repo.id));
  const linkMutation = useMutation({
    mutationFn: async ({
      repo,
      checked,
    }: {
      repo: RepoOut;
      checked: boolean;
    }) => {
      if (!featureId) {
        return;
      }
      if (checked) {
        await linkFeatureRepo(featureId, repo.id);
      } else {
        await unlinkFeatureRepo(featureId, repo.id);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["feature-repos", featureId],
      });
    },
  });

  return (
    <div className="tab-content">
      <section className="surface">
        <div className="section-title">
          <GitBranch aria-hidden="true" size={18} />
          <h2>关联仓库</h2>
        </div>
        {globalRepos.length === 0 ? (
          <div className="empty-block wide">
            <p>仓库池中暂无仓库。</p>
          </div>
        ) : (
          <ul className="check-list">
            {globalRepos.map((repo) => (
              <li key={repo.id}>
                <label className="repo-check-row">
                  <input
                    checked={linkedIds.has(repo.id)}
                    disabled={!featureId || linkMutation.isPending}
                    onChange={(event) =>
                      linkMutation.mutate({
                        repo,
                        checked: event.target.checked,
                      })
                    }
                    type="checkbox"
                  />
                  <span>
                    <strong>{repo.name}</strong>
                    <small>
                      {repo.status} ·{" "}
                      {repo.source === "git" ? repo.url : repo.local_path}
                    </small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function mergeById<T extends { id: string | number }>(left: T[], right: T[]) {
  const rows = new Map<string | number, T>();
  for (const item of left) {
    rows.set(item.id, item);
  }
  for (const item of right) {
    rows.set(item.id, item);
  }
  return [...rows.values()];
}

function messageFromError(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败";
}
