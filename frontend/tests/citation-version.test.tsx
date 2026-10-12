import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { CitationVersion } from "@/app/components/citation-version";
import { ApiError } from "@/utils/api";
import { getDocument, type KnowledgeDocument } from "@/utils/knowledge-admin";

vi.mock("@/utils/knowledge-admin", () => ({ getDocument: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const props = { workspaceId: "a", knowledgeBaseId: "kb", accessToken: "token", onUnauthorized: vi.fn(),
  citation: { family_id: "f", document_id: "v1", file_name: "policy.md", document_version: 1, chunk_id: "c1", chunk_index: 0, excerpt: "Original synthetic evidence" } };

it.each([[true, "ready", "当前版本"], [false, "ready", "历史版本"], [false, "disabled", "已禁用版本"]] as const)("reads only original version metadata for %s/%s", async (is_current, status, label) => {
  vi.mocked(getDocument).mockResolvedValue({ is_current, status } as KnowledgeDocument);
  render(<CitationVersion {...props} />);
  expect(getDocument).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "查看版本状态" }));
  await screen.findByText(new RegExp(label));
  expect(getDocument).toHaveBeenCalledWith("a", "kb", "v1", "token");
});

it("keeps unknown metadata failures separate from the citation and never retargets", async () => {
  vi.mocked(getDocument).mockRejectedValue(new ApiError("Unavailable", 404));
  render(<CitationVersion {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "查看版本状态" }));
  await screen.findByText(/已有摘录未被替换/);
  expect(getDocument).toHaveBeenCalledTimes(1);
  expect(props.citation.excerpt).toBe("Original synthetic evidence");
});

it("ignores late status from an old workspace, including an old 401", async () => {
  let reject!: (reason: unknown) => void;
  vi.mocked(getDocument).mockReturnValue(new Promise((_yes, no) => { reject = no; }));
  const view = render(<CitationVersion {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "查看版本状态" }));
  view.rerender(<CitationVersion {...props} workspaceId="b" />);
  await act(async () => reject(new ApiError("Old session", 401)));
  expect(props.onUnauthorized).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "查看版本状态" })).toBeEnabled();
});
