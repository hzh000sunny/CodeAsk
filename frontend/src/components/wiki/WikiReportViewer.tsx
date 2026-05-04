import { ShieldCheck } from "lucide-react";

import type { WikiReportDetailRead } from "../../types/wiki";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { Button } from "../ui/button";
import { copyTextToClipboard } from "../session/session-clipboard";

const REPORT_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  rejected: "未通过",
  verified: "已验证",
};

export function WikiReportViewer({
  report,
  onOpenFeaturePage,
}: {
  report: WikiReportDetailRead;
  onOpenFeaturePage: () => void;
}) {
  const statusLabel = REPORT_STATUS_LABELS[report.status] ?? report.status;

  return (
    <section className="wiki-reader wiki-report-viewer">
      <div className="page-header compact wiki-page-header">
        <div>
          <h1>{report.title}</h1>
          <p>
            {statusLabel}
            {report.verified_by ? ` · ${report.verified_by}` : ""}
          </p>
        </div>
        <div className="header-actions">
          <Button
            onClick={() => onOpenFeaturePage()}
            type="button"
            variant="secondary"
          >
            前往特性页
          </Button>
          <Button
            onClick={() => copyTextToClipboard(report.body_markdown)}
            type="button"
            variant="secondary"
          >
            复制正文
          </Button>
        </div>
      </div>
      <div className="wiki-reader-scroll">
        <div className="wiki-reader-body">
          <div className="wiki-report-status-row">
            <span className="badge">
              <ShieldCheck aria-hidden="true" size={13} />
              {statusLabel}
            </span>
          </div>
          <MarkdownRenderer
            content={report.body_markdown}
            onCopyCode={(code) => copyTextToClipboard(code)}
          />
        </div>
      </div>
    </section>
  );
}
