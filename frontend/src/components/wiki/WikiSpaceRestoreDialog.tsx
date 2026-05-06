import { History, RotateCcw } from "lucide-react";

import { Button } from "../ui/button";

export function WikiSpaceRestoreDialog({
  featureName,
  isRestoring,
  onCancel,
  onConfirm,
}: {
  featureName: string;
  isRestoring: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-restore-space-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <History aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-restore-space-title">恢复历史特性</h2>
          <p>确认将“{featureName}”从历史特性恢复到当前特性？恢复后它会重新参与当前 Wiki 目录浏览和维护。</p>
          <div className="dialog-actions">
            <Button disabled={isRestoring} onClick={onCancel} type="button" variant="secondary">
              取消
            </Button>
            <Button
              disabled={isRestoring}
              icon={<RotateCcw size={15} />}
              onClick={onConfirm}
              type="button"
              variant="primary"
            >
              {isRestoring ? "恢复中" : "确认恢复"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
