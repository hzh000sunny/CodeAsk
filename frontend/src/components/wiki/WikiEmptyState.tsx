import { BookText, FilePlus2, FolderOpen, Sparkles } from "lucide-react";

import { Button } from "../ui/button";

export function WikiEmptyState({
  canCreate,
  description,
  mode = "feature",
  onCreateDocument,
  onImport,
  title,
}: {
  canCreate: boolean;
  description: string;
  mode?: "feature" | "global";
  onCreateDocument?: () => void;
  onImport?: () => void;
  title: string;
}) {
  const isFeatureMode = mode === "feature";

  return (
    <div className="wiki-empty-state">
      <div className="wiki-empty-card">
        <div className="wiki-empty-card-head">
          <div className="wiki-empty-icon">
            {isFeatureMode ? <BookText aria-hidden="true" size={22} /> : <Sparkles aria-hidden="true" size={22} />}
          </div>
          <div className="wiki-empty-copy">
            {isFeatureMode ? <span className="wiki-empty-eyebrow">Wiki 工作区</span> : null}
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
        </div>

        {isFeatureMode ? (
          <>
            <div className="wiki-empty-paths">
              <section className="wiki-empty-path-card" data-tone="primary">
                <div className="wiki-empty-path-icon">
                  <FilePlus2 aria-hidden="true" size={16} />
                </div>
                <div>
                  <h3>新建空白 Wiki</h3>
                  <p>从一篇说明文档开始，适合写背景、约定、排障手册和沉淀知识。</p>
                </div>
              </section>
              <section className="wiki-empty-path-card">
                <div className="wiki-empty-path-icon">
                  <FolderOpen aria-hidden="true" size={16} />
                </div>
                <div>
                  <h3>导入现有资料</h3>
                  <p>导入已有 Markdown 或目录，把当前资料快速整理成可搜索的 Wiki。</p>
                </div>
              </section>
            </div>

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
                  导入 Wiki
                </Button>
              </div>
            ) : null}

            <div className="wiki-empty-meta">
              <span>支持 Markdown</span>
              <span>支持目录导入</span>
              <span>导入后自动索引</span>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
