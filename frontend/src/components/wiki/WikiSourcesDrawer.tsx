import { useState } from "react";
import { Plus, X } from "lucide-react";

import type {
  WikiSourceCreatePayload,
  WikiSourceRead,
  WikiSourceUpdatePayload,
} from "../../types/wiki";
import { Button } from "../ui/button";
import { WikiSourceFormDialog } from "./WikiSourceFormDialog";
import { WikiSourceList } from "./WikiSourceList";

type WikiSourceFormState =
  | { mode: "create"; source: null }
  | { mode: "edit"; source: WikiSourceRead }
  | null;

export function WikiSourcesDrawer({
  onClose,
  onCreate,
  onSync,
  onUpdate,
  open,
  recentSyncedSourceId,
  sources,
  sourcesLoading,
  syncPendingSourceId,
  submitting,
}: {
  onClose: () => void;
  onCreate: (payload: Omit<WikiSourceCreatePayload, "space_id">) => Promise<void>;
  onSync: (sourceId: number) => void;
  onUpdate: (sourceId: number, payload: WikiSourceUpdatePayload) => Promise<void>;
  open: boolean;
  recentSyncedSourceId: number | null;
  sources: WikiSourceRead[];
  sourcesLoading: boolean;
  syncPendingSourceId: number | null;
  submitting: boolean;
}) {
  const [formState, setFormState] = useState<WikiSourceFormState>(null);

  if (!open) {
    return null;
  }

  return (
    <div className="wiki-drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        aria-labelledby="wiki-sources-title"
        className="wiki-drawer"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="wiki-drawer-header">
          <div>
            <h2 id="wiki-sources-title">来源治理</h2>
            <p>统一管理这个特性的 Wiki 来源记录，便于后续追溯、同步和排查材料来源。</p>
          </div>
          <button
            aria-label="关闭来源治理"
            className="button button-quiet"
            onClick={onClose}
            type="button"
          >
            <span className="button-icon">
              <X size={15} />
            </span>
          </button>
        </div>
        <div className="wiki-sources-body">
          <div className="wiki-sources-toolbar">
            <div className="wiki-sources-summary">
              <strong>{sources.length} 个来源</strong>
              <span>支持登记来源名、路径和附加元数据。</span>
            </div>
            <Button
              icon={<Plus size={15} />}
              onClick={() => setFormState({ mode: "create", source: null })}
              type="button"
              variant="primary"
            >
              添加来源
            </Button>
          </div>
          {formState ? (
            <WikiSourceFormDialog
              mode={formState.mode}
              onCancel={() => setFormState(null)}
              onSubmit={async (payload) => {
                if (formState.mode === "create") {
                  await onCreate(payload as Omit<WikiSourceCreatePayload, "space_id">);
                } else {
                  await onUpdate(formState.source.id, payload as WikiSourceUpdatePayload);
                }
                setFormState(null);
              }}
              pending={submitting}
              source={formState.source}
            />
          ) : null}
          {sourcesLoading ? (
            <div className="wiki-source-empty">
              <strong>正在加载来源</strong>
              <p>来源列表会在这里展示。</p>
            </div>
          ) : (
            <WikiSourceList
              onEdit={(source) => setFormState({ mode: "edit", source })}
              onSync={(source) => onSync(source.id)}
              recentSyncedSourceId={recentSyncedSourceId}
              sources={sources}
              syncPendingSourceId={syncPendingSourceId}
            />
          )}
        </div>
      </aside>
    </div>
  );
}
