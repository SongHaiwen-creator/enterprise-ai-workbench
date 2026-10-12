import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { KnowledgeAdmin } from "@/app/components/knowledge-admin";
import { ApiError, listKnowledgeBases } from "@/utils/api";
import * as api from "@/utils/knowledge-admin";

vi.mock("@/utils/api", async original => ({ ...await original<typeof import("@/utils/api")>(), listKnowledgeBases: vi.fn() }));
vi.mock("@/utils/knowledge-admin", async original => ({
  ...await original<typeof api>(), getKnowledgeBase: vi.fn(), listDocumentFamilies: vi.fn(),
  getDocumentFamily: vi.fn(), listDocumentVersions: vi.fn(), getDocument: vi.fn(),
  uploadDocumentVersion: vi.fn(), activateDocumentVersion: vi.fn(), indexDocument: vi.fn(),
}));
const time = "2026-10-11T00:00:00Z";
const base = { id: "kb", workspace_id: "a", name: "合成制度", status: "active" as const, description: null,
  created_by: "u", created_at: time, updated_at: time };
let family: api.DocumentFamily, versions: api.KnowledgeDocument[];
const props = { workspaceId: "a", accessToken: "token", role: "knowledge_admin" as const,
  onUnauthorized: vi.fn(), onPendingChange: vi.fn(), onBasesChange: vi.fn() };
function document(id: string, version: number): api.KnowledgeDocument {
  return { id, workspace_id: "a", knowledge_base_id: "kb", family_id: "f", file_name: `${id}.md`,
    file_type: "md", version, status: "ready", is_current: false, processing_error: null,
    content_sha256: "a".repeat(64), indexing: null, created_by: "u", created_at: time, updated_at: time };
}
const metadata = { chunk_count: 1, embedding_model: "text-embedding-3-small", embedding_dimensions: 1536, indexed_at: time };
function currentVersions() { return versions.map(v => ({ ...v, is_current: v.id === family.current_document_id })); }
const modal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
const close = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
});
afterAll(() => {
  if (modal) Object.defineProperty(HTMLDialogElement.prototype, "showModal", modal); else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  if (close) Object.defineProperty(HTMLDialogElement.prototype, "close", close); else Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});
beforeEach(() => {
  vi.resetAllMocks();
  family = { id: "f", workspace_id: "a", knowledge_base_id: "kb", display_name: "员工制度.md",
    current_document_id: "v1", revision: 5, created_by: "u", created_at: time, updated_at: time };
  versions = [{ ...document("v1", 1), indexing: metadata }];
  vi.mocked(listKnowledgeBases).mockResolvedValue([base]);
  vi.mocked(api.getKnowledgeBase).mockResolvedValue(base);
  vi.mocked(api.listDocumentFamilies).mockImplementation(async () => [{ ...family }]);
  vi.mocked(api.getDocumentFamily).mockImplementation(async () => ({ ...family }));
  vi.mocked(api.listDocumentVersions).mockImplementation(async () => currentVersions());
  vi.mocked(api.getDocument).mockImplementation(async (_w, _k, id) => currentVersions().find(v => v.id === id)!);
  vi.mocked(api.uploadDocumentVersion).mockImplementation(async () => {
    const next = document("v2", 2); versions.unshift(next); family.revision += 3; return next;
  });
  vi.mocked(api.indexDocument).mockImplementation(async (_w, _k, id) => {
    versions = versions.map(v => v.id === id ? { ...v, indexing: metadata } : v);
    family.revision += 1; return { document_id: id, ...metadata };
  });
  vi.mocked(api.activateDocumentVersion).mockImplementation(async (_w, _k, _f, id) => {
    family = { ...family, current_document_id: id, revision: family.revision + 1 }; return family;
  });
});
afterEach(cleanup);
async function mount() {
  const view = render(<KnowledgeAdmin {...props} />), user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "员工制度.md", exact: true }));
  await screen.findByRole("article", { name: "文档详情" }); return { ...view, user };
}
async function confirm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "确认继续" }));
}

it("prepares a replacement without switching, then confirms explicit activation and rollback", async () => {
  const { user } = await mount();
  expect(screen.getByText("已冻结索引")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成索引" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "上传替代版本", exact: true }));
  const file = new File(["Synthetic replacement"], "updated.md");
  await user.upload(screen.getByLabelText(/选择替代文件/), file);
  await user.click(screen.getByRole("button", { name: "上传并解析" }));
  await screen.findByText(/替代版本已解析/);
  await screen.findByRole("heading", { name: "v2.md", exact: true });
  expect(api.uploadDocumentVersion).toHaveBeenCalledWith("a", "kb", "f", file, "token");
  expect(api.activateDocumentVersion).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "激活此版本" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "生成索引" })); await confirm(user);
  await screen.findByRole("button", { name: "激活此版本" });
  await user.click(screen.getByRole("button", { name: "激活此版本" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("原当前版本 1");
  expect(screen.getByRole("dialog")).toHaveTextContent("v1.md");
  await user.click(screen.getByRole("button", { name: "取消", exact: true }));
  expect(api.activateDocumentVersion).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "激活此版本" })); await confirm(user);
  await screen.findByText("当前版本已切换。历史版本和引用保留。");
  expect(api.activateDocumentVersion).toHaveBeenCalledWith("a", "kb", "f", "v2", 9, "token");
  await waitFor(() => expect(screen.getByRole("button", { name: "v1.md · 版本 1" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "v1.md · 版本 1" }));
  await screen.findByRole("button", { name: "激活此版本" });
  await user.click(screen.getByRole("button", { name: "激活此版本" })); await confirm(user);
  expect(api.activateDocumentVersion).toHaveBeenLastCalledWith("a", "kb", "f", "v1", 10, "token");
});

it("refreshes a revision conflict without automatically replaying activation", async () => {
  versions.unshift({ ...document("v2", 2), indexing: metadata });
  vi.mocked(api.activateDocumentVersion).mockRejectedValue(new ApiError("Conflict", 409));
  const { user } = await mount();
  await user.click(screen.getByRole("button", { name: "v2.md · 版本 2" }));
  await screen.findByRole("button", { name: "激活此版本" });
  await user.click(screen.getByRole("button", { name: "激活此版本" })); await confirm(user);
  await screen.findByRole("alert");
  expect(api.activateDocumentVersion).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(api.listDocumentFamilies).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("button", { name: "激活此版本" })).not.toBeInTheDocument();
});

it("blocks duplicate submit and ignores an activation result after logout/unmount", async () => {
  versions.unshift({ ...document("v2", 2), indexing: metadata });
  let resolve!: (value: api.DocumentFamily) => void;
  vi.mocked(api.activateDocumentVersion).mockReturnValue(new Promise(yes => { resolve = yes; }));
  const { user, unmount } = await mount();
  await user.click(screen.getByRole("button", { name: "v2.md · 版本 2" }));
  await screen.findByRole("button", { name: "激活此版本" });
  await user.click(screen.getByRole("button", { name: "激活此版本" }));
  const button = screen.getByRole("button", { name: "确认继续" });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.activateDocumentVersion).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "员工制度.md", exact: true })).toBeDisabled();
  unmount(); props.onBasesChange.mockClear();
  await act(async () => resolve(family));
  expect(props.onBasesChange).not.toHaveBeenCalled();
});

it("does not display old family details after rapid workspace or role change", async () => {
  let resolve!: (value: api.DocumentFamily) => void;
  vi.mocked(api.getDocumentFamily).mockReturnValueOnce(new Promise(yes => { resolve = yes; }));
  const view = render(<KnowledgeAdmin {...props} />), user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "员工制度.md", exact: true }));
  view.rerender(<KnowledgeAdmin {...props} role={"employee"} />);
  await act(async () => resolve(family));
  expect(screen.queryByRole("article", { name: "文档详情" })).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("权限");
});

it("keeps index preparation failure separate from the active version", async () => {
  versions.unshift(document("v2", 2));
  vi.mocked(api.indexDocument).mockRejectedValue(new ApiError("Failure", 502));
  const { user } = await mount();
  await user.click(screen.getByRole("button", { name: "v2.md · 版本 2" }));
  await screen.findByText("尚未成功索引。");
  await user.click(screen.getByRole("button", { name: "生成索引" })); await confirm(user);
  await screen.findByRole("alert");
  expect(api.activateDocumentVersion).not.toHaveBeenCalled();
  expect(family.current_document_id).toBe("v1");
  expect(within(screen.getByRole("article", { name: "文档详情" })).queryByRole("button", { name: "激活此版本" })).not.toBeInTheDocument();
});
