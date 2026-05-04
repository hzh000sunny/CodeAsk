import { Clock3, FilePenLine, Info, Link2, Upload } from "lucide-react";

import { Button } from "../ui/button";

export function WikiFloatingActions({
  canEdit,
  onCopyLink,
  onEdit,
  onOpenDetail,
  onOpenHistory,
  onOpenImport,
}: {
  canEdit: boolean;
  onCopyLink: () => void;
  onEdit: () => void;
  onOpenDetail: () => void;
  onOpenHistory: () => void;
  onOpenImport: () => void;
}) {
  return (
    <div className="wiki-floating-actions">
      <Button icon={<Info size={15} />} onClick={onOpenDetail} type="button" variant="secondary">
        详情
      </Button>
      <Button
        icon={<Clock3 size={15} />}
        onClick={onOpenHistory}
        type="button"
        variant="secondary"
      >
        历史版本
      </Button>
      <Button
        icon={<Link2 size={15} />}
        onClick={onCopyLink}
        type="button"
        variant="secondary"
      >
        复制链接
      </Button>
      {canEdit ? (
        <>
          <Button
            icon={<Upload size={15} />}
            onClick={onOpenImport}
            type="button"
            variant="secondary"
          >
            导入
          </Button>
          <Button
            icon={<FilePenLine size={15} />}
            onClick={onEdit}
            type="button"
            variant="primary"
          >
            编辑
          </Button>
        </>
      ) : null}
    </div>
  );
}
