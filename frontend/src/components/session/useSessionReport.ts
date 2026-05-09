import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  generateSessionReport,
  getSessionReportPrepareStatus,
  prepareSessionReport,
} from "../../lib/api";
import type {
  ReportRead,
  SessionReportPrepareStatus,
  SessionReportPrepared,
  SessionResponse,
} from "../../types/api";
import { messageFromError } from "./session-model";

function createRequestId(prefix: string) {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) {
    return `${prefix}_${uuid}`;
  }
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export const REPORT_PREPARE_TIMEOUT_MS = 600_000;

export function reportPreparePollingDelayMs(elapsedMs: number) {
  return elapsedMs < 30_000 ? 2_000 : 5_000;
}

async function waitForPreparedReport(
  sessionId: string,
  requestId: string,
  initialStatus?: SessionReportPrepareStatus,
): Promise<SessionReportPrepared> {
  let status = initialStatus;
  let hasPolledStatusEndpoint = !initialStatus;
  let elapsedMs = 0;
  while (elapsedMs < REPORT_PREPARE_TIMEOUT_MS) {
    if (!status) {
      status = await getSessionReportPrepareStatus(sessionId, requestId);
      hasPolledStatusEndpoint = true;
    }
    if (status.status === "succeeded" && status.draft) {
      return status.draft;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "报告草稿生成失败");
    }
    if (!hasPolledStatusEndpoint) {
      status = undefined;
      continue;
    }
    const delayMs = reportPreparePollingDelayMs(elapsedMs);
    await delay(delayMs);
    elapsedMs += delayMs;
    status = undefined;
  }
  throw new Error("报告草稿仍在生成，请稍后重试");
}

export function useSessionReport({
  hasCompletedQuestionAnswer,
  isStreaming,
  selected,
  showActionNotice,
}: {
  hasCompletedQuestionAnswer: boolean;
  isStreaming: boolean;
  selected: SessionResponse | null;
  showActionNotice: (message: string, tone?: "success" | "error") => void;
}) {
  const queryClient = useQueryClient();
  const [reportDialog, setReportDialog] = useState<
    "not-ready" | "preparing" | "confirm" | "success" | null
  >(null);
  const [reportFeatureId, setReportFeatureId] = useState("");
  const [reportTitle, setReportTitle] = useState("");
  const [reportError, setReportError] = useState("");
  const [preparedReport, setPreparedReport] =
    useState<SessionReportPrepared | null>(null);
  const [generatedReport, setGeneratedReport] = useState<ReportRead | null>(
    null,
  );

  const prepareMutation = useMutation({
    mutationFn: ({
      session,
      featureId,
      requestId,
    }: {
      session: SessionResponse;
      featureId: number | null;
      requestId: string;
    }) =>
      prepareSessionReport(
        session.id,
        {
          feature_id: featureId,
        },
        {
          requestId,
        },
      )
        .then((status) =>
          waitForPreparedReport(session.id, status.request_id || requestId, status),
        )
        .catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 503) {
            return waitForPreparedReport(session.id, requestId);
          }
          throw error;
        }),
    onSuccess: (draft) => {
      setPreparedReport(draft);
      setReportFeatureId(draft.feature_id ? String(draft.feature_id) : "");
      setReportTitle(draft.title);
      setReportError("");
      setGeneratedReport(null);
      setReportDialog("confirm");
    },
    onError: (error) => {
      setReportDialog(null);
      setPreparedReport(null);
      setReportError("");
      showActionNotice(`生成报告失败：${messageFromError(error)}`, "error");
    },
  });

  const saveMutation = useMutation({
    mutationFn: ({
      session,
      featureId,
      title,
      bodyMarkdown,
    }: {
      session: SessionResponse;
      featureId: number | null;
      title: string;
      bodyMarkdown: string;
    }) =>
      generateSessionReport(session.id, {
        feature_id: featureId,
        title,
        body_markdown: bodyMarkdown,
      }),
    onSuccess: (report) => {
      setGeneratedReport(report);
      setReportError("");
      setReportDialog("success");
      if (report.feature_id) {
        void queryClient.invalidateQueries({
          queryKey: ["reports", report.feature_id],
        });
      }
    },
    onError: (error) => {
      setReportError("");
      showActionNotice(`生成报告失败：${messageFromError(error)}`, "error");
    },
  });

  function openReportDialog() {
    if (!selected) {
      showActionNotice("请先创建会话后再生成报告", "error");
      return;
    }
    if (!hasCompletedQuestionAnswer || isStreaming) {
      setReportDialog("not-ready");
      setReportError("");
      return;
    }
    setReportError("");
    setGeneratedReport(null);
    setPreparedReport(null);
    setReportDialog("preparing");
    prepareMutation.mutate({
      session: selected,
      featureId: null,
      requestId: createRequestId("report_prepare"),
    });
  }

  function submitReport() {
    if (!selected || !preparedReport) {
      return;
    }
    saveMutation.mutate({
      session: selected,
      featureId: reportFeatureId ? Number(reportFeatureId) : null,
      title: reportTitle.trim(),
      bodyMarkdown: preparedReport.body_markdown,
    });
  }

  return {
    generatedReport,
    isReportPending: prepareMutation.isPending || saveMutation.isPending,
    openReportDialog,
    preparedReport,
    reportDialog,
    reportError,
    reportFeatureId,
    reportTitle,
    setReportDialog,
    setReportFeatureId,
    setReportTitle,
    submitReport,
  };
}
