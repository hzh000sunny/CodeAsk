import {
  Activity,
  CheckCircle2,
  Clock3,
  FileText,
  LoaderCircle,
  MessageSquareText,
  Pencil,
  Trash2,
  XCircle
} from "lucide-react";

import type { RuntimeInsight, RuntimeStage } from "./session-model";
import type { AttachmentResponse } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

interface InvestigationPanelProps {
  attachments: AttachmentResponse[];
  insights: RuntimeInsight[];
  isLoadingAttachments: boolean;
  stages: RuntimeStage[];
  isStreaming: boolean;
  onDescribeAttachment: (attachment: AttachmentResponse) => void;
  onDeleteAttachment: (attachment: AttachmentResponse) => void;
  onRenameAttachment: (attachment: AttachmentResponse) => void;
}

export function InvestigationPanel({
  attachments,
  insights,
  isLoadingAttachments,
  isStreaming,
  onDescribeAttachment,
  onDeleteAttachment,
  onRenameAttachment,
  stages
}: InvestigationPanelProps) {
  return (
    <aside className="progress-panel" role="region" aria-label="调查进度">
      <div className="panel-heading">
        <h2>调查进度</h2>
        <Badge>{isStreaming ? "运行中" : "Agent Runtime"}</Badge>
      </div>
      <ol className="stage-list">
        {stages.map((stage) => (
          <StageItem key={stage.key} stage={stage} />
        ))}
      </ol>
      <section className="insight-section" aria-label="运行事件">
        <div className="panel-subheading">
          <Activity aria-hidden="true" size={16} />
          <h3>运行事件</h3>
        </div>
        {insights.length === 0 ? (
          <p className="empty-note">暂无运行事件</p>
        ) : (
          <ul className="insight-list">
            {insights.map((insight) => (
              <li data-kind={insight.kind} key={insight.id}>
                <strong>{insight.title}</strong>
                <span>{insight.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="attachment-section" role="region" aria-label="会话数据">
        <div className="panel-subheading">
          <FileText aria-hidden="true" size={16} />
          <h3>会话数据</h3>
        </div>
        {isLoadingAttachments ? <p className="empty-note">正在加载会话数据</p> : null}
        {!isLoadingAttachments && attachments.length === 0 ? (
          <p className="empty-note">暂无上传数据</p>
        ) : null}
        {attachments.length > 0 ? (
          <ul className="attachment-list">
            {attachments.map((attachment) => (
              <li key={attachment.id}>
                <div className="attachment-summary">
                  <strong>{attachment.display_name}</strong>
                  <span>
                    {attachment.kind} · {formatAttachmentSize(attachment.size_bytes)} ·{" "}
                    {shortAttachmentId(attachment.id)}
                  </span>
                  {attachment.original_filename &&
                  attachment.original_filename !== attachment.display_name ? (
                    <span>原名 {attachment.original_filename}</span>
                  ) : null}
                  {attachment.description ? (
                    <span className="attachment-description">{attachment.description}</span>
                  ) : null}
                </div>
                <div className="row-actions">
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

function StageItem({ stage }: { stage: RuntimeStage }) {
  const Icon =
    stage.status === "done"
      ? CheckCircle2
      : stage.status === "active"
        ? LoaderCircle
        : stage.status === "error"
          ? XCircle
          : Clock3;

  return (
    <li className="stage-item" data-done={stage.status === "done"} data-status={stage.status}>
      <Icon aria-hidden="true" size={17} />
      <div>
        <strong>{stage.label}</strong>
        <span>{stage.detail}</span>
      </div>
    </li>
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
