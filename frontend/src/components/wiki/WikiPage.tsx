import type { WikiRouteState } from "../../lib/wiki/routing";
import { WikiWorkbench } from "./WikiWorkbench";

export function WikiPage({
  backgroundImportSession,
  onBackgroundImportChange,
  onImportNavigationGuardChange,
  onOpenFeature,
  onRouteChange,
  routeState,
}: {
  backgroundImportSession: { sessionId: number; featureId: number | null } | null;
  onBackgroundImportChange: (session: { sessionId: number; featureId: number | null } | null) => void;
  onImportNavigationGuardChange: (
    guard:
      | {
          blocking: boolean;
          continueInBackground: () => void;
          cancelImport: () => Promise<boolean>;
        }
      | null,
  ) => void;
  onOpenFeature: (featureId: number) => void;
  onRouteChange: (patch: Partial<WikiRouteState>) => void;
  routeState: WikiRouteState;
}) {
  return (
    <WikiWorkbench
      backgroundImportSession={backgroundImportSession}
      onBackgroundImportChange={onBackgroundImportChange}
      onImportNavigationGuardChange={onImportNavigationGuardChange}
      onOpenFeature={onOpenFeature}
      onRouteChange={onRouteChange}
      routeState={routeState}
    />
  );
}
