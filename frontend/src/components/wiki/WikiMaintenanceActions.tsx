import { RefreshCw } from "lucide-react";

import { Button } from "../ui/button";

export function WikiMaintenanceActions({
  isRunning,
  nodeName,
  onCancel,
  onConfirm,
  path,
}: {
  isRunning: boolean;
  nodeName: string;
  onCancel: () => void;
  onConfirm: () => void;
  path: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="wiki-reindex-title"
        aria-modal="true"
        className="confirm-dialog wiki-node-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <RefreshCw aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="wiki-reindex-title">重新索引</h2>
          <p>确认重新索引“{nodeName}”下的文档吗？这会刷新当前目录的索引状态、引用解析和搜索可见性。</p>
          <div className="wiki-node-dialog-note">
            <strong>当前路径</strong>
            <span>{path}</span>
          </div>
          <div className="dialog-actions">
            <Button disabled={isRunning} onClick={onCancel} type="button" variant="secondary">
              取消
            </Button>
            <Button
              disabled={isRunning}
              icon={<RefreshCw size={15} />}
              onClick={onConfirm}
              type="button"
              variant="primary"
            >
              {isRunning ? "处理中" : "确认重新索引"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
