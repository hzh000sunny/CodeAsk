import { BookText, FolderOpen } from "lucide-react";

import { Button } from "../ui/button";

export function WikiEmptyState({
  canCreate,
  description,
  onCreateDocument,
  onImport,
  title,
}: {
  canCreate: boolean;
  description: string;
  onCreateDocument?: () => void;
  onImport?: () => void;
  title: string;
}) {
  return (
    <div className="wiki-empty-state">
      <div className="wiki-empty-icon">
        <BookText aria-hidden="true" size={22} />
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {canCreate ? (
        <div className="wiki-empty-actions">
          <Button
            icon={<BookText size={16} />}
            onClick={onCreateDocument}
            type="button"
            variant="primary"
          >
            新建 Wiki
          </Button>
          <Button
            icon={<FolderOpen size={16} />}
            onClick={onImport}
            type="button"
            variant="secondary"
          >
            导入目录
          </Button>
        </div>
      ) : null}
    </div>
  );
}
