import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type { RepoSource, RepoUpdatePayload } from "../settings-types";

export function RepoCreateForm({
  disabled,
  onCancel,
  onSubmit,
}: {
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (payload: RepoUpdatePayload) => void;
}) {
  const [name, setName] = useState("");
  const [source, setSource] = useState<RepoSource>("git");
  const [location, setLocation] = useState("");

  function reset() {
    setName("");
    setSource("git");
    setLocation("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      name: name.trim(),
      source,
      local_path: source === "local_dir" ? location.trim() : null,
      url: source === "git" ? location.trim() : null,
    });
  }

  return (
    <form className="inline-form repo-edit-form repo-create-form" onSubmit={submit}>
      <div className="form-row">
        <label className="field-label compact repo-edit-field">
          仓库名称
          <Input onChange={(event) => setName(event.target.value)} value={name} />
        </label>
        <label className="field-label compact repo-edit-field">
          类型
          <select
            className="input"
            onChange={(event) => setSource(event.target.value as RepoSource)}
            value={source}
          >
            <option value="git">Git URL</option>
            <option value="local_dir">本地目录</option>
          </select>
        </label>
      </div>
      <label className="field-label compact repo-edit-field repo-location-field">
        {source === "local_dir" ? "本地路径" : "Git URL"}
        <Input
          className="console-mono"
          onChange={(event) => setLocation(event.target.value)}
          placeholder={
            source === "local_dir"
              ? "/绝对路径/到/本地仓库"
              : "https://github.com/org/repo.git"
          }
          value={location}
        />
      </label>
      <div className="form-actions">
        <Button
          disabled={!name.trim() || !location.trim() || disabled}
          type="submit"
          variant="primary"
        >
          创建仓库
        </Button>
        <Button
          disabled={disabled}
          onClick={() => {
            reset();
            onCancel();
          }}
          type="button"
          variant="quiet"
        >
          取消
        </Button>
      </div>
    </form>
  );
}
