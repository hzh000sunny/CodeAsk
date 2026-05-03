import type { FeedbackVerdict } from "../../types/api";

export function feedbackLabel(verdict: FeedbackVerdict) {
  if (verdict === "solved") {
    return "已解决";
  }
  if (verdict === "partial") {
    return "部分解决";
  }
  return "没解决";
}
