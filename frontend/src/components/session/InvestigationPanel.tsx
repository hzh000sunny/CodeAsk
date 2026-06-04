import { Cpu, FileText, MessageSquareText, Pencil, Trash2 } from "lucide-react";

import { ActionTracePanel } from "./action-trace/ActionTracePanel";
import type { ActionTraceEvent } from "./action-trace/action-trace-model";
import type { RuntimeSessionState } from "./session-model";
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
  runtimeState: RuntimeSessionState | null;
}

export function InvestigationPanel({
  attachments,
  insights,
  isLoadingAttachments,
  isStreaming,
  onDescribeAttachment,
  onDeleteAttachment,
  onRenameAttachment,
  runtimeState,
}: InvestigationPanelProps) {
  const visibleRuntimeState = runtimeState ?? {
    modelName: "等待模型选择",
    usageLabel: "0k / 200k",
    usageRatio: 0,
  };
  const usagePercent = Math.round(
    Math.max(0, Math.min(1, visibleRuntimeState.usageRatio)) * 100,
  );

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
          <div className="attachment-empty">
            <span aria-hidden="true" className="attachment-empty-icon">
              <FileText size={15} />
            </span>
            <p className="attachment-empty-title">正在加载会话数据…</p>
          </div>
        ) : null}
        {!isLoadingAttachments && attachments.length === 0 ? (
          <div className="attachment-empty">
            <span aria-hidden="true" className="attachment-empty-icon">
              <FileText size={15} />
            </span>
            <p className="attachment-empty-title">暂无上传数据</p>
            <p className="attachment-empty-hint">
              上传的文件会显示在这里，供模型在调查时取用。
            </p>
          </div>
        ) : null}
        {attachments.length > 0 ? (
          <ul className="attachment-list attachment-scroll">
            {attachments.map((attachment) => (
              <li key={attachment.id}>
                <span aria-hidden="true" className="attachment-icon">
                  <FileText size={15} />
                </span>
                <div className="attachment-summary">
                  <strong>{attachment.display_name}</strong>
                  <span className="attachment-meta">
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
                <div className="attachment-actions">
                  {/* 晋级为 Wiki 暂时隐藏（功能未启用）；API 与上层 prop 保留。 */}
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
      <section
        className="runtime-section"
        role="region"
        aria-label="会话运行状态"
      >
        <div className="panel-subheading">
          <Cpu aria-hidden="true" size={16} />
          <h3>模型状态</h3>
        </div>
        <div className="session-runtime-status">
          <div className="session-runtime-row">
            <span className="session-runtime-label">当前模型</span>
            <strong className="session-runtime-value">
              {visibleRuntimeState.modelName}
            </strong>
          </div>
          <div className="session-runtime-row">
            <span className="session-runtime-label">上下文</span>
            <div className="session-runtime-progress-wrap">
              <div
                aria-label="上下文使用进度"
                aria-valuemax={100}
                aria-valuemin={0}
                aria-valuenow={usagePercent}
                className="session-runtime-progress"
                role="progressbar"
              >
                <span
                  className="session-runtime-progress-bar"
                  style={{ width: `${usagePercent}%` }}
                />
              </div>
              <span className="session-runtime-usage">
                {visibleRuntimeState.usageLabel}
              </span>
            </div>
          </div>
        </div>
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
