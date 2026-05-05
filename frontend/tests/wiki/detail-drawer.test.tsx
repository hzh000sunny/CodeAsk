import { render, screen } from "@testing-library/react";

import { WikiDetailDrawer } from "../../src/components/wiki/WikiDetailDrawer";

describe("WikiDetailDrawer", () => {
  it("renders readable provenance summary fields instead of exposing raw JSON only", () => {
    render(
      <WikiDetailDrawer
        document={{
          document_id: 10,
          node_id: 20,
          title: "Payment Runbook",
          current_version_id: 3,
          current_body_markdown: "# Payment Runbook",
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: {
            source: "directory_import",
            source_id: 7,
          },
          provenance_summary: {
            source: "directory_import",
            source_label: "目录导入",
            source_display_name: "Payment Runbooks",
            source_path: "runbooks/payment.md",
            source_uri: "file:///srv/wiki/payment",
            import_session_id: 301,
          },
          permissions: { read: true, write: true, admin: false },
        }}
        onClose={() => {}}
        open
        path="knowledge-base/payment-runbook"
        updatedAt="2026-05-05T09:00:00"
      />,
    );

    expect(screen.getByText("来源类型")).toBeInTheDocument();
    expect(screen.getByText("目录导入")).toBeInTheDocument();
    expect(screen.getByText("来源名称")).toBeInTheDocument();
    expect(screen.getByText("Payment Runbooks")).toBeInTheDocument();
    expect(screen.getByText("源相对路径")).toBeInTheDocument();
    expect(screen.getByText("runbooks/payment.md")).toBeInTheDocument();
    expect(screen.getByText("来源 URI")).toBeInTheDocument();
    expect(screen.getByText("file:///srv/wiki/payment")).toBeInTheDocument();
    expect(screen.getByText("导入会话")).toBeInTheDocument();
    expect(screen.getByText("301")).toBeInTheDocument();
  });
});
