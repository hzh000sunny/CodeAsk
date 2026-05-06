import { useEffect, useState } from "react";
import { AlertTriangle, FilePenLine, FolderPlus, Save } from "lucide-react";

import { Button } from "../ui/button";
import { Input } from "../ui/input";

export function WikiNodeInputDialog({
  confirmLabel,
  errorMessage,
  isSubmitting,
  modeLabel,
  onCancel,
  onSubmit,
  parentPath,
  title,
  initialValue = "",
}: {
  confirmLabel: string;
  errorMessage: string;
  isSubmitting: boolean;
  modeLabel: "folder" | "document" | "rename";
  onCancel: () => void;
  onSubmit: (value: string) => void;
  parentPath: string | null;
  title: string;
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const nameLabel =
    modeLabel === "folder" ? "目录名称" : modeLabel === "document" ? "Wiki 标题" : "新名称";

  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-node-dialog-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          {modeLabel === "folder" ? (
            <FolderPlus aria-hidden="true" size={18} />
          ) : (
            <FilePenLine aria-hidden="true" size={18} />
          )}
        </div>
        <div className="dialog-content">
          <h2 id="wiki-node-dialog-title">{title}</h2>
          <div className="wiki-node-dialog-form">
            {parentPath ? (
              <div className="wiki-node-dialog-note">
                <strong>所在位置</strong>
                <span>{parentPath}</span>
              </div>
            ) : null}
            <label className="field-label compact">
              {nameLabel}
              <Input
                autoFocus
                onChange={(event) => setValue(event.target.value)}
                placeholder={modeLabel === "folder" ? "例如：运行手册" : "例如：支付接入说明"}
                value={value}
              />
            </label>
          </div>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button disabled={isSubmitting} onClick={onCancel} type="button" variant="secondary">
              取消
            </Button>
            <Button
              disabled={!value.trim() || isSubmitting}
              icon={<Save size={15} />}
              onClick={() => onSubmit(value)}
              type="button"
              variant="primary"
            >
              {isSubmitting ? "保存中" : confirmLabel}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function WikiNodeDeleteDialog({
  clearOnly = false,
  errorMessage,
  isDeleting,
  nodeName,
  onCancel,
  onConfirm,
  path,
}: {
  clearOnly?: boolean;
  errorMessage: string;
  isDeleting: boolean;
  nodeName: string;
  onCancel: () => void;
  onConfirm: () => void;
  path: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-delete-node-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-delete-node-title">{clearOnly ? "清空目录内容" : "删除 Wiki 节点"}</h2>
          <p>
            {clearOnly
              ? `确认清空“${nodeName}”下的数据？目录本身会保留，目录下的文档、静态资源或问题报告会被删除。`
              : `确认删除“${nodeName}”？其下游子节点会一起进入软删除状态。`}
          </p>
          <div className="wiki-node-dialog-note">
            <strong>当前路径</strong>
            <span>{path}</span>
          </div>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button disabled={isDeleting} onClick={onCancel} type="button" variant="secondary">
              取消
            </Button>
            <Button
              disabled={isDeleting}
              onClick={onConfirm}
              type="button"
              variant="danger"
            >
              {isDeleting ? (clearOnly ? "清空中" : "删除中") : clearOnly ? "确认清空" : "确认删除"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function WikiEditLeaveDialog({
  isPublishing,
  onCancel,
  onDiscard,
  onLeaveWithDraft,
  onPublish,
}: {
  isPublishing: boolean;
  onCancel: () => void;
  onDiscard: () => void;
  onLeaveWithDraft: () => void;
  onPublish: () => void;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-edit-leave-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog wiki-leave-dialog"
        role="dialog"
      >
        <div className="dialog-icon warning">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-edit-leave-title">离开编辑态</h2>
          <p>当前内容还没有保存。你可以保留自动草稿返回阅读态，也可以丢弃草稿或直接保存。</p>
          <div className="dialog-actions wiki-dialog-actions-stack">
            <Button disabled={isPublishing} onClick={onCancel} type="button" variant="secondary">
              继续编辑
            </Button>
            <Button
              disabled={isPublishing}
              onClick={onLeaveWithDraft}
              type="button"
              variant="secondary"
            >
              保留草稿并离开
            </Button>
            <Button
              disabled={isPublishing}
              onClick={onDiscard}
              type="button"
              variant="danger"
            >
              丢弃草稿
            </Button>
            <Button
              disabled={isPublishing}
              onClick={onPublish}
              type="button"
              variant="primary"
            >
              {isPublishing ? "保存中" : "保存并离开"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function WikiMessageDialog({
  message,
  onClose,
  title = "操作失败",
}: {
  message: string;
  onClose: () => void;
  title?: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-message-dialog-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-message-dialog-title">{title}</h2>
          <p>{message}</p>
          <div className="dialog-actions">
            <Button onClick={onClose} type="button" variant="primary">
              知道了
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
