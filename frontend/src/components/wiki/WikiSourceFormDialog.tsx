import { useEffect, useState } from "react";

import type {
  WikiSourceCreatePayload,
  WikiSourceKind,
  WikiSourceRead,
  WikiSourceUpdatePayload,
} from "../../types/wiki";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

function buildInitialState(source: WikiSourceRead | null) {
  return {
    displayName: source?.display_name ?? "",
    kind: source?.kind ?? "directory_import",
    metadataText: source?.metadata_json ? JSON.stringify(source.metadata_json, null, 2) : "",
    uri: source?.uri ?? "",
  };
}

export function WikiSourceFormDialog({
  mode,
  pending,
  source,
  onCancel,
  onSubmit,
}: {
  mode: "create" | "edit";
  pending: boolean;
  source: WikiSourceRead | null;
  onCancel: () => void;
  onSubmit: (
    payload: Omit<WikiSourceCreatePayload, "space_id"> | WikiSourceUpdatePayload,
  ) => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState("");
  const [kind, setKind] = useState<WikiSourceKind>("directory_import");
  const [uri, setUri] = useState("");
  const [metadataText, setMetadataText] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const next = buildInitialState(source);
    setDisplayName(next.displayName);
    setKind(next.kind);
    setUri(next.uri);
    setMetadataText(next.metadataText);
    setErrorMessage("");
  }, [source]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let metadataJson: Record<string, unknown> | null = null;

    if (metadataText.trim()) {
      try {
        const parsed = JSON.parse(metadataText) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setErrorMessage("附加元数据必须是 JSON 对象");
          return;
        }
        metadataJson = parsed as Record<string, unknown>;
      } catch {
        setErrorMessage("附加元数据不是合法的 JSON");
        return;
      }
    }

    setErrorMessage("");
    if (mode === "create") {
      await onSubmit({
        display_name: displayName.trim(),
        kind,
        metadata_json: metadataJson,
        uri: uri.trim() || null,
      });
      return;
    }
    await onSubmit({
      display_name: displayName.trim(),
      metadata_json: metadataJson,
      uri: uri.trim() || null,
    });
  }

  return (
    <form aria-label="来源表单" className="wiki-source-form" onSubmit={handleSubmit}>
      <div className="wiki-source-form-header">
        <div>
          <strong>{mode === "create" ? "添加来源" : "编辑来源"}</strong>
          <p>登记可追溯的来源信息，便于后续同步、追踪和定位材料来源。</p>
        </div>
      </div>
      <div className="wiki-source-form-grid">
        <label className="field-label compact">
          来源名称
          <Input
            aria-label="来源名称"
            autoFocus
            onChange={(event) => setDisplayName(event.target.value)}
            value={displayName}
          />
        </label>
        <label className="field-label compact">
          来源类型
          <select
            aria-label="来源类型"
            className="input wiki-source-select"
            disabled={mode === "edit"}
            onChange={(event) => setKind(event.target.value as WikiSourceKind)}
            value={kind}
          >
            <option value="directory_import">目录导入</option>
            <option value="manual_upload">手动录入</option>
            <option value="session_promotion">会话晋级</option>
          </select>
        </label>
        <label className="field-label compact">
          URI / 路径
          <Input
            aria-label="URI / 路径"
            onChange={(event) => setUri(event.target.value)}
            placeholder="例如 file:///srv/wiki/payment"
            value={uri}
          />
        </label>
        <label className="field-label compact">
          附加元数据
          <Textarea
            aria-label="附加元数据"
            onChange={(event) => setMetadataText(event.target.value)}
            placeholder='例如 {"root_path":"docs/runbooks","branch":"main"}'
            value={metadataText}
          />
        </label>
      </div>
      {errorMessage ? (
        <div className="inline-alert danger" role="alert">
          {errorMessage}
        </div>
      ) : null}
      <div className="dialog-actions wiki-source-form-actions">
        <Button disabled={pending} onClick={onCancel} type="button" variant="secondary">
          取消
        </Button>
        <Button disabled={!displayName.trim() || pending} type="submit" variant="primary">
          {pending ? "保存中" : "保存来源"}
        </Button>
      </div>
    </form>
  );
}
