import { Textarea } from "../ui/textarea";

export function WikiSourceEditor({
  onChange,
  value,
}: {
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <section className="wiki-editor-pane">
      <div className="wiki-pane-heading">Markdown 源码</div>
      <Textarea
        className="wiki-source-editor"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </section>
  );
}
