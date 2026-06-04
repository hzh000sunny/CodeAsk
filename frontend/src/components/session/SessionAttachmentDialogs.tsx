import {
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { AlertTriangle, MessageSquareText, Pencil } from "lucide-react";

import type { AttachmentResponse } from "../../types/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

export type AttachmentDialog =
  | { mode: "rename"; attachment: AttachmentResponse }
  | { mode: "describe"; attachment: AttachmentResponse }
  | { mode: "delete"; attachment: AttachmentResponse };

interface SessionAttachmentDialogsProps {
  dialog: AttachmentDialog | null;
  pending: boolean;
  onClose: () => void;
  onSubmitRename: (displayName: string) => void;
  onSubmitDescribe: (description: string) => void;
  onSubmitDelete: () => void;
}

export function SessionAttachmentDialogs({
  dialog,
  pending,
  onClose,
  onSubmitRename,
  onSubmitDescribe,
  onSubmitDelete,
}: SessionAttachmentDialogsProps) {
  if (!dialog) {
    return null;
  }
  if (dialog.mode === "rename") {
    return (
      <RenameAttachmentDialog
        attachment={dialog.attachment}
        onClose={onClose}
        onSubmit={onSubmitRename}
        pending={pending}
      />
    );
  }
  if (dialog.mode === "describe") {
    return (
      <DescribeAttachmentDialog
        attachment={dialog.attachment}
        onClose={onClose}
        onSubmit={onSubmitDescribe}
        pending={pending}
      />
    );
  }
  return (
    <DeleteAttachmentDialog
      attachment={dialog.attachment}
      onClose={onClose}
      onConfirm={onSubmitDelete}
      pending={pending}
    />
  );
}

function backdropKeyHandler(onClose: () => void, pending: boolean) {
  return (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && !pending) {
      onClose();
    }
  };
}

function RenameAttachmentDialog({
  attachment,
  onClose,
  onSubmit,
  pending,
}: {
  attachment: AttachmentResponse;
  onClose: () => void;
  onSubmit: (displayName: string) => void;
  pending: boolean;
}) {
  const [value, setValue] = useState(attachment.display_name);
  const trimmed = value.trim();
  const canSubmit = Boolean(trimmed) && !pending;

  function submit() {
    if (canSubmit) {
      onSubmit(value);
    }
  }

  return (
    <div className="dialog-backdrop" onKeyDown={backdropKeyHandler(onClose, pending)}>
      <section
        aria-labelledby="attachment-rename-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <Pencil aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="attachment-rename-title">重命名会话数据</h2>
          <p>为这份数据起一个便于识别的名称，不会改动文件内容。</p>
          <label className="field-label compact">
            名称
            <Input
              aria-label="会话数据名称"
              autoFocus
              onChange={(event) => setValue(event.target.value)}
              onFocus={(event) => event.currentTarget.select()}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submit();
                }
              }}
              value={value}
            />
          </label>
          <div className="dialog-actions">
            <Button disabled={pending} onClick={onClose} type="button" variant="secondary">
              取消
            </Button>
            <Button disabled={!canSubmit} onClick={submit} type="button" variant="primary">
              {pending ? "保存中" : "保存"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function DescribeAttachmentDialog({
  attachment,
  onClose,
  onSubmit,
  pending,
}: {
  attachment: AttachmentResponse;
  onClose: () => void;
  onSubmit: (description: string) => void;
  pending: boolean;
}) {
  const [value, setValue] = useState(attachment.description ?? "");

  return (
    <div className="dialog-backdrop" onKeyDown={backdropKeyHandler(onClose, pending)}>
      <section
        aria-labelledby="attachment-describe-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <MessageSquareText aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="attachment-describe-title">编辑用途说明</h2>
          <p>说明这份数据是什么、模型可以怎么用，留空则清除说明。</p>
          <label className="field-label compact">
            用途说明
            <Textarea
              aria-label="会话数据用途说明"
              autoFocus
              onChange={(event) => setValue(event.target.value)}
              placeholder="例如：复现崩溃时的完整服务端日志"
              value={value}
            />
          </label>
          <div className="dialog-actions">
            <Button disabled={pending} onClick={onClose} type="button" variant="secondary">
              取消
            </Button>
            <Button
              disabled={pending}
              onClick={() => onSubmit(value)}
              type="button"
              variant="primary"
            >
              {pending ? "保存中" : "保存"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function DeleteAttachmentDialog({
  attachment,
  onClose,
  onConfirm,
  pending,
}: {
  attachment: AttachmentResponse;
  onClose: () => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  return (
    <div className="dialog-backdrop" onKeyDown={backdropKeyHandler(onClose, pending)}>
      <section
        aria-labelledby="attachment-delete-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="attachment-delete-title">删除会话数据</h2>
          <p>确认删除“{attachment.display_name}”？文件会从会话工作目录移除，且不可恢复。</p>
          <div className="dialog-actions">
            <Button disabled={pending} onClick={onClose} type="button" variant="secondary">
              取消
            </Button>
            <Button disabled={pending} onClick={onConfirm} type="button" variant="danger">
              {pending ? "删除中" : "确认删除"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
