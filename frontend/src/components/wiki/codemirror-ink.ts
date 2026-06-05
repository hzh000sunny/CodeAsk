import { HighlightStyle } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

const MONO_STACK =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "CodeAsk Sans CJK", "Noto Sans CJK SC", "Microsoft YaHei", monospace';

// ink-and-paper 编辑器主题：透明底（露出纸面）、炭灰光标/选区静音、行号退成弱灰，
// 焦点环交给外层 .wiki-source-pane:focus-within，CM 自身不画轮廓。
export const inkEditorTheme = EditorView.theme(
  {
    "&": {
      color: "var(--text)",
      backgroundColor: "transparent",
      fontSize: "13.5px",
      height: "100%",
    },
    "&.cm-focused": {
      outline: "none",
    },
    ".cm-scroller": {
      overflow: "auto",
      fontFamily: MONO_STACK,
      lineHeight: "1.7",
    },
    ".cm-content": {
      padding: "14px 6px 40px",
      caretColor: "var(--text)",
    },
    ".cm-gutters": {
      backgroundColor: "transparent",
      color: "var(--muted)",
      border: "none",
    },
    ".cm-lineNumbers .cm-gutterElement": {
      padding: "0 8px 0 12px",
      fontSize: "11px",
      opacity: "0.55",
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(43, 47, 55, 0.035)",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "transparent",
      color: "var(--text)",
      opacity: "0.9",
    },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
      {
        backgroundColor: "var(--soft)",
      },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "var(--text)",
    },
    ".cm-matchingBracket, &.cm-focused .cm-matchingBracket": {
      backgroundColor: "rgba(43, 47, 55, 0.1)",
      outline: "none",
    },
  },
  { dark: false },
);

// 语法着色：层级靠字重/字号，不靠颜色铺满；唯一的彩色信号是链接的蓝。
// 标记符号（#、*、-、>、` 等）退成弱灰，让正文内容更突出。
export const inkHighlightStyle = HighlightStyle.define([
  { tag: [t.heading, t.heading1], color: "var(--text)", fontWeight: "700", fontSize: "1.22em" },
  { tag: t.heading2, color: "var(--text)", fontWeight: "700", fontSize: "1.12em" },
  { tag: t.heading3, color: "var(--text)", fontWeight: "700", fontSize: "1.04em" },
  {
    tag: [t.heading4, t.heading5, t.heading6],
    color: "var(--text)",
    fontWeight: "700",
  },
  { tag: t.strong, color: "var(--text)", fontWeight: "700" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: t.strikethrough, color: "var(--muted)", textDecoration: "line-through" },
  { tag: t.link, color: "var(--accent)" },
  { tag: t.url, color: "var(--accent)", textDecoration: "underline" },
  { tag: t.monospace, color: "#475467" },
  { tag: t.labelName, color: "var(--muted)" },
  { tag: [t.quote], color: "var(--muted)", fontStyle: "italic" },
  { tag: [t.list], color: "var(--muted)" },
  { tag: [t.contentSeparator], color: "var(--line-strong)" },
  { tag: [t.processingInstruction], color: "var(--muted)" },
]);
