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

type AppFeedbackContextValue = {
  dismissError: () => void;
  showError: (message: string, options?: { title?: string }) => void;
  showSuccess: (message: string) => void;
};

const AppFeedbackContext = createContext<AppFeedbackContextValue | null>(null);

export function AppFeedbackProvider({ children }: { children: ReactNode }) {
  const successTimeoutRef = useRef<number | null>(null);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorState, setErrorState] = useState<{
    message: string;
    title: string;
  } | null>(null);

  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        window.clearTimeout(successTimeoutRef.current);
      }
    };
  }, []);

  const dismissError = useCallback(() => {
    setErrorState(null);
  }, []);

  const showSuccess = useCallback((message: string) => {
    if (successTimeoutRef.current) {
      window.clearTimeout(successTimeoutRef.current);
    }
    setSuccessMessage(message);
    successTimeoutRef.current = window.setTimeout(() => {
      setSuccessMessage("");
      successTimeoutRef.current = null;
    }, 2400);
  }, []);

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
    }),
    [dismissError, showError, showSuccess],
  );

  return (
    <AppFeedbackContext.Provider value={value}>
      {children}
      {successMessage ? (
        <div aria-live="polite" className="app-feedback-toast" role="status">
          <CheckCircle2 aria-hidden="true" size={16} />
          <span>{successMessage}</span>
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
