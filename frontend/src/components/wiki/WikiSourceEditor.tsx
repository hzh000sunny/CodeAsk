import { useEffect, useMemo, useRef, type RefObject } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";

import { inkEditorTheme, inkHighlightStyle } from "./codemirror-ink";
import { WikiEditorToolbar } from "./WikiEditorToolbar";

export function WikiSourceEditor({
  editorViewRef,
  onChange,
  onScroll,
  value,
}: {
  editorViewRef: RefObject<EditorView | null>;
  onChange: (value: string) => void;
  onScroll?: () => void;
  value: string;
}) {
  // onScroll 经 ref 透传，让 CM 扩展与滚动监听保持稳定、不随渲染重建。
  const onScrollRef = useRef(onScroll);
  useEffect(() => {
    onScrollRef.current = onScroll;
  }, [onScroll]);

  const chars = value.length;
  const lines = value.length === 0 ? 0 : value.split("\n").length;

  const extensions = useMemo(
    () => [
      markdown({ base: markdownLanguage }),
      EditorView.lineWrapping,
      syntaxHighlighting(inkHighlightStyle),
      inkEditorTheme,
    ],
    [],
  );

  return (
    <section className="wiki-editor-pane wiki-source-pane">
      <div className="wiki-pane-heading">
        <span className="wiki-pane-heading-label">Markdown 源码</span>
        <span className="wiki-pane-heading-meta">
          {chars} 字 · {lines} 行
        </span>
      </div>
      <WikiEditorToolbar editorViewRef={editorViewRef} />
      <CodeMirror
        basicSetup={{
          foldGutter: false,
          highlightActiveLine: true,
          highlightActiveLineGutter: true,
          lineNumbers: true,
        }}
        className="wiki-source-editor"
        extensions={extensions}
        onChange={onChange}
        onCreateEditor={(view) => {
          editorViewRef.current = view;
          view.scrollDOM.addEventListener(
            "scroll",
            () => {
              onScrollRef.current?.();
            },
            { passive: true },
          );
        }}
        placeholder="在此用 Markdown 撰写文档…"
        value={value}
      />
    </section>
  );
}
