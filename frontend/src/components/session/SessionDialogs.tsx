import { AlertTriangle, CheckCircle2, FileText, LoaderCircle } from "lucide-react";

import type { FeatureRead, ReportRead } from "../../types/api";
import { useForwardErrorToAppFeedback } from "../feedback/useForwardErrorToAppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export function ReportReadinessDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-readiness-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon warning">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-readiness-title">暂不能生成报告</h2>
          <p>至少完成一次问答，并得到可汇总的回答后，才能生成问题定位报告。</p>
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

export function ReportPreparingDialog() {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-preparing-title"
        aria-modal="true"
        className="confirm-dialog report-progress-dialog"
        role="dialog"
      >
        <div className="dialog-icon info spinning">
          <LoaderCircle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-preparing-title">正在准备报告</h2>
          <p>正在汇总当前会话的问答、证据和建议特性，请稍候。</p>
        </div>
      </section>
    </div>
  );
}

export function ReportConfirmDialog({
  errorMessage,
  existingReportId,
  featureId,
  features,
  isGenerating,
  onCancel,
  onConfirm,
  onFeatureChange,
  onTitleChange,
  title,
}: {
  errorMessage: string;
  existingReportId: number | null;
  featureId: string;
  features: FeatureRead[];
  isGenerating: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onFeatureChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  title: string;
}) {
  useForwardErrorToAppFeedback(errorMessage, { title: "生成报告失败" });

  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-confirm-title"
        aria-modal="true"
        className="confirm-dialog report-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <FileText aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-confirm-title">生成问题定位报告</h2>
          <p>
            {existingReportId
              ? "当前会话已经生成过报告，本次保存会覆盖更新原报告。"
              : "报告会沉淀到绑定特性的“问题报告”中，生成后可以直接跳转查看。"}
          </p>
          <label className="field-label compact">
            绑定特性
            <select
              className="input"
              onChange={(event) => onFeatureChange(event.target.value)}
              value={featureId}
            >
              <option value="">请选择特性</option>
              {features.map((feature) => (
                <option key={feature.id} value={feature.id}>
                  {feature.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label compact">
            报告标题
            <Input
              onChange={(event) => onTitleChange(event.target.value)}
              value={title}
            />
          </label>
          <div className="dialog-actions">
            <Button
              disabled={isGenerating}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={!featureId || !title.trim() || isGenerating}
              onClick={onConfirm}
              type="button"
              variant="primary"
            >
              {isGenerating ? "处理中" : existingReportId ? "更新报告" : "保存报告"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function ReportSuccessDialog({
  onClose,
  onOpen,
  report,
  updated = false,
}: {
  onClose: () => void;
  onOpen: () => void;
  report: ReportRead;
  updated?: boolean;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-success-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon success">
          <CheckCircle2 aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-success-title">{updated ? "报告已更新" : "报告已生成"}</h2>
          <p>“{report.title}”已经写入特性的问题报告列表。</p>
          <div className="dialog-actions">
            <Button onClick={onClose} type="button" variant="secondary">
              留在会话
            </Button>
            <Button onClick={onOpen} type="button" variant="primary">
              查看报告
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function DeleteSessionDialog({
  errorMessage,
  isDeleting,
  onCancel,
  onConfirm,
  sessionTitle,
}: {
  errorMessage: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  sessionTitle: string;
}) {
  useForwardErrorToAppFeedback(errorMessage, { title: "删除会话失败" });

  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="delete-session-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="delete-session-title">删除会话</h2>
          <p>确认删除“{sessionTitle}”？删除后会话记录和关联附件将被移除。</p>
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
