import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { KnowledgeAdmin } from "@/app/components/knowledge-admin";
import { ApiError, type KnowledgeBase, type MembershipRole, listKnowledgeBases } from "@/utils/api";
import {
  type KnowledgeDocument, createKnowledgeBase, getDocument, getKnowledgeBase, indexDocument,
  listDocuments, updateDocumentStatus, updateKnowledgeBase, uploadDocument,
} from "@/utils/knowledge-admin";

vi.mock("@/utils/api", async importOriginal => ({ ...await importOriginal<typeof import("@/utils/api")>(), listKnowledgeBases: vi.fn() }));
vi.mock("@/utils/knowledge-admin", () => ({
  createKnowledgeBase: vi.fn(), getDocument: vi.fn(), getKnowledgeBase: vi.fn(), indexDocument: vi.fn(),
  listDocuments: vi.fn(), updateDocumentStatus: vi.fn(), updateKnowledgeBase: vi.fn(), uploadDocument: vi.fn(),
}));
const kb = (id = "kb-a", status: KnowledgeBase["status"] = "active"): KnowledgeBase => ({
  id, workspace_id: "w-a", name: id === "kb-a" ? "公司制度" : "其他制度", description: "原描述", status,
  created_by: "u", created_at: "2026-10-01T01:00:00Z", updated_at: "2026-10-01T01:00:00Z",
});
const doc = (status: KnowledgeDocument["status"] = "ready", id = "doc-a"): KnowledgeDocument => ({
  id, workspace_id: "w-a", knowledge_base_id: "kb-a", file_name: `${id}.md`, file_type: "md", status,
  version: 1, processing_error: status === "failed" ? "No extractable text" : null,
  created_by: "u", created_at: kb().created_at, updated_at: kb().updated_at,
});
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const onUnauthorized = vi.fn(), onPendingChange = vi.fn(), onBasesChange = vi.fn();
const props = { workspaceId: "w-a", accessToken: "token", role: "knowledge_admin" as MembershipRole, onUnauthorized, onPendingChange, onBasesChange };
async function mount() {
  const view = render(<KnowledgeAdmin {...props} />);
  await waitFor(() => expect(screen.getByLabelText("知识库名称")).toBeEnabled());
  await waitFor(() => expect(screen.getByRole("button", { name: "doc-a.md" })).toBeInTheDocument());
  return { ...view, user: userEvent.setup() };
}
async function openReady(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "doc-a.md" }));
  await screen.findByRole("article", { name: "文档详情" });
}
async function confirm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "确认继续" }));
}

const originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, writable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, writable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
});
afterAll(() => {
  if (originalShowModal) Object.defineProperty(HTMLDialogElement.prototype, "showModal", originalShowModal);
  else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, "close", originalClose);
  else Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listKnowledgeBases).mockResolvedValue([kb()]);
  vi.mocked(getKnowledgeBase).mockImplementation(async (_w, id) => kb(id));
  vi.mocked(listDocuments).mockResolvedValue([doc()]);
  vi.mocked(getDocument).mockImplementation(async (_w, _k, id) => doc("ready", id));
  vi.mocked(indexDocument).mockResolvedValue({ document_id: "doc-a", chunk_count: 3, embedding_model: "text-embedding-3-small", embedding_dimensions: 1536, indexed_at: kb().created_at });
  // jsdom does not implement the browser's modal focus/visibility behavior.
  vi.spyOn(HTMLDialogElement.prototype, "showModal").mockImplementation(function () { this.setAttribute("open", ""); });
  vi.spyOn(HTMLDialogElement.prototype, "close").mockImplementation(function () { this.removeAttribute("open"); });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Knowledge administration", () => {
  it.each(["employee", "agent_admin"] as MembershipRole[])("does not fetch or render management for %s", role => {
    render(<KnowledgeAdmin {...props} role={role} />);
    expect(screen.getByRole("alert")).toHaveTextContent("知识管理员");
    expect(listKnowledgeBases).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("选择文档")).not.toBeInTheDocument();
  });
  it.each(["knowledge_admin", "system_admin"] as MembershipRole[])("allows %s to read metadata and unknown indexing state", async role => {
    render(<KnowledgeAdmin {...props} role={role} />);
    const user = userEvent.setup(); await screen.findByRole("button", { name: "doc-a.md" });
    await openReady(user);
    expect(screen.getByText(/当前索引状态未提供/)).toBeInTheDocument();
    expect(screen.queryByText("已索引")).not.toBeInTheDocument();
    expect(indexDocument).not.toHaveBeenCalled();
  });
  it("supports empty knowledge bases and selects a newly created same-name base", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValueOnce([]).mockResolvedValue([kb()]);
    vi.mocked(createKnowledgeBase).mockResolvedValue(kb());
    render(<KnowledgeAdmin {...props} />); const user = userEvent.setup();
    await screen.findByText("暂无知识库，可先创建知识库。");
    await user.click(screen.getByRole("button", { name: "新建知识库" }));
    await user.type(screen.getByLabelText("知识库名称"), "  公司制度  ");
    await user.click(screen.getByRole("button", { name: "创建知识库" }));
    await screen.findByText("知识库已创建。");
    expect(createKnowledgeBase).toHaveBeenCalledWith("w-a", { name: "公司制度", description: null }, "token");
    expect(onBasesChange).toHaveBeenCalledWith([kb()]);
  });
  it("clears descriptions, sends only modified fields and avoids no-op PATCH", async () => {
    const { user } = await mount();
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    expect(updateKnowledgeBase).not.toHaveBeenCalled();
    vi.mocked(updateKnowledgeBase).mockResolvedValue({ ...kb(), description: null });
    await user.clear(screen.getByLabelText("知识库描述"));
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    await screen.findByText("知识库已保存。");
    expect(updateKnowledgeBase).toHaveBeenCalledWith("w-a", "kb-a", { description: null }, "token");
  });
  it.each(["   ", "a".repeat(256)])("validates an invalid trimmed name before mutation", async name => {
    const { user } = await mount();
    fireEvent.change(screen.getByLabelText("知识库名称"), { target: { value: name } });
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    expect(screen.getByRole("alert")).toHaveTextContent("1–255"); expect(updateKnowledgeBase).not.toHaveBeenCalled();
  });
  it("validates description bounds", async () => {
    const { user } = await mount();
    fireEvent.change(screen.getByLabelText("知识库描述"), { target: { value: "文".repeat(5001) } });
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    expect(screen.getByRole("alert")).toHaveTextContent("5000"); expect(updateKnowledgeBase).not.toHaveBeenCalled();
  });
  it("confirms disable and supports cancellation without a write", async () => {
    const { user } = await mount();
    await user.click(screen.getByRole("button", { name: "禁用知识库" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("不再参与新的知识检索和问答");
    await user.click(screen.getByRole("button", { name: "取消", exact: true }));
    expect(updateKnowledgeBase).not.toHaveBeenCalled();
    vi.mocked(updateKnowledgeBase).mockResolvedValue(kb("kb-a", "disabled"));
    vi.mocked(listKnowledgeBases).mockResolvedValue([kb("kb-a", "disabled")]);
    vi.mocked(getKnowledgeBase).mockResolvedValue(kb("kb-a", "disabled"));
    await user.click(screen.getByRole("button", { name: "禁用知识库" })); await confirm(user);
    await screen.findByText("知识库已禁用。");
    expect(updateKnowledgeBase).toHaveBeenCalledWith("w-a", "kb-a", { status: "disabled" }, "token");
  });
  it("disabled bases allow document toggles while upload/indexing are disabled", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue([kb("kb-a", "disabled")]);
    vi.mocked(getKnowledgeBase).mockResolvedValue(kb("kb-a", "disabled"));
    const { user } = await mount(); await openReady(user);
    expect(screen.getByLabelText("选择文档")).toBeDisabled();
    expect(screen.getByRole("button", { name: "索引 / 重新索引" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "禁用文档" })).toBeEnabled();
    vi.mocked(updateDocumentStatus).mockResolvedValue(doc("disabled"));
    await user.click(screen.getByRole("button", { name: "禁用文档" })); await confirm(user);
    await screen.findByText("文档已禁用。");
    expect(updateDocumentStatus).toHaveBeenCalledWith("w-a", "kb-a", "doc-a", "disabled", "token");
  });
  it("enables a disabled base without automatically indexing", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue([kb("kb-a", "disabled")]);
    vi.mocked(getKnowledgeBase).mockResolvedValue(kb("kb-a", "disabled"));
    vi.mocked(updateKnowledgeBase).mockResolvedValue(kb());
    const { user } = await mount(); await user.click(screen.getByRole("button", { name: "启用知识库" }));
    expect(updateKnowledgeBase).toHaveBeenCalledWith("w-a", "kb-a", { status: "active" }, "token");
    expect(indexDocument).not.toHaveBeenCalled();
  });
  it.each(["uploaded", "processing", "failed", "disabled"] as KnowledgeDocument["status"][])("only offers legal actions for %s", async status => {
    vi.mocked(getDocument).mockResolvedValue(doc(status));
    const { user } = await mount(); await openReady(user);
    const detail = within(screen.getByRole("article", { name: "文档详情" }));
    expect(detail.queryByRole("button", { name: "索引 / 重新索引" })).not.toBeInTheDocument();
    expect(detail.queryByRole("button", { name: "禁用文档" })).not.toBeInTheDocument();
    if (status === "disabled") {
      vi.mocked(updateDocumentStatus).mockResolvedValue(doc());
      await user.click(detail.getByRole("button", { name: "启用文档" }));
      expect(updateDocumentStatus).toHaveBeenCalledWith("w-a", "kb-a", "doc-a", "ready", "token");
      expect(indexDocument).not.toHaveBeenCalled();
    }
  });
  it.each(["policy.pdf", "policy.txt", "policy.MD"])("uploads %s without auto indexing", async filename => {
    const { user } = await mount(); const file = new File(["synthetic"], filename);
    vi.mocked(uploadDocument).mockResolvedValue(doc());
    await user.upload(screen.getByLabelText("选择文档"), file);
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await screen.findByText("上传并解析完成，可手动索引。");
    expect(uploadDocument).toHaveBeenCalledWith("w-a", "kb-a", file, "token");
    expect(indexDocument).not.toHaveBeenCalled();
  });
  it("keeps 201 failed visible with a separate-new-upload recovery", async () => {
    vi.mocked(uploadDocument).mockResolvedValue(doc("failed"));
    vi.mocked(listDocuments).mockResolvedValue([doc("failed")]);
    const { user } = await mount();
    await user.upload(screen.getByLabelText("选择文档"), new File(["bad"], "bad.pdf"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await screen.findByText(/文档已登记，解析失败/);
    expect(screen.getByText(/修正后重新选择文件上传/)).toBeInTheDocument();
    expect(indexDocument).not.toHaveBeenCalled(); expect(updateDocumentStatus).not.toHaveBeenCalled();
  });
  it.each([new File([], "empty.txt"), new File(["text"], "bad.exe"), new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.txt")])("rejects invalid local file $name", async file => {
    const { user } = await mount();
    fireEvent.change(screen.getByLabelText("选择文档"), { target: { files: [file] } });
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    expect(screen.getByRole("alert")).toHaveTextContent("10 MiB"); expect(uploadDocument).not.toHaveBeenCalled();
  });
  it("only indexes after confirmation and forgets the successful operation on re-entry", async () => {
    const { user, unmount } = await mount(); await openReady(user);
    await user.click(screen.getByRole("button", { name: "索引 / 重新索引" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("OpenAI"); expect(indexDocument).not.toHaveBeenCalled();
    await confirm(user); await screen.findByText("本次索引结果");
    expect(screen.getByText(/3 个片段/)).toBeInTheDocument();
    unmount(); await mount(); expect(screen.queryByText("本次索引结果")).not.toBeInTheDocument();
  });
  it.each([502, 503])("supports explicit indexing retry after %s without a status write", async status => {
    vi.mocked(indexDocument).mockRejectedValueOnce(new ApiError("Safe error", status));
    const { user } = await mount(); await openReady(user);
    await user.click(screen.getByRole("button", { name: "索引 / 重新索引" })); await confirm(user);
    await screen.findByRole("alert");
    expect(indexDocument).toHaveBeenCalledTimes(1); expect(updateDocumentStatus).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "索引 / 重新索引" })); await confirm(user);
    await screen.findByText("本次索引结果"); expect(indexDocument).toHaveBeenCalledTimes(2);
  });
  it.each([413, 415, 422, 0, 500])("keeps current file and input recoverable after upload error %s", async status => {
    vi.mocked(uploadDocument).mockRejectedValue(new ApiError("Safe error", status));
    const { user } = await mount(); const file = new File(["text"], "policy.txt");
    await user.upload(screen.getByLabelText("选择文档"), file);
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("选择文档")).toHaveProperty("files", expect.objectContaining({ 0: file }));
    expect(uploadDocument).toHaveBeenCalledTimes(1);
    if ([0, 500].includes(status)) expect(screen.getByRole("alert")).toHaveTextContent("服务端可能已完成");
  });
  it.each([401, 403])("clears confidential state after mutation %s", async status => {
    vi.mocked(uploadDocument).mockRejectedValue(new ApiError("Safe error", status));
    const { user } = await mount();
    await user.upload(screen.getByLabelText("选择文档"), new File(["text"], "policy.txt"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await waitFor(() => expect(screen.queryByLabelText("知识库名称")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "doc-a.md" })).not.toBeInTheDocument();
    expect(onBasesChange).toHaveBeenLastCalledWith(null);
    expect(onUnauthorized).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  });
  it.each([404, 409])("refreshes after %s without replaying mutation", async status => {
    vi.mocked(updateKnowledgeBase).mockRejectedValue(new ApiError("Safe error", status));
    const { user } = await mount(); await user.type(screen.getByLabelText("知识库名称"), "新");
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    await screen.findByRole("alert");
    await waitFor(() => expect(listKnowledgeBases).toHaveBeenCalledTimes(2));
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(1);
  });
  it("reports successful mutation and failed refresh separately, then GET refresh recovers", async () => {
    vi.mocked(updateKnowledgeBase).mockResolvedValue({ ...kb(), name: "更新制度" });
    const { user } = await mount();
    vi.mocked(listKnowledgeBases).mockRejectedValueOnce(new ApiError("Safe error", 500));
    await user.type(screen.getByLabelText("知识库名称"), "新"); await user.click(screen.getByRole("button", { name: "保存知识库" }));
    await screen.findByText(/操作已完成，列表刷新失败/);
    expect(screen.getByText("知识库已保存。")).toBeInTheDocument();
    expect(onBasesChange).toHaveBeenLastCalledWith(null);
    await user.click(screen.getByRole("button", { name: "刷新知识库（替换草稿）" }));
    await waitFor(() => expect(onBasesChange).toHaveBeenLastCalledWith([kb()]));
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(1);
  });
  it("serializes double submit and notifies shell pending while a write is unresolved", async () => {
    const pending = deferred<KnowledgeBase>(); vi.mocked(updateKnowledgeBase).mockReturnValue(pending.promise);
    const { user } = await mount(); await user.type(screen.getByLabelText("知识库名称"), "新");
    const form = screen.getByRole("button", { name: "保存知识库" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(1);
    expect(onPendingChange).toHaveBeenLastCalledWith(true);
    expect(screen.getByRole("button", { name: /公司制度 已启用/ })).toBeDisabled();
    await act(async () => pending.resolve(kb()));
    await waitFor(() => expect(onPendingChange).toHaveBeenLastCalledWith(false));
  });
  it("fences old KB document responses and late detail responses", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue([kb(), kb("kb-b")]);
    const slow = deferred<KnowledgeDocument[]>();
    vi.mocked(listDocuments).mockImplementation((_w, base) => base === "kb-a" ? slow.promise : Promise.resolve([doc("ready", "new-doc")]));
    render(<KnowledgeAdmin {...props} />); const user = userEvent.setup();
    await screen.findByRole("button", { name: /其他制度 已启用/ });
    await user.click(screen.getByRole("button", { name: /其他制度 已启用/ }));
    await screen.findByRole("button", { name: "new-doc.md" });
    await act(async () => slow.resolve([doc("ready", "old-secret")]));
    expect(screen.queryByText("old-secret.md")).not.toBeInTheDocument();
  });
  it("fences Workspace A -> B -> A reads and clears File/draft state", async () => {
    const slow = deferred<KnowledgeDocument[]>(); vi.mocked(listDocuments).mockReturnValueOnce(slow.promise);
    const view = render(<KnowledgeAdmin {...props} />);
    await waitFor(() => expect(listDocuments).toHaveBeenCalledTimes(1));
    view.rerender(<KnowledgeAdmin {...props} workspaceId="w-b" />);
    await waitFor(() => expect(listDocuments).toHaveBeenCalledTimes(2));
    view.rerender(<KnowledgeAdmin {...props} />);
    await waitFor(() => expect(listDocuments).toHaveBeenCalledTimes(3));
    await act(async () => slow.resolve([doc("ready", "stale-secret")]));
    expect(screen.queryByText("stale-secret.md")).not.toBeInTheDocument();
    expect(screen.getByLabelText("选择文档")).toHaveValue("");
  });
  it("does not emit result or cache callbacks from a mutation after unmount", async () => {
    const pending = deferred<KnowledgeDocument>(); vi.mocked(uploadDocument).mockReturnValue(pending.promise);
    const { user, unmount } = await mount();
    await user.upload(screen.getByLabelText("选择文档"), new File(["text"], "policy.txt"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    unmount(); onBasesChange.mockClear();
    await act(async () => pending.resolve(doc()));
    expect(onBasesChange).not.toHaveBeenCalled(); expect(listDocuments).toHaveBeenCalledTimes(1);
  });
  it("discards an older detail response after selecting another document", async () => {
    vi.mocked(listDocuments).mockResolvedValue([doc(), doc("ready", "doc-b")]);
    const slow = deferred<KnowledgeDocument>();
    vi.mocked(getDocument).mockReturnValueOnce(slow.promise).mockResolvedValue(doc("disabled", "doc-b"));
    const { user } = await mount();
    await user.click(screen.getByRole("button", { name: "doc-a.md" }));
    await user.click(screen.getByRole("button", { name: "doc-b.md" }));
    await screen.findByRole("button", { name: "启用文档" });
    await act(async () => slow.resolve(doc()));
    expect(within(screen.getByRole("article", { name: "文档详情" })).getByRole("heading")).toHaveTextContent("doc-b.md");
    expect(screen.queryByRole("button", { name: "禁用文档" })).not.toBeInTheDocument();
  });
  it("clears actual File and draft contents on a session change", async () => {
    const { user, rerender } = await mount();
    await user.clear(screen.getByLabelText("知识库名称")); await user.type(screen.getByLabelText("知识库名称"), "私密草稿");
    await user.upload(screen.getByLabelText("选择文档"), new File(["Synthetic"], "private.txt"));
    rerender(<KnowledgeAdmin {...props} accessToken="new-token" />);
    await waitFor(() => expect(screen.getByLabelText("知识库名称")).toHaveValue("公司制度"));
    expect(screen.getByLabelText("选择文档")).toHaveValue("");
    expect(screen.getByRole("button", { name: "上传并解析" })).toBeDisabled();
  });
  it("ignores an old list authorization failure after selecting a current library", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue([kb(), kb("kb-b")]);
    const { user } = await mount();
    const slow = deferred<KnowledgeBase[]>(); vi.mocked(listKnowledgeBases).mockReturnValueOnce(slow.promise);
    await user.click(screen.getByRole("button", { name: "刷新知识库（替换草稿）" }));
    await user.click(screen.getByRole("button", { name: /其他制度 已启用/ }));
    await waitFor(() => expect(screen.getByLabelText("知识库名称")).toHaveValue("其他制度"));
    await act(async () => slow.reject(new ApiError("Stale permission failure", 403)));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("知识库名称")).toHaveValue("其他制度");
    expect(screen.getByLabelText("知识库名称")).toBeEnabled();
  });
  it("supports retrying a failed initial list read without a write", async () => {
    vi.mocked(listKnowledgeBases).mockRejectedValueOnce(new ApiError("Unavailable", 500));
    render(<KnowledgeAdmin {...props} />); const user = userEvent.setup();
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "刷新知识库（替换草稿）" }));
    await screen.findByRole("button", { name: "doc-a.md" });
    expect(createKnowledgeBase).not.toHaveBeenCalled(); expect(updateKnowledgeBase).not.toHaveBeenCalled();
  });
  it("renders markup-like metadata as literal text", async () => {
    const marked = { ...kb(), name: "<script>alert(1)</script>", description: "<img src=x>" };
    vi.mocked(listKnowledgeBases).mockResolvedValue([marked]); vi.mocked(getKnowledgeBase).mockResolvedValue(marked);
    vi.mocked(listDocuments).mockResolvedValue([{ ...doc(), file_name: "<img onerror=x>.md" }]);
    render(<KnowledgeAdmin {...props} />); await screen.findByRole("button", { name: "<img onerror=x>.md" });
    expect(document.querySelector(".knowledge-admin script, .knowledge-admin img")).toBeNull();
    expect(screen.getByLabelText("知识库描述")).toHaveValue("<img src=x>");
  });
});
