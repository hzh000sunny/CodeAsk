import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getWikiTree, promoteSessionAttachmentToWiki } from "../../lib/wiki/api";
import { wikiQueryKeys } from "../../lib/wiki/query-keys";
import {
  buildWikiNodeDisplayPath,
  buildWikiTree,
  flattenTree,
  formatWikiStoredPath,
} from "../../lib/wiki/tree";
import { canCreateChildrenInWikiNode } from "../../lib/wiki/system-node-actions";
import type { AttachmentResponse, FeatureRead } from "../../types/api";
import type {
  WikiPromotionRead,
  WikiPromotionTargetKind,
  WikiTreeRead,
} from "../../types/wiki";
import { messageFromError } from "./session-model";

interface PromotionTargetOption {
  label: string;
  value: string;
}

function inferPromotionTargetKind(attachment: AttachmentResponse): WikiPromotionTargetKind {
  const name = (attachment.original_filename || attachment.display_name).toLowerCase();
  if (attachment.kind === "image") {
    return "asset";
  }
  if (name.endsWith(".md") || name.endsWith(".txt") || name.endsWith(".log")) {
    return "document";
  }
  return "asset";
}

function deriveDocumentName(attachment: AttachmentResponse) {
  const raw = attachment.display_name || attachment.original_filename || "新的 Wiki";
  return raw.replace(/\.[^.]+$/, "").trim() || "新的 Wiki";
}

function buildFolderOptions(treeData: WikiTreeRead | undefined) {
  if (!treeData) {
    return [] as PromotionTargetOption[];
  }
  const roots = buildWikiTree(treeData.nodes);
  return flattenTree(roots)
    .filter((node) => canCreateChildrenInWikiNode(node))
    .map((node) => ({
      label:
        buildWikiNodeDisplayPath(roots, node.id) ??
        formatWikiStoredPath(node.path) ??
        node.name,
      value: String(node.id),
    }));
}

export function useSessionWikiPromotion({
  detectedFeatureIds,
  features,
  onOpenWiki,
  showActionNotice,
}: {
  detectedFeatureIds: number[];
  features: FeatureRead[];
  onOpenWiki?: (target: { featureId: number; nodeId: number }) => void;
  showActionNotice: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [attachment, setAttachment] = useState<AttachmentResponse | null>(null);
  const [featureId, setFeatureId] = useState("");
  const [parentId, setParentId] = useState("");
  const [documentName, setDocumentName] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<WikiPromotionRead | null>(null);

  const selectedFeatureId = featureId ? Number(featureId) : null;
  const targetKind = attachment ? inferPromotionTargetKind(attachment) : null;

  const treeQuery = useQuery({
    queryKey: wikiQueryKeys.tree(selectedFeatureId),
    queryFn: () => getWikiTree(selectedFeatureId),
    enabled: attachment != null && selectedFeatureId != null,
  });

  const folderOptions = useMemo(
    () => buildFolderOptions(treeQuery.data),
    [treeQuery.data],
  );

  useEffect(() => {
    if (!attachment) {
      return;
    }
    const preferredFeatureId =
      detectedFeatureIds.find((candidate) => features.some((item) => item.id === candidate)) ??
      (features.length === 1 ? features[0]?.id : undefined);
    if (preferredFeatureId != null) {
      setFeatureId(String(preferredFeatureId));
    } else {
      setFeatureId("");
    }
    setDocumentName(deriveDocumentName(attachment));
    setParentId("");
    setErrorMessage("");
    setResult(null);
  }, [attachment, detectedFeatureIds, features]);

  useEffect(() => {
    if (folderOptions.length === 0) {
      setParentId("");
      return;
    }
    if (folderOptions.some((option) => option.value === parentId)) {
      return;
    }
    const knowledgeRoot =
      folderOptions.find((option) => option.label === "知识库") ?? folderOptions[0];
    setParentId(knowledgeRoot?.value ?? "");
  }, [folderOptions, parentId]);

  const promoteMutation = useMutation({
    mutationFn: async () => {
      if (!attachment || selectedFeatureId == null || !treeQuery.data?.space) {
        throw new Error("请先选择特性和目标目录");
      }
      return promoteSessionAttachmentToWiki({
        sessionId: attachment.session_id,
        attachmentId: attachment.id,
        spaceId: treeQuery.data.space.id,
        parentId: parentId ? Number(parentId) : null,
        targetKind: targetKind ?? "asset",
        name: targetKind === "document" ? documentName.trim() : null,
      });
    },
    onSuccess: async (promotion) => {
      const promotedFeatureId = promotion.node.feature_id ?? selectedFeatureId ?? null;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(null) }),
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(promotedFeatureId) }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "search"] }),
        promotion.node.type === "document"
          ? queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(promotion.node.id) })
          : Promise.resolve(),
      ]);
      setResult(promotion);
      setErrorMessage("");
      showActionNotice("会话附件已写入 Wiki");
    },
    onError: (error) => {
      setErrorMessage(`晋级失败：${messageFromError(error)}`);
    },
  });

  return {
    attachment,
    canSubmit:
      attachment != null &&
      selectedFeatureId != null &&
      parentId !== "" &&
      !treeQuery.isFetching &&
      (targetKind !== "document" || documentName.trim().length > 0),
    closeDialog: () => {
      setAttachment(null);
      setErrorMessage("");
      setResult(null);
    },
    documentName,
    errorMessage,
    featureId,
    folderOptions,
    openDialog: (nextAttachment: AttachmentResponse) => {
      setAttachment(nextAttachment);
    },
    openPromotedWiki: () => {
      if (!result || !onOpenWiki || result.node.feature_id == null) {
        return;
      }
      const nextNodeId = result.node.type === "document" ? result.node.id : result.node.parent_id;
      onOpenWiki({
        featureId: result.node.feature_id,
        nodeId: nextNodeId ?? result.node.id,
      });
      setAttachment(null);
      setResult(null);
    },
    parentId,
    promoteMutation,
    result,
    setDocumentName,
    setFeatureId,
    setParentId,
    targetKind,
    treeLoading: treeQuery.isFetching,
  };
}
