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
  brokenImageTargets?: Iterable<string>;
  headingIdPrefix?: string;
}

export function MarkdownRenderer({
  content,
  onCopyCode,
  imageSrcMap,
  linkHrefMap,
  brokenImageTargets,
  headingIdPrefix,
}: MarkdownRendererProps) {
  const brokenImages = brokenImageTargets ? new Set(brokenImageTargets) : null;
  const normalizedContent = normalizeMarkdownHtmlImages(content);
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1({ children }) {
            return (
              <MarkdownHeading level={1} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          h2({ children }) {
            return (
              <MarkdownHeading level={2} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          h3({ children }) {
            return (
              <MarkdownHeading level={3} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          h4({ children }) {
            return (
              <MarkdownHeading level={4} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          h5({ children }) {
            return (
              <MarkdownHeading level={5} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          h6({ children }) {
            return (
              <MarkdownHeading level={6} prefix={headingIdPrefix}>
                {children}
              </MarkdownHeading>
            );
          },
          a({ href, children }) {
            const nextHref = (href && linkHrefMap?.[href]) || href || "#";
            return <a href={nextHref}>{children}</a>;
          },
          img({ src, alt }) {
            const nextSrc = (src && imageSrcMap?.[src]) || src || "";
            const isBroken = Boolean(src && brokenImages?.has(src));
            return (
              <MarkdownImage
                alt={alt ?? ""}
                broken={isBroken}
                src={nextSrc}
                title={src ?? ""}
              />
            );
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
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

const HTML_IMAGE_SRC_RE = /<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;
const HTML_IMAGE_ALT_RE = /\balt\s*=\s*["']([^"']*)["']/i;

function normalizeMarkdownHtmlImages(content: string) {
  return content.replace(HTML_IMAGE_SRC_RE, (rawTag, src: string) => {
    const altMatch = rawTag.match(HTML_IMAGE_ALT_RE);
    const alt = escapeMarkdownImageAlt(altMatch?.[1] ?? "");
    return `![${alt}](<${src.trim()}>)`;
  });
}

function escapeMarkdownImageAlt(alt: string) {
  return alt.replace(/[[\]\\]/g, "\\$&");
}

function MarkdownHeading({
  children,
  level,
  prefix,
}: {
  children: ReactNode;
  level: 1 | 2 | 3 | 4 | 5 | 6;
  prefix?: string;
}) {
  const text = textFromNode(children).trim();
  const id = prefix && text ? buildMarkdownHeadingId(text, prefix) : undefined;
  const Tag = `h${level}` as const;
  return (
    <Tag data-heading-text={text || undefined} id={id}>
      {children}
    </Tag>
  );
}

function MarkdownImage({
  alt,
  broken,
  src,
  title,
}: {
  alt: string;
  broken: boolean;
  src: string;
  title: string;
}) {
  const [loadFailed, setLoadFailed] = useState(broken);

  useEffect(() => {
    setLoadFailed(broken);
  }, [broken, src]);

  if (loadFailed) {
    return (
      <span className="markdown-image-placeholder" role="img" aria-label={alt || title || "图片无法加载"}>
        <span>图片无法加载</span>
        {title ? <small>{title}</small> : null}
      </span>
    );
  }

  return (
    <img
      alt={alt}
      className="markdown-image"
      onError={() => setLoadFailed(true)}
      src={src}
    />
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

export function buildMarkdownHeadingId(text: string, prefix = "heading") {
  const normalized = text.trim().replace(/\s+/g, "-");
  return `${prefix}-${normalized || "section"}`;
}
