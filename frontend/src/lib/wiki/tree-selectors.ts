import type { WikiTreeNodeRecord } from "./tree";

export function findFeatureRootNode(
  roots: WikiTreeNodeRecord[],
  featureId: number | null,
): WikiTreeNodeRecord | null {
  if (featureId == null) {
    return null;
  }
  for (const node of roots) {
    if (
      (node.system_role === "feature_space_current" ||
        node.system_role === "feature_space_history") &&
      node.feature_id === featureId
    ) {
      return node;
    }
    const child = findFeatureRootNode(node.children, featureId);
    if (child) {
      return child;
    }
  }
  return null;
}

export function findSystemRoleNode(
  roots: WikiTreeNodeRecord[],
  systemRole: string,
): WikiTreeNodeRecord | null {
  for (const node of roots) {
    if (node.system_role === systemRole) {
      return node;
    }
    const child = findSystemRoleNode(node.children, systemRole);
    if (child) {
      return child;
    }
  }
  return null;
}
