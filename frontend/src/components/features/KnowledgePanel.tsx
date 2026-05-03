import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FilePlus2, Trash2 } from "lucide-react";

import { deleteDocument, listDocuments, uploadDocument } from "../../lib/api";
import type { DocumentRead } from "../../types/api";
import { Button } from "../ui/button";

export function KnowledgePanel({ featureId }: { featureId?: number }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<DocumentRead | null>(
    null,
  );
  const { data: fetchedDocuments = [] } = useQuery({
    queryKey: ["documents", featureId],
    queryFn: () => listDocuments(featureId),
    enabled: Boolean(featureId),
  });
  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const uploaded: DocumentRead[] = [];
      for (const file of files) {
        const relativePath = file.webkitRelativePath || file.name;
        uploaded.push(
          await uploadDocument({
            feature_id: featureId ?? 0,
            file,
            title: relativePath,
          }),
        );
      }
      return uploaded;
    },
    onSuccess: (documents) => {
      setStatus(`已上传 ${documents.length} 个 Wiki 文件`);
      void queryClient.invalidateQueries({
        queryKey: ["documents", featureId],
      });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      setSelectedDocument(null);
      setStatus("已删除 Wiki 文档");
      void queryClient.invalidateQueries({
        queryKey: ["documents", featureId],
      });
    },
  });

  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="content-toolbar">
          <div className="section-title">
            <Database aria-hidden="true" size={18} />
            <h2>知识库</h2>
          </div>
          <label className="file-button">
            <FilePlus2 aria-hidden="true" size={16} />
            上传 Wiki
            <input
              aria-label="选择 Wiki 文件或目录"
              accept=".md,.markdown,.txt,.pdf,.docx"
              disabled={!featureId || uploadMutation.isPending}
              multiple
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (files.length > 0) {
                  uploadMutation.mutate(files);
                }
              }}
              type="file"
              {...{ webkitdirectory: "" }}
            />
          </label>
        </div>
        {status ? <p className="action-status">{status}</p> : null}
        {fetchedDocuments.length === 0 ? (
          <div className="empty-block wide">
            <p>当前特性还没有上传 Wiki 文档。</p>
          </div>
        ) : (
          <ul className="data-list">
            {fetchedDocuments.map((document) => (
              <li key={document.id}>
                <button
                  className="plain-row-button"
                  onClick={() => setSelectedDocument(document)}
                  type="button"
                >
                  <span>{document.title}</span>
                  <small>
                    {document.kind} · {document.path}
                  </small>
                </button>
                <Button
                  disabled={deleteMutation.isPending}
                  icon={<Trash2 size={15} />}
                  onClick={() => deleteMutation.mutate(document.id)}
                  type="button"
                  variant="quiet"
                >
                  删除
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="surface">
        <div className="section-title">
          <FilePlus2 aria-hidden="true" size={18} />
          <h2>预览</h2>
        </div>
        {selectedDocument ? (
          <dl className="meta-grid">
            <dt>标题</dt>
            <dd>{selectedDocument.title}</dd>
            <dt>路径</dt>
            <dd>{selectedDocument.path}</dd>
            <dt>类型</dt>
            <dd>{selectedDocument.kind}</dd>
            <dt>上传人</dt>
            <dd>{selectedDocument.uploaded_by_subject_id}</dd>
            <dt>更新时间</dt>
            <dd>{new Date(selectedDocument.updated_at).toLocaleString()}</dd>
          </dl>
        ) : (
          <div className="empty-block wide">
            <p>选择左侧文档后预览元信息。</p>
          </div>
        )}
      </section>
    </div>
  );
}
