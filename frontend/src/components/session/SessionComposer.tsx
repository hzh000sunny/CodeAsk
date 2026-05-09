import { useState, type KeyboardEvent, type RefObject } from "react";
import { FileText, FileUp, SendHorizontal, Square } from "lucide-react";

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
  onCancelMessage,
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
  onCancelMessage: () => void;
  onOpenReportDialog: () => void;
  onSendMessage: () => void;
  onUploadFile: (file: File | undefined) => void;
  reportPending: boolean;
  selected: boolean;
  uploadStatus: string;
}) {
  const [isComposing, setIsComposing] = useState(false);

  function insertNewline(event: KeyboardEvent<HTMLTextAreaElement>) {
    const target = event.currentTarget;
    const start = target.selectionStart ?? draft.length;
    const end = target.selectionEnd ?? draft.length;
    const nextDraft = `${draft.slice(0, start)}\n${draft.slice(end)}`;
    onDraftChange(nextDraft);
    window.requestAnimationFrame(() => {
      target.setSelectionRange(start + 1, start + 1);
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter") {
      return;
    }
    if (isComposing || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    if (event.shiftKey || event.ctrlKey) {
      insertNewline(event);
      return;
    }
    if (draft.trim() && !isStreaming) {
      onSendMessage();
    }
  }

  return (
    <div className="composer" role="region" aria-label="会话输入操作区">
      <Textarea
        aria-label="会话输入"
        onCompositionEnd={() => setIsComposing(false)}
        onCompositionStart={() => setIsComposing(true)}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={handleKeyDown}
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
          {reportPending ? "准备中" : "生成报告"}
        </Button>
        <Button
          disabled={!isStreaming && !draft.trim()}
          icon={isStreaming ? <Square size={15} /> : <SendHorizontal size={16} />}
          onClick={isStreaming ? onCancelMessage : onSendMessage}
          type="button"
          variant={isStreaming ? "secondary" : "primary"}
        >
          {isStreaming ? "停止" : "发送"}
        </Button>
      </div>
    </div>
  );
}
