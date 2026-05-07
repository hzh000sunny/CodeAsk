import {
  ArrowUpRight,
  FileText,
  MessageSquareText,
  Pencil,
  Trash2,
} from "lucide-react";

import { ActionTracePanel } from "./action-trace/ActionTracePanel";
import type { ActionTraceEvent } from "./action-trace/action-trace-model";
import type { AttachmentResponse } from "../../types/api";
import { Button } from "../ui/button";

interface InvestigationPanelProps {
  attachments: AttachmentResponse[];
  insights: ActionTraceEvent[];
  isLoadingAttachments: boolean;
  isStreaming: boolean;
  onDescribeAttachment: (attachment: AttachmentResponse) => void;
  onDeleteAttachment: (attachment: AttachmentResponse) => void;
  onPromoteAttachment: (attachment: AttachmentResponse) => void;
  onRenameAttachment: (attachment: AttachmentResponse) => void;
}

export function InvestigationPanel({
  attachments,
  insights,
  isLoadingAttachments,
  isStreaming,
  onDescribeAttachment,
  onDeleteAttachment,
  onPromoteAttachment,
  onRenameAttachment,
}: InvestigationPanelProps) {
  return (
    <aside className="progress-panel" role="region" aria-label="Agent 行动轨迹">
      <ActionTracePanel events={insights} isStreaming={isStreaming} />
      <section
        className="attachment-section"
        role="region"
        aria-label="会话数据"
      >
        <div className="panel-subheading">
          <FileText aria-hidden="true" size={16} />
          <h3>会话数据</h3>
        </div>
        {isLoadingAttachments ? (
          <p className="empty-note">正在加载会话数据</p>
        ) : null}
        {!isLoadingAttachments && attachments.length === 0 ? (
          <p className="empty-note">暂无上传数据</p>
        ) : null}
        {attachments.length > 0 ? (
          <ul className="attachment-list attachment-scroll">
            {attachments.map((attachment) => (
              <li key={attachment.id}>
                <div className="attachment-summary">
                  <strong>{attachment.display_name}</strong>
                  <span>
                    {attachment.kind} ·{" "}
                    {formatAttachmentSize(attachment.size_bytes)} ·{" "}
                    {shortAttachmentId(attachment.id)}
                  </span>
                  {attachment.original_filename &&
                  attachment.original_filename !== attachment.display_name ? (
                    <span>原名 {attachment.original_filename}</span>
                  ) : null}
                  {attachment.description ? (
                    <span className="attachment-description">
                      {attachment.description}
                    </span>
                  ) : null}
                </div>
                <div className="row-actions">
                  <Button
                    aria-label={`晋级为 Wiki ${attachment.display_name}`}
                    className="icon-only"
                    icon={<ArrowUpRight size={15} />}
                    onClick={() => onPromoteAttachment(attachment)}
                    title={`晋级为 Wiki ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                  <Button
                    aria-label={`编辑用途说明 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<MessageSquareText size={15} />}
                    onClick={() => onDescribeAttachment(attachment)}
                    title={`编辑用途说明 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                  <Button
                    aria-label={`重命名 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<Pencil size={15} />}
                    onClick={() => onRenameAttachment(attachment)}
                    title={`重命名 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                  <Button
                    aria-label={`删除 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<Trash2 size={15} />}
                    onClick={() => onDeleteAttachment(attachment)}
                    title={`删除 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </aside>
  );
}

function shortAttachmentId(id: string) {
  return id.length <= 8 ? id : id.slice(-8);
}

function formatAttachmentSize(sizeBytes: number | null | undefined) {
  if (typeof sizeBytes !== "number") {
    return "未知大小";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}
