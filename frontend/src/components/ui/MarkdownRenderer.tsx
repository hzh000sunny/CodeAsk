import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
  onCopyCode?: (code: string) => Promise<void> | void;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
}

export function MarkdownRenderer({
  content,
  onCopyCode,
  imageSrcMap,
  linkHrefMap,
}: MarkdownRendererProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const nextHref = (href && linkHrefMap?.[href]) || href || "#";
            return <a href={nextHref}>{children}</a>;
          },
          img({ src, alt }) {
            const nextSrc = (src && imageSrcMap?.[src]) || src || "";
            return <img alt={alt ?? ""} className="markdown-image" src={nextSrc} />;
          },
          pre({ children }) {
            const code = textFromNode(children).replace(/\n$/, "");
            return (
              <MarkdownCodeBlock code={code} onCopyCode={onCopyCode}>
                {children}
              </MarkdownCodeBlock>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function MarkdownCodeBlock({
  children,
  code,
  onCopyCode,
}: {
  children: ReactNode;
  code: string;
  onCopyCode?: (code: string) => Promise<void> | void;
}) {
  const timeoutRef = useRef<number | null>(null);
  const [copyStatus, setCopyStatus] = useState("");

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  function showCopyStatus(label: string) {
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    setCopyStatus(label);
    timeoutRef.current = window.setTimeout(() => {
      setCopyStatus("");
      timeoutRef.current = null;
    }, 1200);
  }

  async function copyCode() {
    try {
      await onCopyCode?.(code);
      showCopyStatus("已复制");
    } catch {
      showCopyStatus("复制失败");
    }
  }

  return (
    <div className="markdown-code-block">
      {onCopyCode ? (
        <div className="markdown-code-toolbar">
          <button
            aria-label="复制代码块"
            className="markdown-code-copy"
            onClick={() => void copyCode()}
            title="复制代码"
            type="button"
          >
            <Copy aria-hidden="true" size={14} />
          </button>
          {copyStatus ? (
            <span className="markdown-copy-toast" role="status">
              {copyStatus}
            </span>
          ) : null}
        </div>
      ) : null}
      <pre>{children}</pre>
    </div>
  );
}

function textFromNode(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return "";
  }
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(textFromNode).join("");
  }
  if (typeof node === "object" && "props" in node) {
    const props = node.props as { children?: ReactNode };
    return textFromNode(props.children);
  }
  return "";
}
