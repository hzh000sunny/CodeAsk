import { useState } from "react";
import { UserRound } from "lucide-react";

import { getNickname, getSubjectId, setNickname } from "../../lib/identity";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { LlmConfigManager } from "./llm/LlmConfigManager";

export function UserSettings() {
  const [nickname, setNicknameValue] = useState(getNickname());
  const [saved, setSaved] = useState(false);

  return (
    <div className="settings-stack">
      <section className="surface">
        <div className="section-title">
          <UserRound aria-hidden="true" size={18} />
          <h2>用户配置</h2>
        </div>
        <dl className="meta-grid">
          <dt>Subject ID</dt>
          <dd>{getSubjectId()}</dd>
        </dl>
        <div className="user-profile-form">
          <label className="user-profile-field" htmlFor="user-nickname">
            <span>昵称</span>
            <Input
              id="user-nickname"
              onChange={(event) => {
                setSaved(false);
                setNicknameValue(event.target.value);
              }}
              placeholder="可选"
              value={nickname}
            />
          </label>
          <div className="form-actions user-profile-actions">
            <Button
              onClick={() => {
                setNickname(nickname);
                setSaved(true);
              }}
              type="button"
              variant="primary"
            >
              保存用户设置
            </Button>
            {saved ? <span className="action-status inline">已保存</span> : null}
          </div>
        </div>
      </section>
      <LlmConfigManager scope="user" />
    </div>
  );
}
