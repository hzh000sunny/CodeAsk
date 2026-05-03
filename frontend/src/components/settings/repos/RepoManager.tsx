import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus } from "lucide-react";

import {
  createRepo,
  deleteRepo,
  listRepos,
  refreshRepo,
  updateRepo,
} from "../../../lib/api";
import { Button } from "../../ui/button";
import { messageFromApiError } from "../settings-utils";
import type { RepoUpdatePayload } from "../settings-types";
import { RepoCreateForm } from "./RepoCreateForm";
import { RepoRow } from "./RepoRow";

export function RepoManager() {
  const queryClient = useQueryClient();
  const noticeTimeoutRef = useRef<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "success" | "danger";
    message: string;
  } | null>(null);
  const { data: repos = [] } = useQuery({
    queryKey: ["repos"],
    queryFn: listRepos,
  });

  useEffect(() => {
    return () => {
      if (noticeTimeoutRef.current) {
        window.clearTimeout(noticeTimeoutRef.current);
      }
    };
  }, []);

  function showNotice(tone: "success" | "danger", message: string) {
    if (noticeTimeoutRef.current) {
      window.clearTimeout(noticeTimeoutRef.current);
    }
    setNotice({ tone, message });
    noticeTimeoutRef.current = window.setTimeout(() => {
      setNotice(null);
      noticeTimeoutRef.current = null;
    }, 3200);
  }

  const createMutation = useMutation({
    mutationFn: (payload: RepoUpdatePayload) => createRepo(payload),
    onSuccess: () => {
      setShowForm(false);
      showNotice("success", "仓库已添加");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `添加仓库失败：${messageFromApiError(error)}`);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({
      repoId,
      payload,
    }: {
      repoId: string;
      payload: RepoUpdatePayload;
    }) => updateRepo(repoId, payload),
    onSuccess: () => {
      showNotice("success", "仓库已保存");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `保存仓库失败：${messageFromApiError(error)}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteRepo,
    onSuccess: () => {
      showNotice("success", "仓库已删除");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `删除仓库失败：${messageFromApiError(error)}`);
    },
  });
  const refreshMutation = useMutation({
    mutationFn: refreshRepo,
    onSuccess: () => {
      showNotice("success", "仓库同步已提交");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `同步仓库失败：${messageFromApiError(error)}`);
    },
  });

  return (
    <section className="surface">
      <div className="section-title">
        <GitBranch aria-hidden="true" size={18} />
        <h2>仓库管理</h2>
      </div>
      <div className="content-toolbar slim">
        <p>维护 CodeAsk 后端用于代码检索和 Agent 调查的全局仓库缓存。</p>
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowForm((value) => !value)}
          type="button"
          variant="primary"
        >
          添加仓库
        </Button>
      </div>
      {notice ? (
        <div
          className="settings-toast"
          data-tone={notice.tone}
          role={notice.tone === "danger" ? "alert" : "status"}
        >
          {notice.message}
        </div>
      ) : null}
      {showForm ? (
        <RepoCreateForm
          disabled={createMutation.isPending}
          onCancel={() => setShowForm(false)}
          onSubmit={(payload) => createMutation.mutate(payload)}
        />
      ) : null}
      {repos.length === 0 ? (
        <div className="empty-block wide">
          <p>暂无仓库</p>
        </div>
      ) : (
        <ul className="data-list settings-config-list">
          {repos.map((repo) => (
            <RepoRow
              key={repo.id}
              deleting={deleteMutation.isPending}
              onDelete={() => deleteMutation.mutate(repo.id)}
              onRefresh={() => refreshMutation.mutate(repo.id)}
              onUpdate={(payload) =>
                updateMutation.mutate({ repoId: repo.id, payload })
              }
              refreshing={refreshMutation.isPending}
              repo={repo}
              updating={updateMutation.isPending}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
