import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";
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
            const nextHref = lookupByTarget(linkHrefMap, href) ?? href ?? "#";
            return <a href={nextHref}>{children}</a>;
          },
          img({ src, alt }) {
            const nextSrc = lookupByTarget(imageSrcMap, src) ?? src ?? "";
            // 外部图片(http/https/data/协议相对)直接按原地址渲染：后端无法核验其可达性，
            // 旧文档里它们可能被误标 broken；真正加载失败交给 <img onError> 兜底。
            const isBroken =
              !isExternalUrl(src) && hasBrokenTarget(brokenImages, src);
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
            const language = getCodeLanguage(children);
            if (language === "mermaid") {
              return <MermaidDiagram chart={code} />;
            }
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

// react-markdown 会对 Markdown 里的 URL 做百分号编码，含中文/空格的相对路径会变成
// `%E5%9B%BE%E7%89%87/...`，而后端解析出的 ref.target 是未编码的原文（如 `图片/测试.png`）。
// 查表时按原值和解码后两种形态都试一次，避免编码差异导致命中失败、图片/内链失效。
function safeDecodeUri(value: string): string {
  try {
    return decodeURI(value);
  } catch {
    return value;
  }
}

// 带协议或协议相对的外部地址，永远不是 wiki 内部资源。
const EXTERNAL_URL_RE = /^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|\/\/)/;

function isExternalUrl(value: string | null | undefined): boolean {
  return Boolean(value && EXTERNAL_URL_RE.test(value.trim()));
}

function lookupByTarget(
  map: Record<string, string> | undefined,
  target: string | null | undefined,
): string | undefined {
  if (!map || !target) {
    return undefined;
  }
  if (map[target] !== undefined) {
    return map[target];
  }
  const decoded = safeDecodeUri(target);
  if (decoded !== target && map[decoded] !== undefined) {
    return map[decoded];
  }
  return undefined;
}

function hasBrokenTarget(
  broken: Set<string> | null,
  target: string | null | undefined,
): boolean {
  if (!broken || !target) {
    return false;
  }
  if (broken.has(target)) {
    return true;
  }
  const decoded = safeDecodeUri(target);
  return decoded !== target && broken.has(decoded);
}

let mermaidInitialized = false;
let mermaidModulePromise: Promise<typeof import("mermaid").default> | null = null;

async function loadMermaid() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import("mermaid").then((module) => module.default);
  }
  const mermaid = await mermaidModulePromise;
  if (mermaidInitialized) {
    return mermaid;
  }

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    themeVariables: {
      fontFamily:
        'Inter, "CodeAsk Sans CJK", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif',
      primaryColor: "#eef7ff",
      primaryTextColor: "#162033",
      primaryBorderColor: "#7bb1d9",
      lineColor: "#667085",
      secondaryColor: "#f6f8fb",
      tertiaryColor: "#fff7ed",
    },
  });
  mermaidInitialized = true;
  return mermaid;
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

function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [intrinsicWidth, setIntrinsicWidth] = useState<number | null>(null);
  const blockRef = useRef<HTMLDivElement | null>(null);
  const reactId = useId();
  const renderId = `codeask-mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`;

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      setSvg("");
      setError("");
      setIntrinsicWidth(null);
      try {
        const mermaid = await loadMermaid();
        const result = await mermaid.render(renderId, chart);
        if (!cancelled) {
          setSvg(result.svg);
          setIntrinsicWidth(readSvgViewBoxWidth(result.svg));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Mermaid 流程图渲染失败");
        }
      }
    }

    void renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [chart, renderId]);

  const displayWidth = intrinsicWidth ? Math.min(Math.max(intrinsicWidth, 720), 1200) : null;

  useEffect(() => {
    if (!svg || !blockRef.current) {
      return;
    }
    blockRef.current.scrollLeft = Math.max(
      0,
      (blockRef.current.scrollWidth - blockRef.current.clientWidth) / 2,
    );
  }, [svg, displayWidth]);

  if (error) {
    return (
      <div className="markdown-mermaid-block" data-state="error" ref={blockRef}>
        <div className="markdown-mermaid-error" role="alert">
          <strong>流程图渲染失败</strong>
          <span>{error}</span>
        </div>
        <pre>{chart}</pre>
      </div>
    );
  }

  return (
    <div
      className="markdown-mermaid-block"
      data-state={svg ? "ready" : "loading"}
      ref={blockRef}
    >
      {svg ? (
        <div
          className="markdown-mermaid-svg"
          dangerouslySetInnerHTML={{ __html: svg }}
          style={displayWidth ? { minWidth: `${displayWidth}px` } : undefined}
        />
      ) : (
        <div className="markdown-mermaid-loading" role="status">
          正在渲染流程图
        </div>
      )}
    </div>
  );
}

function readSvgViewBoxWidth(svg: string): number | null {
  const match = svg.match(/\bviewBox=["']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)/i);
  if (!match?.[1]) {
    return null;
  }
  const width = Number.parseFloat(match[1]);
  return Number.isFinite(width) && width > 0 ? Math.ceil(width) : null;
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

function getCodeLanguage(node: ReactNode): string {
  const className = findCodeClassName(node);
  const match = className.match(/(?:^|\s)language-([^\s]+)/);
  return match?.[1]?.toLowerCase() ?? "";
}

function findCodeClassName(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return "";
  }
  if (Array.isArray(node)) {
    return node.map(findCodeClassName).find(Boolean) ?? "";
  }
  if (typeof node === "object" && "props" in node) {
    const props = node.props as { children?: ReactNode; className?: unknown };
    if (typeof props.className === "string") {
      return props.className;
    }
    return findCodeClassName(props.children);
  }
  return "";
}

export function buildMarkdownHeadingId(text: string, prefix = "heading") {
  const normalized = text.trim().replace(/\s+/g, "-");
  return `${prefix}-${normalized || "section"}`;
}
