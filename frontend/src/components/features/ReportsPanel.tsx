import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  FilePenLine,
  RotateCcw,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";

import {
  deleteReport,
  listReports,
  rejectReport,
  unverifyReport,
  updateReport,
  verifyReport,
} from "../../lib/api";
import type { ReportRead } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { Textarea } from "../ui/textarea";
import { messageFromError } from "./feature-utils";

type ActionStatus = {
  message: string;
  tone: "success" | "danger";
};

export function ReportsPanel({
  featureId,
  selectedReportId,
}: {
  featureId?: number;
  selectedReportId: number | null;
}) {
  const queryClient = useQueryClient();
  const reportsQueryKey = ["reports", featureId] as const;
  const [selectedLocalReportId, setSelectedLocalReportId] = useState<
    number | null
  >(selectedReportId);
  const [statusFilter, setStatusFilter] = useState("all");
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [actionStatus, setActionStatus] = useState<ActionStatus | null>(null);
  const { data: fetchedReports = [] } = useQuery({
    queryKey: reportsQueryKey,
    queryFn: () => listReports(featureId),
    enabled: Boolean(featureId),
  });
  const selectedReport =
    fetchedReports.find((report) => report.id === selectedLocalReportId) ??
    null;
  const statusFilters = useMemo(
    () => reportStatusFilters(fetchedReports),
    [fetchedReports],
  );
  const filteredReports = useMemo(() => {
    if (statusFilter === "all") {
      return fetchedReports;
    }
    return fetchedReports.filter(
      (report) => reportStatusKey(report) === statusFilter,
    );
  }, [fetchedReports, statusFilter]);

  useEffect(() => {
    if (!selectedReportId) {
      return;
    }
    setSelectedLocalReportId(selectedReportId);
    setStatusFilter("all");
    setIsEditing(false);
    setActionStatus(null);
  }, [selectedReportId]);

  const updateMutation = useMutation({
    mutationFn: ({
      reportId,
      title,
      bodyMarkdown,
    }: {
      reportId: number;
      title: string;
      bodyMarkdown: string;
    }) =>
      updateReport(reportId, {
        title,
        body_markdown: bodyMarkdown,
      }),
    onSuccess: (report) => {
      cacheReport(report);
      setSelectedLocalReportId(report.id);
      setIsEditing(false);
      setActionStatus({ message: "报告已保存", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: reportsQueryKey });
    },
    onError: (error) => {
      setActionStatus({
        message: `保存报告失败：${messageFromError(error)}`,
        tone: "danger",
      });
    },
  });
  const verifyMutation = useMutation({
    mutationFn: verifyReport,
    onSuccess: (report) => {
      cacheReport(report);
      setSelectedLocalReportId(report.id);
      setActionStatus({ message: "报告已验证通过", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: reportsQueryKey });
    },
    onError: (error) => {
      setActionStatus({
        message: `验证报告失败：${messageFromError(error)}`,
        tone: "danger",
      });
    },
  });
  const rejectMutation = useMutation({
    mutationFn: rejectReport,
    onSuccess: (report) => {
      cacheReport(report);
      setSelectedLocalReportId(report.id);
      setActionStatus({ message: "报告已标记为未通过", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: reportsQueryKey });
    },
    onError: (error) => {
      setActionStatus({
        message: `标记未通过失败：${messageFromError(error)}`,
        tone: "danger",
      });
    },
  });
  const unverifyMutation = useMutation({
    mutationFn: unverifyReport,
    onSuccess: (report) => {
      cacheReport(report);
      setSelectedLocalReportId(report.id);
      setActionStatus({ message: "报告已撤销验证", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: reportsQueryKey });
    },
    onError: (error) => {
      setActionStatus({
        message: `撤销验证失败：${messageFromError(error)}`,
        tone: "danger",
      });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteReport,
    onSuccess: (_unused, reportId) => {
      removeReportFromCache(reportId);
      setSelectedLocalReportId(null);
      setIsEditing(false);
      setActionStatus({ message: "报告已删除", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: reportsQueryKey });
    },
    onError: (error) => {
      setActionStatus({
        message: `删除报告失败：${messageFromError(error)}`,
        tone: "danger",
      });
    },
  });
  const isActionPending =
    updateMutation.isPending ||
    verifyMutation.isPending ||
    rejectMutation.isPending ||
    unverifyMutation.isPending ||
    deleteMutation.isPending;

  function cacheReport(report: ReportRead) {
    queryClient.setQueryData<ReportRead[]>(reportsQueryKey, (current = []) => {
      if (current.some((item) => item.id === report.id)) {
        return current.map((item) => (item.id === report.id ? report : item));
      }
      return [report, ...current];
    });
  }

  function removeReportFromCache(reportId: number) {
    queryClient.setQueryData<ReportRead[]>(reportsQueryKey, (current = []) =>
      current.filter((report) => report.id !== reportId),
    );
  }

  function selectReport(report: ReportRead) {
    setSelectedLocalReportId(report.id);
    setIsEditing(false);
    setActionStatus(null);
  }

  function openEditor() {
    if (!selectedReport) {
      return;
    }
    setEditTitle(selectedReport.title);
    setEditBody(selectedReport.body_markdown);
    setIsEditing(true);
    setActionStatus(null);
  }

  function saveReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedReport) {
      return;
    }
    updateMutation.mutate({
      reportId: selectedReport.id,
      title: editTitle.trim() || selectedReport.title,
      bodyMarkdown: editBody,
    });
  }

  function confirmDelete() {
    if (!selectedReport) {
      return;
    }
    const confirmed = window.confirm("确认删除这份问题报告？删除后无法恢复。");
    if (!confirmed) {
      return;
    }
    deleteMutation.mutate(selectedReport.id);
  }

  return (
    <div className="tab-content two-column reports-tab-content">
      <section className="surface report-list-surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>问题报告</h2>
        </div>
        <div
          aria-label="报告状态筛选"
          className="report-filter-tabs"
          role="tablist"
        >
          {statusFilters.map((filter) => (
            <button
              aria-selected={statusFilter === filter.id}
              className="report-filter-button"
              key={filter.id}
              onClick={() => {
                setStatusFilter(filter.id);
                setSelectedLocalReportId(null);
                setIsEditing(false);
                setActionStatus(null);
              }}
              role="tab"
              type="button"
            >
              <span>{filter.label}</span>
              <small>{filter.count}</small>
            </button>
          ))}
        </div>
        {fetchedReports.length === 0 ? (
          <div className="empty-block wide">
            <p>暂无沉淀的问题报告。</p>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="empty-block wide">
            <p>当前状态下暂无报告。</p>
          </div>
        ) : (
          <ul className="data-list">
            {filteredReports.map((report) => (
              <li key={report.id}>
                <button
                  className="plain-row-button"
                  onClick={() => selectReport(report)}
                  type="button"
                >
                  <span>{report.title}</span>
                  <small>
                    {reportStatusLabel(report)} ·{" "}
                    {new Date(report.updated_at).toLocaleString()}
                  </small>
                </button>
                <Badge>{reportStatusLabel(report)}</Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="surface report-detail-surface">
        <div className="report-detail-header">
          <div className="section-title">
            <ShieldCheck aria-hidden="true" size={18} />
            <h2>报告详情</h2>
          </div>
          {selectedReport ? (
            <Badge>{reportStatusLabel(selectedReport)}</Badge>
          ) : null}
        </div>
        {actionStatus ? (
          <p
            aria-live="polite"
            className="action-status inline report-action-status"
            data-tone={actionStatus.tone}
          >
            {actionStatus.message}
          </p>
        ) : null}
        {selectedReport ? (
          <>
            <div aria-label="报告操作" className="report-detail-actions">
              <Button
                disabled={isActionPending}
                icon={<FilePenLine aria-hidden="true" size={16} />}
                onClick={openEditor}
                type="button"
                variant="secondary"
              >
                编辑报告
              </Button>
              {reportStatusKey(selectedReport) === "verified" ? (
                <Button
                  disabled={isActionPending}
                  icon={<RotateCcw aria-hidden="true" size={16} />}
                  onClick={() => unverifyMutation.mutate(selectedReport.id)}
                  type="button"
                  variant="secondary"
                >
                  撤销验证
                </Button>
              ) : (
                <>
                  <Button
                    disabled={isActionPending}
                    icon={<CheckCircle2 aria-hidden="true" size={16} />}
                    onClick={() => verifyMutation.mutate(selectedReport.id)}
                    type="button"
                    variant="primary"
                  >
                    验证通过
                  </Button>
                  {reportStatusKey(selectedReport) !== "rejected" ? (
                    <Button
                      disabled={isActionPending}
                      icon={<XCircle aria-hidden="true" size={16} />}
                      onClick={() => rejectMutation.mutate(selectedReport.id)}
                      type="button"
                      variant="secondary"
                    >
                      验证不通过
                    </Button>
                  ) : null}
                </>
              )}
              <Button
                disabled={isActionPending}
                icon={<Trash2 aria-hidden="true" size={16} />}
                onClick={confirmDelete}
                type="button"
                variant="danger"
              >
                删除报告
              </Button>
            </div>
            {isEditing ? (
              <form className="report-edit-form" onSubmit={saveReport}>
                <label className="field-label compact">
                  <span>报告标题</span>
                  <Input
                    aria-label="报告标题"
                    onChange={(event) => setEditTitle(event.target.value)}
                    value={editTitle}
                  />
                </label>
                <label className="field-label compact">
                  <span>报告内容</span>
                  <Textarea
                    aria-label="报告内容"
                    onChange={(event) => setEditBody(event.target.value)}
                    value={editBody}
                  />
                </label>
                <div className="report-edit-actions">
                  <Button
                    disabled={isActionPending || !editTitle.trim()}
                    type="submit"
                    variant="primary"
                  >
                    保存报告
                  </Button>
                  <Button
                    disabled={isActionPending}
                    onClick={() => setIsEditing(false)}
                    type="button"
                    variant="secondary"
                  >
                    取消
                  </Button>
                </div>
              </form>
            ) : (
              <article className="report-preview">
                <div className="report-preview-title">
                  {selectedReport.title}
                </div>
                <MarkdownRenderer content={selectedReport.body_markdown} />
              </article>
            )}
          </>
        ) : (
          <div className="empty-block wide">
            <p>选择左侧报告后查看详情。</p>
          </div>
        )}
      </section>
    </div>
  );
}

const BASE_STATUS_FILTERS = [
  { id: "all", label: "全部" },
  { id: "draft", label: "草稿" },
  { id: "verified", label: "已验证" },
  { id: "rejected", label: "未通过" },
];

const REPORT_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  rejected: "未通过",
  stale: "已过期",
  superseded: "已替代",
  verified: "已验证",
};

function reportStatusFilters(reports: ReportRead[]) {
  const knownIds = new Set(BASE_STATUS_FILTERS.map((filter) => filter.id));
  const dynamicStatuses = reports
    .map(reportStatusKey)
    .filter((status) => !knownIds.has(status))
    .filter((status, index, statuses) => statuses.indexOf(status) === index);

  return [...BASE_STATUS_FILTERS, ...dynamicStatuses.map((status) => ({
    id: status,
    label: REPORT_STATUS_LABELS[status] ?? status,
  }))].map((filter) => ({
    ...filter,
    count:
      filter.id === "all"
        ? reports.length
        : reports.filter((report) => reportStatusKey(report) === filter.id)
            .length,
  }));
}

function reportStatusKey(report: ReportRead) {
  if (report.verified || report.status === "verified") {
    return "verified";
  }
  return report.status || "draft";
}

function reportStatusLabel(report: ReportRead) {
  return REPORT_STATUS_LABELS[reportStatusKey(report)] ?? report.status;
}
