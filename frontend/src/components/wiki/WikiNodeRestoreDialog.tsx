import { RotateCcw } from "lucide-react";

import { Button } from "../ui/button";

export function WikiNodeRestoreDialog({
  isRestoring,
  nodeName,
  onClose,
  onRestore,
  path,
}: {
  isRestoring: boolean;
  nodeName: string;
  onClose: () => void;
  onRestore: () => void;
  path: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-restore-node-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon success">
          <RotateCcw aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-restore-node-title">Wiki 节点已删除，可恢复</h2>
          <p>“{nodeName}” 已进入软删除状态。你可以立即恢复，原有路径和子树会一并尝试恢复。</p>
          <div className="wiki-node-dialog-note">
            <strong>原路径</strong>
            <span>{path}</span>
          </div>
          <div className="dialog-actions">
            <Button disabled={isRestoring} onClick={onClose} type="button" variant="secondary">
              关闭
            </Button>
            <Button
              disabled={isRestoring}
              onClick={onRestore}
              type="button"
              variant="primary"
            >
              {isRestoring ? "恢复中" : "恢复节点"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
