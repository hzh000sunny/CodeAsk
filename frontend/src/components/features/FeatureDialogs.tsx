import { AlertTriangle } from "lucide-react";

import { useForwardErrorToAppFeedback } from "../feedback/useForwardErrorToAppFeedback";
import { Button } from "../ui/button";

export function DeleteFeatureDialog({
  errorMessage,
  featureName,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  errorMessage: string;
  featureName: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useForwardErrorToAppFeedback(errorMessage, { title: "删除特性失败" });

  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="delete-feature-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="delete-feature-title">删除特性</h2>
          <p>
            确认删除“{featureName}
            ”？删除后该特性的设置、关联关系和知识资料将不再从特性列表进入。
          </p>
          <div className="dialog-actions">
            <Button
              disabled={isDeleting}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={isDeleting}
              onClick={onConfirm}
              type="button"
              variant="danger"
            >
              {isDeleting ? "删除中" : "确认删除"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
