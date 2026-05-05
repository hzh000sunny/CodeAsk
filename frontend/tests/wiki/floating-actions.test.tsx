import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { WikiFloatingActions } from "../../src/components/wiki/WikiFloatingActions";

describe("WikiFloatingActions", () => {
  it("keeps the primary actions visible and folds secondary actions into more", () => {
    const onCopyLink = vi.fn();
    const onEdit = vi.fn();
    const onOpenDetail = vi.fn();
    const onOpenHistory = vi.fn();
    const onOpenImport = vi.fn();

    render(
      <WikiFloatingActions
        canEdit
        onCopyLink={onCopyLink}
        onEdit={onEdit}
        onOpenDetail={onOpenDetail}
        onOpenHistory={onOpenHistory}
        onOpenImport={onOpenImport}
      />,
    );

    expect(screen.getByRole("button", { name: "详情" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制链接" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "编辑" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更多" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "历史版本" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导入" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "更多" }));

    fireEvent.click(screen.getByRole("menuitem", { name: "历史版本" }));
    expect(onOpenHistory).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "导入" }));
    expect(onOpenImport).toHaveBeenCalledTimes(1);
  });
});
