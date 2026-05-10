import { useQuery } from "@tanstack/react-query";

import { getMe, listFeatureAdmins } from "../../lib/api";

export function useFeaturePermissions(featureId?: number | null) {
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const { data: admins = [] } = useQuery({
    queryKey: ["feature-admins", featureId],
    queryFn: () => listFeatureAdmins(featureId as number),
    enabled: Boolean(featureId),
  });
  const isAdmin = me?.role === "admin";
  const canManageFeature =
    Boolean(featureId) &&
    (isAdmin ||
      admins.some((admin) => admin.user_id === me?.subject_id && me?.authenticated));

  return {
    admins,
    canCreateFeature: Boolean(isAdmin),
    canManageFeature,
    isAdmin: Boolean(isAdmin),
    me,
  };
}
