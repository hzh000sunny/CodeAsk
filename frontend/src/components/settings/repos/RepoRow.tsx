import { useState } from "react";
import type { FormEvent } from "react";
import { Pencil, RefreshCw, Trash2 } from "lucide-react";

import type { RepoOut } from "../../../types/api";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type { RepoSource, RepoUpdatePayload } from "../settings-types";

export function RepoRow({
  deleting,
  onDelete,
  onRefresh,
  onUpdate,
  refreshing,
  repo,
  updating,
}: {
  deleting: boolean;
  onDelete: () => void;
  onRefresh: () => void;
  onUpdate: (payload: RepoUpdatePayload) => void;
  refreshing: boolean;
  repo: RepoOut;
  updating: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(repo.name);
  const [source, setSource] = useState<RepoSource>(repo.source);
  const [location, setLocation] = useState(
    repo.source === "git" ? (repo.url ?? "") : (repo.local_path ?? ""),
  );
  const syncLabel = repo.status === "failed" ? "重试同步" : "同步";
  const locationLabel =
    source === "local_dir" ? "编辑本地路径" : "编辑 Git URL";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onUpdate({
      name: name.trim(),
      source,
      local_path: source === "local_dir" ? location.trim() : null,
      url: source === "git" ? location.trim() : null,
    });
    setEditing(false);
  }

  return (
    <li data-editing={editing ? "true" : undefined}>
      {editing ? (
        <form className="inline-form repo-edit-form" onSubmit={submit}>
          <label className="field-label compact repo-edit-field">
            编辑仓库名称
            <Input
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label className="field-label compact repo-edit-field">
            编辑仓库类型
            <select
              className="input"
              onChange={(event) => setSource(event.target.value as RepoSource)}
              value={source}
            >
              <option value="local_dir">本地目录</option>
              <option value="git">Git URL</option>
            </select>
          </label>
          <label className="field-label compact repo-edit-field repo-location-field">
            {locationLabel}
            <Input
              onChange={(event) => setLocation(event.target.value)}
              value={location}
            />
          </label>
          <div className="form-actions">
            <Button
              disabled={!name.trim() || !location.trim() || updating}
              type="submit"
              variant="primary"
            >
              保存仓库
            </Button>
            <Button
              disabled={updating}
              onClick={() => setEditing(false)}
              type="button"
              variant="quiet"
            >
              取消
            </Button>
          </div>
        </form>
      ) : (
        <>
          <div className="config-summary">
            <span>{repo.name}</span>
            <small>{repo.source === "git" ? repo.url : repo.local_path}</small>
          </div>
          <div className="row-actions">
            <Badge>{repo.status}</Badge>
            <Button
              aria-label={`编辑仓库 ${repo.name}`}
              disabled={updating}
              icon={<Pencil size={15} />}
              onClick={() => setEditing(true)}
              type="button"
              variant="quiet"
            >
              编辑
            </Button>
            <Button
              aria-label={`${syncLabel}仓库 ${repo.name}`}
              disabled={refreshing}
              icon={<RefreshCw size={15} />}
              onClick={onRefresh}
              type="button"
              variant="quiet"
            >
              {syncLabel}
            </Button>
            <Button
              disabled={deleting}
              icon={<Trash2 size={15} />}
              onClick={onDelete}
              type="button"
              variant="quiet"
            >
              删除
            </Button>
          </div>
        </>
      )}
    </li>
  );
}
