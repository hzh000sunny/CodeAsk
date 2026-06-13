import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderGit2, GitBranch, Lock } from "lucide-react";

import {
  linkFeatureRepo,
  listFeatureRepos,
  listRepos,
  unlinkFeatureRepo,
} from "../../lib/api";
import type { RepoOut, RepoStatus } from "../../types/api";
import { Badge } from "../ui/badge";

const REPO_STATUS: Record<RepoStatus, { key: string; label: string }> = {
  ready: { key: "ready", label: "就绪" },
  cloning: { key: "cloning", label: "克隆中" },
  registered: { key: "pending", label: "待同步" },
  failed: { key: "failed", label: "同步失败" },
};

export function ReposPanel({
  canManageFeature,
  featureId,
}: {
  canManageFeature: boolean;
  featureId?: number;
}) {
  const queryClient = useQueryClient();
  const { data: globalRepos = [] } = useQuery({
    queryKey: ["repos"],
    queryFn: listRepos,
  });
  const { data: fetchedFeatureRepos = [] } = useQuery({
    queryKey: ["feature-repos", featureId],
    queryFn: () => listFeatureRepos(featureId ?? 0),
    enabled: Boolean(featureId),
  });
  const linkedIds = useMemo(
    () => new Set(fetchedFeatureRepos.map((repo) => repo.id)),
    [fetchedFeatureRepos],
  );
  // 保持仓库池的自然顺序：勾选是多选操作，自上而下连续勾选时不应让刚勾的行跳位
  const linkMutation = useMutation({
    mutationFn: async ({
      repo,
      checked,
    }: {
      repo: RepoOut;
      checked: boolean;
    }) => {
      if (!featureId) {
        return;
      }
      if (checked) {
        await linkFeatureRepo(featureId, repo.id);
      } else {
        await unlinkFeatureRepo(featureId, repo.id);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["feature-repos", featureId],
      });
    },
  });

  return (
    <div className="tab-content repos-tab-content">
      <section className="surface">
        <div className="repos-head">
          <div className="section-title">
            <GitBranch aria-hidden="true" size={18} />
            <h2>关联仓库</h2>
          </div>
          {globalRepos.length > 0 ? (
            <span className="repos-count">
              已关联 <strong>{linkedIds.size}</strong> / 共 {globalRepos.length}
            </span>
          ) : null}
        </div>
        {!canManageFeature && globalRepos.length > 0 ? (
          <div className="repos-readonly-note">
            <Lock aria-hidden="true" size={14} />
            <span>只读：你没有该特性的管理权限，无法更改关联。</span>
          </div>
        ) : null}
        {globalRepos.length === 0 ? (
          <div className="empty-block wide repos-empty-pool">
            <p>仓库池中暂无仓库。</p>
            <p className="repos-empty-hint">
              前往「设置 → 仓库管理」添加仓库后，即可在此关联到当前特性。
            </p>
          </div>
        ) : (
          <ul className="check-list">
            {globalRepos.map((repo) => {
              const status = REPO_STATUS[repo.status];
              const location =
                repo.source === "git" ? repo.url : repo.local_path;
              return (
                <li
                  data-linked={linkedIds.has(repo.id) ? "true" : undefined}
                  key={repo.id}
                >
                  <label className="repo-check-row">
                    <input
                      checked={linkedIds.has(repo.id)}
                      disabled={
                        !featureId ||
                        !canManageFeature ||
                        linkMutation.isPending
                      }
                      onChange={(event) =>
                        linkMutation.mutate({
                          repo,
                          checked: event.target.checked,
                        })
                      }
                      type="checkbox"
                    />
                    <span aria-hidden="true" className="repo-source-glyph">
                      {repo.source === "git" ? (
                        <GitBranch size={16} />
                      ) : (
                        <FolderGit2 size={16} />
                      )}
                    </span>
                    <span className="repo-meta">
                      <strong>{repo.name}</strong>
                      <small>{location}</small>
                    </span>
                    <Badge className={`repo-status-chip is-${status.key}`}>
                      {status.label}
                    </Badge>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
