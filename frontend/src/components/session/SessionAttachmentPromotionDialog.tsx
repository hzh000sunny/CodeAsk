import { ArrowUpRight, BookPlus, FileText, FolderTree, ImagePlus } from "lucide-react";

import type { FeatureRead } from "../../types/api";
import type { WikiPromotionTargetKind } from "../../types/wiki";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export function SessionAttachmentPromotionDialog({
  attachmentName,
  canSubmit,
  documentName,
  errorMessage,
  featureId,
  features,
  folderOptions,
  onCancel,
  onConfirm,
  onDocumentNameChange,
  onFeatureChange,
  onParentChange,
  parentId,
  pending,
  targetKind,
  treeLoading,
}: {
  attachmentName: string;
  canSubmit: boolean;
  documentName: string;
  errorMessage: string;
  featureId: string;
  features: FeatureRead[];
  folderOptions: Array<{ label: string; value: string }>;
  onCancel: () => void;
  onConfirm: () => void;
  onDocumentNameChange: (value: string) => void;
  onFeatureChange: (value: string) => void;
  onParentChange: (value: string) => void;
  parentId: string;
  pending: boolean;
  targetKind: WikiPromotionTargetKind;
  treeLoading: boolean;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="session-promotion-title"
        aria-modal="true"
        className="confirm-dialog report-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <BookPlus aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="session-promotion-title">晋级为 Wiki</h2>
          <p>把当前会话附件沉淀到正式 Wiki，后续可被搜索、引用和继续维护。</p>
          <div className="wiki-promotion-summary">
            <strong>{attachmentName}</strong>
            <span>
              {targetKind === "document" ? "将写入 Markdown 文档" : "将写入静态资源"}
            </span>
          </div>
          <label className="field-label compact">
            目标特性
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
            目标目录
            <select
              className="input"
              disabled={!featureId || treeLoading || folderOptions.length === 0}
              onChange={(event) => onParentChange(event.target.value)}
              value={parentId}
            >
              <option value="">
                {treeLoading ? "正在加载目录" : folderOptions.length === 0 ? "暂无可用目录" : "请选择目录"}
              </option>
              {folderOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {targetKind === "document" ? (
            <label className="field-label compact">
              Wiki 标题
              <Input
                onChange={(event) => onDocumentNameChange(event.target.value)}
                value={documentName}
              />
            </label>
          ) : null}
          <div className="wiki-promotion-target">
            <Badge>
              {targetKind === "document" ? <FileText size={14} /> : <ImagePlus size={14} />}
              {targetKind === "document" ? "文档" : "资源"}
            </Badge>
            <Badge>
              <FolderTree size={14} />
              {folderOptions.find((option) => option.value === parentId)?.label ?? "未选择目录"}
            </Badge>
          </div>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button
              disabled={pending}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={!canSubmit || pending}
              onClick={onConfirm}
              type="button"
              variant="primary"
            >
              {pending ? "写入中" : "确认晋级"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function SessionAttachmentPromotionSuccessDialog({
  nodeName,
  onClose,
  onOpenWiki,
  targetKind,
}: {
  nodeName: string;
  onClose: () => void;
  onOpenWiki: () => void;
  targetKind: WikiPromotionTargetKind;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="session-promotion-success-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon success">
          <BookPlus aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="session-promotion-success-title">已写入 Wiki</h2>
          <p>
            “{nodeName}” 已作为{targetKind === "document" ? "文档" : "资源"}沉淀到目标特性。
          </p>
          <div className="dialog-actions">
            <Button onClick={onClose} type="button" variant="secondary">
              留在会话
            </Button>
            <Button
              icon={<ArrowUpRight size={15} />}
              onClick={onOpenWiki}
              type="button"
              variant="primary"
            >
              打开 Wiki
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
