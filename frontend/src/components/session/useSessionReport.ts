import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { generateSessionReport } from "../../lib/api";
import type { FeatureRead, ReportRead, SessionResponse } from "../../types/api";
import { messageFromError } from "./session-model";

export function useSessionReport({
  detectedFeatureIds,
  features,
  hasCompletedQuestionAnswer,
  isStreaming,
  selected,
  showActionNotice,
}: {
  detectedFeatureIds: number[];
  features: FeatureRead[];
  hasCompletedQuestionAnswer: boolean;
  isStreaming: boolean;
  selected: SessionResponse | null;
  showActionNotice: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [reportDialog, setReportDialog] = useState<
    "not-ready" | "confirm" | "success" | null
  >(null);
  const [reportFeatureId, setReportFeatureId] = useState("");
  const [reportTitle, setReportTitle] = useState("");
  const [reportError, setReportError] = useState("");
  const [generatedReport, setGeneratedReport] = useState<ReportRead | null>(
    null,
  );

  const reportMutation = useMutation({
    mutationFn: ({
      session,
      featureId,
      title,
    }: {
      session: SessionResponse;
      featureId: number;
      title: string;
    }) =>
      generateSessionReport(session.id, {
        feature_id: featureId,
        title,
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
      setReportError(`生成报告失败：${messageFromError(error)}`);
    },
  });

  function openReportDialog() {
    if (!selected) {
      showActionNotice("请先创建会话后再生成报告");
      return;
    }
    if (!hasCompletedQuestionAnswer || isStreaming) {
      setReportDialog("not-ready");
      setReportError("");
      return;
    }
    const inferredFeatureId = detectedFeatureIds.find((id) =>
      features.some((feature) => feature.id === id),
    );
    const defaultFeatureId = inferredFeatureId ?? features[0]?.id;
    setReportFeatureId(defaultFeatureId ? String(defaultFeatureId) : "");
    setReportTitle(`${selected.title}定位报告`);
    setReportError("");
    setGeneratedReport(null);
    setReportDialog("confirm");
  }

  function submitReport() {
    if (!selected || !reportFeatureId) {
      return;
    }
    reportMutation.mutate({
      session: selected,
      featureId: Number(reportFeatureId),
      title: reportTitle.trim() || `${selected.title}定位报告`,
    });
  }

  return {
    generatedReport,
    openReportDialog,
    reportDialog,
    reportError,
    reportFeatureId,
    reportMutation,
    reportTitle,
    setReportDialog,
    setReportFeatureId,
    setReportTitle,
    submitReport,
  };
}
