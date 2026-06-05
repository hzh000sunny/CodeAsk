import type { RefObject } from "react";
import {
  Bold,
  Code,
  Heading,
  Italic,
  Link2,
  List,
  ListOrdered,
  Quote,
  SquareCode,
} from "lucide-react";
import { EditorSelection, type ChangeSpec } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";

// 在选区两侧包裹标记（如 ** **）；无选区时插入标记并把光标停在中间。
function wrapSelection(view: EditorView, mark: string, markEnd = mark) {
  view.dispatch(
    view.state.changeByRange((range) => {
      const text = view.state.sliceDoc(range.from, range.to);
      const insert = `${mark}${text}${markEnd}`;
      const anchor = range.from + mark.length;
      return {
        changes: { from: range.from, to: range.to, insert },
        range: EditorSelection.range(anchor, anchor + text.length),
      };
    }),
  );
  view.focus();
}

// 给选区覆盖的每一行加前缀（标题/列表/引用）。
function prefixLines(view: EditorView, prefix: string) {
  const { state } = view;
  const startLine = state.doc.lineAt(state.selection.main.from);
  const endLine = state.doc.lineAt(state.selection.main.to);
  const changes: ChangeSpec[] = [];
  for (let line = startLine.number; line <= endLine.number; line += 1) {
    changes.push({ from: state.doc.line(line).from, insert: prefix });
  }
  view.dispatch({ changes });
  view.focus();
}

function insertLink(view: EditorView) {
  view.dispatch(
    view.state.changeByRange((range) => {
      const text = view.state.sliceDoc(range.from, range.to) || "链接文字";
      const insert = `[${text}](url)`;
      const urlFrom = range.from + 1 + text.length + 2;
      return {
        changes: { from: range.from, to: range.to, insert },
        range: EditorSelection.range(urlFrom, urlFrom + 3),
      };
    }),
  );
  view.focus();
}

function insertCodeBlock(view: EditorView) {
  view.dispatch(
    view.state.changeByRange((range) => {
      const text = view.state.sliceDoc(range.from, range.to);
      const insert = `\`\`\`\n${text}\n\`\`\``;
      const anchor = range.from + 4;
      return {
        changes: { from: range.from, to: range.to, insert },
        range: EditorSelection.range(anchor, anchor + text.length),
      };
    }),
  );
  view.focus();
}

type ToolAction = {
  icon: typeof Bold;
  label: string;
  run: (view: EditorView) => void;
};

const ACTIONS: ToolAction[][] = [
  [
    { icon: Bold, label: "加粗", run: (v) => wrapSelection(v, "**") },
    { icon: Italic, label: "斜体", run: (v) => wrapSelection(v, "*") },
    { icon: Code, label: "行内代码", run: (v) => wrapSelection(v, "`") },
  ],
  [
    { icon: Heading, label: "标题", run: (v) => prefixLines(v, "## ") },
    { icon: List, label: "无序列表", run: (v) => prefixLines(v, "- ") },
    { icon: ListOrdered, label: "有序列表", run: (v) => prefixLines(v, "1. ") },
    { icon: Quote, label: "引用", run: (v) => prefixLines(v, "> ") },
  ],
  [
    { icon: Link2, label: "链接", run: insertLink },
    { icon: SquareCode, label: "代码块", run: insertCodeBlock },
  ],
];

export function WikiEditorToolbar({
  editorViewRef,
}: {
  editorViewRef: RefObject<EditorView | null>;
}) {
  function handle(run: (view: EditorView) => void) {
    const view = editorViewRef.current;
    if (view) {
      run(view);
    }
  }

  return (
    <div className="wiki-editor-toolbar" role="toolbar" aria-label="Markdown 格式">
      {ACTIONS.map((group, groupIndex) => (
        <div className="wiki-editor-toolbar-group" key={groupIndex}>
          {group.map((action) => {
            const Icon = action.icon;
            return (
              <button
                aria-label={action.label}
                className="wiki-editor-tool"
                key={action.label}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => handle(action.run)}
                title={action.label}
                type="button"
              >
                <Icon aria-hidden="true" size={15} strokeWidth={1.9} />
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
