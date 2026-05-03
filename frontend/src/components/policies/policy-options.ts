export const STAGE_OPTIONS = [
  { value: "all", label: "全流程" },
  { value: "scope_detection", label: "范围判断" },
  { value: "knowledge_retrieval", label: "知识检索" },
  { value: "sufficiency_judgement", label: "充分性判断" },
  { value: "code_investigation", label: "代码调查" },
  { value: "answer_finalization", label: "最终回答" },
  { value: "report_drafting", label: "报告生成" },
];

export function stageLabel(stage: string) {
  return STAGE_OPTIONS.find((option) => option.value === stage)?.label ?? stage;
}
