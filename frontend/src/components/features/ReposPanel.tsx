import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";

import {
  linkFeatureRepo,
  listFeatureRepos,
  listRepos,
  unlinkFeatureRepo,
} from "../../lib/api";
import type { RepoOut } from "../../types/api";

export function ReposPanel({ featureId }: { featureId?: number }) {
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
  const linkedIds = new Set(fetchedFeatureRepos.map((repo) => repo.id));
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
    <div className="tab-content">
      <section className="surface">
        <div className="section-title">
          <GitBranch aria-hidden="true" size={18} />
          <h2>关联仓库</h2>
        </div>
        {globalRepos.length === 0 ? (
          <div className="empty-block wide">
            <p>仓库池中暂无仓库。</p>
          </div>
        ) : (
          <ul className="check-list">
            {globalRepos.map((repo) => (
              <li key={repo.id}>
                <label className="repo-check-row">
                  <input
                    checked={linkedIds.has(repo.id)}
                    disabled={!featureId || linkMutation.isPending}
                    onChange={(event) =>
                      linkMutation.mutate({
                        repo,
                        checked: event.target.checked,
                      })
                    }
                    type="checkbox"
                  />
                  <span>
                    <strong>{repo.name}</strong>
                    <small>
                      {repo.status} ·{" "}
                      {repo.source === "git" ? repo.url : repo.local_path}
                    </small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
