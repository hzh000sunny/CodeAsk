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
  const [source, setSource] = useState<RepoSource>("local_dir");
  const [location, setLocation] = useState("");

  function reset() {
    setName("");
    setSource("local_dir");
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
          <option value="local_dir">本地目录</option>
          <option value="git">Git URL</option>
        </select>
      </label>
      <label className="field-label compact repo-edit-field repo-location-field">
        {source === "local_dir" ? "本地路径" : "Git URL"}
        <Input
          onChange={(event) => setLocation(event.target.value)}
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
