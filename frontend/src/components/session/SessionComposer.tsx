import type { RefObject } from "react";
import { FileText, FileUp, SendHorizontal } from "lucide-react";

import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";

export function SessionComposer({
  createPending,
  draft,
  fileInputRef,
  forceCodeInvestigation,
  isStreaming,
  onDraftChange,
  onForceCodeInvestigationChange,
  onOpenReportDialog,
  onSendMessage,
  onUploadFile,
  reportPending,
  selected,
  uploadStatus,
}: {
  createPending: boolean;
  draft: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  forceCodeInvestigation: boolean;
  isStreaming: boolean;
  onDraftChange: (value: string) => void;
  onForceCodeInvestigationChange: (checked: boolean) => void;
  onOpenReportDialog: () => void;
  onSendMessage: () => void;
  onUploadFile: (file: File | undefined) => void;
  reportPending: boolean;
  selected: boolean;
  uploadStatus: string;
}) {
  return (
    <div className="composer" role="region" aria-label="会话输入操作区">
      <Textarea
        aria-label="会话输入"
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="描述你遇到的问题，或粘贴关键日志片段"
        value={draft}
      />
      <div className="composer-actions">
        <input
          accept=".log,.txt,.md"
          className="visually-hidden"
          onChange={(event) => onUploadFile(event.target.files?.[0])}
          ref={fileInputRef}
          type="file"
        />
        <Button
          disabled={createPending}
          icon={<FileUp size={16} />}
          onClick={() => fileInputRef.current?.click()}
          type="button"
          variant="quiet"
        >
          上传日志
        </Button>
        {uploadStatus ? (
          <span className="upload-status">{uploadStatus}</span>
        ) : null}
        <label className="checkbox-row">
          <input
            checked={forceCodeInvestigation}
            onChange={(event) =>
              onForceCodeInvestigationChange(event.target.checked)
            }
            type="checkbox"
          />
          <span>强制代码调查</span>
        </label>
        <Button
          disabled={!selected || reportPending}
          icon={<FileText size={16} />}
          onClick={onOpenReportDialog}
          type="button"
          variant="secondary"
        >
          生成报告
        </Button>
        <Button
          disabled={!draft.trim() || isStreaming}
          icon={<SendHorizontal size={16} />}
          onClick={onSendMessage}
          type="button"
          variant="primary"
        >
          {isStreaming ? "发送中" : "发送"}
        </Button>
      </div>
    </div>
  );
}
