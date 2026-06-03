import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Button } from "../ui/button";

export type AppFeedbackToastTone = "success" | "error";

type AppFeedbackToastState = {
  message: string;
  tone: AppFeedbackToastTone;
};

type AppFeedbackContextValue = {
  dismissError: () => void;
  showError: (message: string, options?: { title?: string }) => void;
  showSuccess: (message: string) => void;
  showToast: (message: string, options?: { tone?: AppFeedbackToastTone }) => void;
};

const AppFeedbackContext = createContext<AppFeedbackContextValue | null>(null);
const TOAST_DISMISS_MS = 4000;

export function AppFeedbackProvider({ children }: { children: ReactNode }) {
  const toastTimeoutRef = useRef<number | null>(null);
  const [toastState, setToastState] = useState<AppFeedbackToastState | null>(null);
  const [errorState, setErrorState] = useState<{
    message: string;
    title: string;
  } | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        window.clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  const dismissError = useCallback(() => {
    setErrorState(null);
  }, []);

  const showToast = useCallback((message: string, options?: { tone?: AppFeedbackToastTone }) => {
    if (toastTimeoutRef.current) {
      window.clearTimeout(toastTimeoutRef.current);
    }
    setToastState({ message, tone: options?.tone ?? "success" });
    toastTimeoutRef.current = window.setTimeout(() => {
      setToastState(null);
      toastTimeoutRef.current = null;
    }, TOAST_DISMISS_MS);
  }, []);

  const showSuccess = useCallback((message: string) => showToast(message, { tone: "success" }), [showToast]);

  const showError = useCallback(
    (message: string, options?: { title?: string }) => {
      setErrorState({
        message,
        title: options?.title?.trim() || "操作失败",
      });
    },
    [],
  );

  const value = useMemo<AppFeedbackContextValue>(
    () => ({
      dismissError,
      showError,
      showSuccess,
      showToast,
    }),
    [dismissError, showError, showSuccess, showToast],
  );

  return (
    <AppFeedbackContext.Provider value={value}>
      {children}
      {toastState ? (
        <div
          aria-live={toastState.tone === "error" ? "assertive" : "polite"}
          className="app-feedback-toast"
          data-tone={toastState.tone}
          role={toastState.tone === "error" ? "alert" : "status"}
        >
          {toastState.tone === "error" ? (
            <AlertTriangle aria-hidden="true" size={18} />
          ) : (
            <CheckCircle2 aria-hidden="true" size={18} />
          )}
          <span>{toastState.message}</span>
        </div>
      ) : null}
      {errorState ? (
        <div className="dialog-backdrop">
          <section
            aria-labelledby="app-feedback-error-title"
            aria-modal="true"
            className="confirm-dialog app-feedback-error-dialog"
            role="alertdialog"
          >
            <div className="dialog-icon danger">
              <AlertTriangle aria-hidden="true" size={18} />
            </div>
            <div className="dialog-content">
              <h2 id="app-feedback-error-title">{errorState.title}</h2>
              <p>{errorState.message}</p>
              <div className="dialog-actions">
                <Button onClick={dismissError} type="button" variant="primary">
                  知道了
                </Button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </AppFeedbackContext.Provider>
  );
}

export function useAppFeedback() {
  const context = useContext(AppFeedbackContext);
  if (!context) {
    throw new Error("useAppFeedback must be used within AppFeedbackProvider");
  }
  return context;
}
