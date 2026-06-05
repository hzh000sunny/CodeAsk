export interface WikiTocHeading {
  id: string;
  text: string;
  level: number;
}

export function WikiTableOfContents({
  activeId,
  headings,
  minLevel,
  onSelect,
}: {
  activeId: string | null;
  headings: WikiTocHeading[];
  minLevel: number;
  onSelect: (id: string) => void;
}) {
  return (
    <aside aria-label="文档大纲" className="wiki-reader-toc">
      <div className="wiki-reader-toc-title">目录</div>
      <nav className="wiki-reader-toc-list">
        {headings.map((heading) => (
          <button
            className="wiki-reader-toc-link"
            data-active={heading.id === activeId || undefined}
            // 相对最浅标题缩进，最多三级，避免深层目录把侧栏推得太宽。
            data-indent={Math.min(heading.level - minLevel, 2)}
            key={heading.id}
            onClick={() => onSelect(heading.id)}
            title={heading.text}
            type="button"
          >
            {heading.text}
          </button>
        ))}
      </nav>
    </aside>
  );
}
