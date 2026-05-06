import type {
  FeatureRead,
  AttachmentResponse,
  ReportRead,
  SessionResponse,
} from "../../types/api";
import type { WikiPromotionRead, WikiPromotionTargetKind } from "../../types/wiki";
import {
  SessionAttachmentPromotionDialog,
  SessionAttachmentPromotionSuccessDialog,
} from "./SessionAttachmentPromotionDialog";
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
  isPromotingAttachment: boolean;
  onBulkDeleteCancel: () => void;
  onBulkDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  onDeleteConfirm: () => void;
  onPromotionCancel: () => void;
  onPromotionConfirm: () => void;
  onPromotionDocumentNameChange: (value: string) => void;
  onPromotionFeatureChange: (featureId: string) => void;
  onPromotionOpenWiki: () => void;
  onPromotionParentChange: (parentId: string) => void;
  onOpenGeneratedReport: () => void;
  onReportCancel: () => void;
  onReportClose: () => void;
  onReportConfirm: () => void;
  onReportFeatureChange: (featureId: string) => void;
  onReportTitleChange: (title: string) => void;
  promotionAttachment: AttachmentResponse | null;
  promotionCanSubmit: boolean;
  promotionDocumentName: string;
  promotionError: string;
  promotionFeatureId: string;
  promotionFolderOptions: Array<{ label: string; value: string }>;
  promotionParentId: string;
  promotionResult: WikiPromotionRead | null;
  promotionTargetKind: WikiPromotionTargetKind | null;
  promotionTreeLoading: boolean;
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
  isPromotingAttachment,
  onBulkDeleteCancel,
  onBulkDeleteConfirm,
  onDeleteCancel,
  onDeleteConfirm,
  onPromotionCancel,
  onPromotionConfirm,
  onPromotionDocumentNameChange,
  onPromotionFeatureChange,
  onPromotionOpenWiki,
  onPromotionParentChange,
  onOpenGeneratedReport,
  onReportCancel,
  onReportClose,
  onReportConfirm,
  onReportFeatureChange,
  onReportTitleChange,
  promotionAttachment,
  promotionCanSubmit,
  promotionDocumentName,
  promotionError,
  promotionFeatureId,
  promotionFolderOptions,
  promotionParentId,
  promotionResult,
  promotionTargetKind,
  promotionTreeLoading,
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
      {promotionAttachment && promotionTargetKind && !promotionResult ? (
        <SessionAttachmentPromotionDialog
          attachmentName={promotionAttachment.display_name}
          canSubmit={promotionCanSubmit}
          documentName={promotionDocumentName}
          errorMessage={promotionError}
          featureId={promotionFeatureId}
          features={features}
          folderOptions={promotionFolderOptions}
          onCancel={onPromotionCancel}
          onConfirm={onPromotionConfirm}
          onDocumentNameChange={onPromotionDocumentNameChange}
          onFeatureChange={onPromotionFeatureChange}
          onParentChange={onPromotionParentChange}
          parentId={promotionParentId}
          pending={isPromotingAttachment}
          targetKind={promotionTargetKind}
          treeLoading={promotionTreeLoading}
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
      {promotionResult && promotionTargetKind ? (
        <SessionAttachmentPromotionSuccessDialog
          nodeName={promotionResult.node.name}
          onClose={onPromotionCancel}
          onOpenWiki={onPromotionOpenWiki}
          targetKind={promotionTargetKind}
        />
      ) : null}
    </>
  );
}
