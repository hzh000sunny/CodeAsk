import { useEffect } from "react";

import { useAppFeedback } from "./AppFeedback";

export function useForwardErrorToAppFeedback(
  message: string | null | undefined,
  options?: { title?: string },
) {
  const { showError } = useAppFeedback();
  const title = options?.title;

  useEffect(() => {
    if (!message?.trim()) {
      return;
    }
    showError(message, title ? { title } : undefined);
  }, [message, showError, title]);
}
