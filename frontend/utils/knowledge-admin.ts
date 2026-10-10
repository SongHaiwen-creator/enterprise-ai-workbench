import { type KnowledgeBase, requestJson } from "./api";

export type KnowledgeBaseCreate = { name: string; description?: string | null };
export type KnowledgeBaseUpdate = Partial<KnowledgeBaseCreate> & { status?: KnowledgeBase["status"] };
export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed" | "disabled";
export type KnowledgeDocument = {
  id: string; workspace_id: string; knowledge_base_id: string;
  file_name: string; file_type: "pdf" | "txt" | "md"; status: DocumentStatus;
  version: number; processing_error: string | null; created_by: string;
  created_at: string; updated_at: string;
};
export type DocumentIndexResponse = {
  document_id: string; chunk_count: number; embedding_model: string;
  embedding_dimensions: number; indexed_at: string;
};

const root = (workspace: string) => `/api/workspaces/${workspace}/knowledge-bases`;
const documents = (workspace: string, base: string) => `${root(workspace)}/${base}/documents`;

export function getKnowledgeBase(workspace: string, base: string, token: string) {
  return requestJson<KnowledgeBase>(`${root(workspace)}/${base}`, {}, token);
}
export function createKnowledgeBase(workspace: string, payload: KnowledgeBaseCreate, token: string) {
  return requestJson<KnowledgeBase>(root(workspace), { method: "POST", body: JSON.stringify(payload) }, token);
}
export function updateKnowledgeBase(workspace: string, base: string, payload: KnowledgeBaseUpdate, token: string) {
  return requestJson<KnowledgeBase>(`${root(workspace)}/${base}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
}
export function listDocuments(workspace: string, base: string, token: string) {
  return requestJson<KnowledgeDocument[]>(documents(workspace, base), {}, token);
}
export function getDocument(workspace: string, base: string, document: string, token: string) {
  return requestJson<KnowledgeDocument>(`${documents(workspace, base)}/${document}`, {}, token);
}
export function uploadDocument(workspace: string, base: string, file: File, token: string) {
  const body = new FormData();
  body.append("file", file);
  return requestJson<KnowledgeDocument>(documents(workspace, base), { method: "POST", body }, token);
}
export function updateDocumentStatus(workspace: string, base: string, document: string, status: "ready" | "disabled", token: string) {
  return requestJson<KnowledgeDocument>(`${documents(workspace, base)}/${document}`, { method: "PATCH", body: JSON.stringify({ status }) }, token);
}
export function indexDocument(workspace: string, base: string, document: string, token: string) {
  return requestJson<DocumentIndexResponse>(`${documents(workspace, base)}/${document}/index`, { method: "POST" }, token);
}
