import type {
  FeatureRead,
  ReportRead,
  SessionResponse,
} from "../../types/api";
import {
  DeleteSessionDialog,
  ReportConfirmDialog,
  ReportReadinessDialog,
  ReportSuccessDialog,
} from "./SessionDialogs";

type ReportDialogState = "not-ready" | "confirm" | "success" | null;

interface SessionWorkspaceDialogsProps {
  bulkSelectedCount: number;
  confirmBulkDelete: boolean;
  deleteCandidate: SessionResponse | null;
  deleteError: string;
  features: FeatureRead[];
  generatedReport: ReportRead | null;
  isBulkDeleting: boolean;
  isDeleting: boolean;
  isGeneratingReport: boolean;
  onBulkDeleteCancel: () => void;
  onBulkDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  onDeleteConfirm: () => void;
  onOpenGeneratedReport: () => void;
  onReportCancel: () => void;
  onReportClose: () => void;
  onReportConfirm: () => void;
  onReportFeatureChange: (featureId: string) => void;
  onReportTitleChange: (title: string) => void;
  reportDialog: ReportDialogState;
  reportError: string;
  reportFeatureId: string;
  reportTitle: string;
}

export function SessionWorkspaceDialogs({
  bulkSelectedCount,
  confirmBulkDelete,
  deleteCandidate,
  deleteError,
  features,
  generatedReport,
  isBulkDeleting,
  isDeleting,
  isGeneratingReport,
  onBulkDeleteCancel,
  onBulkDeleteConfirm,
  onDeleteCancel,
  onDeleteConfirm,
  onOpenGeneratedReport,
  onReportCancel,
  onReportClose,
  onReportConfirm,
  onReportFeatureChange,
  onReportTitleChange,
  reportDialog,
  reportError,
  reportFeatureId,
  reportTitle,
}: SessionWorkspaceDialogsProps) {
  return (
    <>
      {deleteCandidate ? (
        <DeleteSessionDialog
          errorMessage={deleteError}
          isDeleting={isDeleting}
          onCancel={onDeleteCancel}
          onConfirm={onDeleteConfirm}
          sessionTitle={deleteCandidate.title}
        />
      ) : null}
      {confirmBulkDelete ? (
        <DeleteSessionDialog
          errorMessage={deleteError}
          isDeleting={isBulkDeleting}
          onCancel={onBulkDeleteCancel}
          onConfirm={onBulkDeleteConfirm}
          sessionTitle={`${bulkSelectedCount} 个会话`}
        />
      ) : null}
      {reportDialog === "not-ready" ? (
        <ReportReadinessDialog onClose={onReportClose} />
      ) : null}
      {reportDialog === "confirm" ? (
        <ReportConfirmDialog
          errorMessage={reportError}
          featureId={reportFeatureId}
          features={features}
          isGenerating={isGeneratingReport}
          onCancel={onReportCancel}
          onConfirm={onReportConfirm}
          onFeatureChange={onReportFeatureChange}
          onTitleChange={onReportTitleChange}
          title={reportTitle}
        />
      ) : null}
      {reportDialog === "success" && generatedReport ? (
        <ReportSuccessDialog
          onClose={onReportClose}
          onOpen={onOpenGeneratedReport}
          report={generatedReport}
        />
      ) : null}
    </>
  );
}
