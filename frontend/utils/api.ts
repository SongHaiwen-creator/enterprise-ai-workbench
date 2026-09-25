export type MembershipRole =
  | "employee"
  | "knowledge_admin"
  | "agent_admin"
  | "system_admin";

export type MembershipStatus = "invited" | "active" | "disabled";

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: 1800;
}

export interface CurrentUser {
  id: string;
  email: string;
  name: string;
  status: "active" | "disabled";
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  status: "active" | "disabled";
  created_at: string;
  updated_at: string;
}

export interface WorkspaceListItem {
  id: string;
  name: string;
  slug: string;
  status: "active" | "disabled";
  role: MembershipRole;
  joined_at: string | null;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  email: string;
  name: string;
  role: MembershipRole;
  status: MembershipStatus;
  joined_at: string | null;
}

export interface KnowledgeBase {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  status: "active" | "disabled";
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GroundedCitation {
  document_id: string;
  file_name: string;
  document_version: number;
  chunk_id: string;
  chunk_index: number;
  excerpt: string;
}

export interface GenerationMetadata {
  model: string;
  reasoning_effort: "low";
  retrieval_limit: 5;
  prompt_version: string;
  max_input_tokens: number;
  max_output_tokens: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface GroundedAnswerResponse {
  question: string;
  status: "answered" | "unsupported";
  answer: string | null;
  message: string | null;
  citations: GroundedCitation[];
  generation: GenerationMetadata;
}

export interface MembershipUpdate {
  role?: MembershipRole;
  status?: MembershipStatus;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
);

async function errorMessage(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;

  try {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
  } catch {
    return fallback;
  }

  return fallback;
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Unable to reach the Enterprise AI API.", 0);
  }

  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as T;
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentUser(accessToken: string): Promise<CurrentUser> {
  return requestJson<CurrentUser>("/api/auth/me", {}, accessToken);
}

export function listWorkspaces(accessToken: string): Promise<WorkspaceListItem[]> {
  return requestJson<WorkspaceListItem[]>("/api/workspaces", {}, accessToken);
}

export function getWorkspace(workspaceId: string, accessToken: string): Promise<Workspace> {
  return requestJson<Workspace>(`/api/workspaces/${workspaceId}`, {}, accessToken);
}

export function listWorkspaceMembers(
  workspaceId: string,
  accessToken: string,
): Promise<WorkspaceMember[]> {
  return requestJson<WorkspaceMember[]>(
    `/api/workspaces/${workspaceId}/members`,
    {},
    accessToken,
  );
}

export function createWorkspaceMember(
  workspaceId: string,
  payload: { user_id: string; role: MembershipRole },
  accessToken: string,
): Promise<unknown> {
  return requestJson(`/api/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify(payload),
  }, accessToken);
}

export function updateWorkspaceMember(
  workspaceId: string,
  membershipId: string,
  payload: MembershipUpdate,
  accessToken: string,
): Promise<unknown> {
  return requestJson(`/api/workspaces/${workspaceId}/members/${membershipId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }, accessToken);
}

export function listKnowledgeBases(
  workspaceId: string,
  accessToken: string,
): Promise<KnowledgeBase[]> {
  return requestJson<KnowledgeBase[]>(
    `/api/workspaces/${workspaceId}/knowledge-bases`,
    {},
    accessToken,
  );
}

export function answerKnowledgeQuestion(
  workspaceId: string,
  knowledgeBaseId: string,
  question: string,
  accessToken: string,
): Promise<GroundedAnswerResponse> {
  return requestJson<GroundedAnswerResponse>(
    `/api/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/answer`,
    {
      method: "POST",
      body: JSON.stringify({ question }),
    },
    accessToken,
  );
}
