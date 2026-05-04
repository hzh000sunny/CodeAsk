import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpenText, FolderTree, ShieldCheck } from "lucide-react";

import { getWikiTree, listWikiReportProjections } from "../../lib/wiki/api";
import { Button } from "../ui/button";

export function KnowledgePanel({
  featureId,
  onOpenWiki,
}: {
  featureId?: number;
  onOpenWiki: (featureId: number) => void;
}) {
  const treeQuery = useQuery({
    queryKey: ["feature-knowledge-preview", featureId],
    queryFn: () => getWikiTree(featureId as number),
    enabled: Boolean(featureId),
  });
  const reportsQuery = useQuery({
    queryKey: ["feature-knowledge-reports", featureId],
    queryFn: () => listWikiReportProjections(featureId as number),
    enabled: Boolean(featureId),
  });

  const knowledgeRoots = useMemo(() => {
    return (treeQuery.data?.nodes ?? []).filter(
      (node) => node.parent_id == null || node.system_role != null,
    );
  }, [treeQuery.data?.nodes]);

  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="content-toolbar">
          <div className="section-title">
            <FolderTree aria-hidden="true" size={18} />
            <h2>Wiki 目录预览</h2>
          </div>
          {featureId ? (
            <Button onClick={() => onOpenWiki(featureId)} type="button" variant="secondary">
              进入 Wiki 工作台
            </Button>
          ) : null}
        </div>
        {!featureId ? (
          <div className="empty-block wide">
            <p>先选择一个特性，再查看该特性的 Wiki 目录。</p>
          </div>
        ) : treeQuery.isLoading ? (
          <div className="empty-block wide">
            <p>正在加载 Wiki 目录。</p>
          </div>
        ) : knowledgeRoots.length === 0 ? (
          <div className="empty-block wide">
            <p>当前特性还没有 Wiki 内容。</p>
          </div>
        ) : (
          <ul className="data-list">
            {knowledgeRoots.map((node) => (
              <li key={node.id}>
                <div className="plain-row-button static">
                  <span>{node.name}</span>
                  <small>{node.path}</small>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="surface">
        <div className="section-title">
          <BookOpenText aria-hidden="true" size={18} />
          <h2>知识状态</h2>
        </div>
        {!featureId ? (
          <div className="empty-block wide">
            <p>当前没有可预览的特性。</p>
          </div>
        ) : (
          <dl className="meta-grid">
            <dt>文档节点</dt>
            <dd>
              {(treeQuery.data?.nodes ?? []).filter((node) => node.type === "document").length}
            </dd>
            <dt>报告投影</dt>
            <dd>
              <span className="inline-icon-text">
                <ShieldCheck aria-hidden="true" size={14} />
                {reportsQuery.data?.items.length ?? 0}
              </span>
            </dd>
            <dt>系统目录</dt>
            <dd>
              {(treeQuery.data?.nodes ?? []).filter((node) => node.system_role != null).length}
            </dd>
          </dl>
        )}
      </section>
    </div>
  );
}
