"use client";

import { FormEvent, useState } from "react";

import { KnowledgeQA } from "@/app/components/knowledge-qa";

import {
  ApiError,
  CurrentUser,
  KnowledgeBase,
  MembershipRole,
  MembershipStatus,
  Workspace,
  WorkspaceListItem,
  WorkspaceMember,
  createWorkspaceMember,
  getCurrentUser,
  getWorkspace,
  listKnowledgeBases,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  updateWorkspaceMember,
} from "@/utils/api";
import { formatEnumLabel, formatJoinedAt, initials } from "@/utils/presentation";

const ROLES: MembershipRole[] = [
  "employee",
  "knowledge_admin",
  "agent_admin",
  "system_admin",
];

const STATUSES: MembershipStatus[] = ["invited", "active", "disabled"];

type Notice = { tone: "success" | "error"; message: string } | null;
type ProductArea = "knowledge-qa" | "workspace";

export default function Home() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceListItem[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [knowledgeBasesError, setKnowledgeBasesError] = useState<string | null>(null);
  const [productArea, setProductArea] = useState<ProductArea>("knowledge-qa");
  const [qaPending, setQaPending] = useState(false);
  const [loginPending, setLoginPending] = useState(false);
  const [workspacePending, setWorkspacePending] = useState(false);
  const [memberPending, setMemberPending] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [newMemberId, setNewMemberId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<MembershipRole>("employee");

  const selectedWorkspace =
    workspaces.find((item) => item.id === selectedWorkspaceId) ?? null;
  const isAdministrator = selectedWorkspace?.role === "system_admin";

  function clearSession(message?: string) {
    setAccessToken(null);
    setCurrentUser(null);
    setWorkspaces([]);
    setSelectedWorkspaceId(null);
    setWorkspace(null);
    setMembers([]);
    setKnowledgeBases([]);
    setKnowledgeBasesError(null);
    setQaPending(false);
    setPassword("");
    setNotice(null);
    setLoginError(message ?? null);
  }

  function handleApiError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) {
      clearSession("Your session expired. Sign in again to continue.");
      return;
    }

    setNotice({
      tone: "error",
      message: error instanceof ApiError ? error.message : fallback,
    });
  }

  async function selectWorkspace(item: WorkspaceListItem, token: string) {
    setSelectedWorkspaceId(item.id);
    setWorkspace(null);
    setMembers([]);
    setKnowledgeBases([]);
    setKnowledgeBasesError(null);
    setNotice(null);
    setWorkspacePending(true);

    try {
      const [workspaceResult, memberResult] = await Promise.all([
        getWorkspace(item.id, token),
        item.role === "system_admin"
          ? listWorkspaceMembers(item.id, token)
          : Promise.resolve([]),
      ]);
      setWorkspace(workspaceResult);
      setMembers(memberResult);

      try {
        setKnowledgeBases(await listKnowledgeBases(item.id, token));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearSession("Your session expired. Sign in again to continue.");
          return;
        }
        setKnowledgeBasesError(
          error instanceof ApiError
            ? error.message
            : "We could not load knowledge bases for this workspace.",
        );
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession("Your session expired. Sign in again to continue.");
      } else {
        const message =
          error instanceof ApiError ? error.message : "We could not load this workspace.";
        setNotice({ tone: "error", message });
      }
    } finally {
      setWorkspacePending(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginPending(true);
    setLoginError(null);

    try {
      const session = await login(email, password);
      const [userResult, workspaceResult] = await Promise.all([
        getCurrentUser(session.access_token),
        listWorkspaces(session.access_token),
      ]);

      setAccessToken(session.access_token);
      setCurrentUser(userResult);
      setWorkspaces(workspaceResult);
      setPassword("");

      if (workspaceResult.length > 0) {
        await selectWorkspace(workspaceResult[0], session.access_token);
      }
    } catch (error) {
      clearSession();
      setLoginError(
        error instanceof ApiError ? error.message : "We could not sign you in.",
      );
    } finally {
      setLoginPending(false);
    }
  }

  async function refreshMembers(token: string, workspaceId: string) {
    const memberResult = await listWorkspaceMembers(workspaceId, token);
    setMembers(memberResult);
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !selectedWorkspaceId) return;

    setMemberPending("new");
    setNotice(null);
    try {
      await createWorkspaceMember(
        selectedWorkspaceId,
        { user_id: newMemberId.trim(), role: newMemberRole },
        accessToken,
      );
      await refreshMembers(accessToken, selectedWorkspaceId);
      setNewMemberId("");
      setNewMemberRole("employee");
      setNotice({ tone: "success", message: "Member added as invited." });
    } catch (error) {
      handleApiError(error, "We could not add this member.");
    } finally {
      setMemberPending(null);
    }
  }

  async function handleMemberUpdate(
    member: WorkspaceMember,
    update: { role?: MembershipRole; status?: MembershipStatus },
  ) {
    if (!accessToken || !selectedWorkspaceId) return;

    setMemberPending(member.id);
    setNotice(null);
    try {
      await updateWorkspaceMember(selectedWorkspaceId, member.id, update, accessToken);
      await refreshMembers(accessToken, selectedWorkspaceId);
      setNotice({ tone: "success", message: `${member.name}'s access was updated.` });
    } catch (error) {
      handleApiError(error, "We could not update this member.");
    } finally {
      setMemberPending(null);
    }
  }

  if (!accessToken || !currentUser) {
    return (
      <main className="login-shell">
        <section className="brand-panel" aria-labelledby="brand-title">
          <div className="brand-mark" aria-hidden="true">EA</div>
          <div>
            <p className="eyebrow">Enterprise AI Workbench</p>
            <h1 id="brand-title">One secure place for enterprise AI.</h1>
            <p className="brand-summary">
              Enter your workspace to manage access today—and build trusted AI
              capabilities tomorrow.
            </p>
          </div>
          <div className="trust-note">
            <span aria-hidden="true">●</span>
            Workspace-scoped access
          </div>
        </section>

        <section className="login-panel" aria-labelledby="login-title">
          <div className="login-card">
            <p className="section-kicker">Welcome back</p>
            <h2 id="login-title">Sign in to continue</h2>
            <p className="muted">Use the account provisioned by your administrator.</p>

            <form className="stack-form" onSubmit={handleLogin}>
              <label htmlFor="email">Work email</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />

              {loginError && (
                <p className="form-message error-message" role="alert">
                  {loginError}
                </p>
              )}

              <button className="primary-button" type="submit" disabled={loginPending}>
                {loginPending ? "Signing in…" : "Sign in"}
              </button>
            </form>
            <p className="privacy-note">Your session stays in this browser tab only.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="workspace-shell">
      <aside className="sidebar">
        <div className="product-lockup">
          <div className="brand-mark compact" aria-hidden="true">EA</div>
          <div>
            <strong>Enterprise AI</strong>
            <span>Workbench</span>
          </div>
        </div>

        <div className="sidebar-heading">
          <p className="eyebrow">Your workspaces</p>
          <span>{workspaces.length}</span>
        </div>

        <nav className="workspace-list" aria-label="Workspace selection">
          {workspaces.map((item) => (
            <button
              className={item.id === selectedWorkspaceId ? "workspace-link active" : "workspace-link"}
              key={item.id}
              type="button"
              onClick={() => void selectWorkspace(item, accessToken)}
              disabled={qaPending}
              aria-current={item.id === selectedWorkspaceId ? "page" : undefined}
            >
              <span className="workspace-avatar" aria-hidden="true">{initials(item.name)}</span>
              <span className="workspace-link-copy">
                <strong>{item.name}</strong>
                <small>{formatEnumLabel(item.role)}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="product-nav-heading">
          <p className="eyebrow">Product</p>
        </div>
        <nav className="product-nav" aria-label="Product navigation">
          <button
            type="button"
            className={productArea === "knowledge-qa" ? "product-link active" : "product-link"}
            onClick={() => setProductArea("knowledge-qa")}
            disabled={qaPending}
            aria-current={productArea === "knowledge-qa" ? "page" : undefined}
          >
            <span className="product-icon" aria-hidden="true">✦</span>
            <span><strong>Knowledge Q&A</strong><small>Grounded answers</small></span>
          </button>
          <button
            type="button"
            className={productArea === "workspace" ? "product-link active" : "product-link"}
            onClick={() => setProductArea("workspace")}
            disabled={qaPending}
            aria-current={productArea === "workspace" ? "page" : undefined}
          >
            <span className="product-icon" aria-hidden="true">⌂</span>
            <span><strong>Workspace</strong><small>Access & members</small></span>
          </button>
        </nav>

        <div className="sidebar-user">
          <span className="user-avatar" aria-hidden="true">{initials(currentUser.name)}</span>
          <span>
            <strong>{currentUser.name}</strong>
            <small>{currentUser.email}</small>
          </span>
          <button className="text-button" type="button" onClick={() => clearSession()}>
            Sign out
          </button>
        </div>
      </aside>

      <section className="content-shell">
        <header className="topbar">
          <div>
            <p className="section-kicker">
              {productArea === "knowledge-qa" ? "Workspace / Knowledge Base" : "Workspace administration"}
            </p>
            <h1>{productArea === "knowledge-qa" ? "Knowledge Q&A" : selectedWorkspace?.name ?? "Workspaces"}</h1>
            {productArea === "knowledge-qa" && selectedWorkspace && (
              <p className="topbar-context">{selectedWorkspace.name}</p>
            )}
          </div>
          {selectedWorkspace && (
            <span className="role-badge">{formatEnumLabel(selectedWorkspace.role)}</span>
          )}
        </header>

        <div className="content">
          {notice && (
            <p
              className={`notice ${notice.tone === "success" ? "success-notice" : "error-notice"}`}
              role={notice.tone === "error" ? "alert" : "status"}
            >
              {notice.message}
            </p>
          )}

          {workspaces.length === 0 ? (
            <section className="empty-state">
              <div className="empty-icon" aria-hidden="true">◇</div>
              <h2>No active workspaces</h2>
              <p>
                Your account does not have an active workspace membership. Ask a
                system administrator to grant access.
              </p>
            </section>
          ) : workspacePending ? (
            <section className="loading-card" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              Loading workspace…
            </section>
          ) : workspace && selectedWorkspace && productArea === "knowledge-qa" ? (
            <KnowledgeQA
              key={workspace.id}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              knowledgeBases={knowledgeBases}
              knowledgeBasesPending={workspacePending}
              knowledgeBasesError={knowledgeBasesError}
              accessToken={accessToken}
              onUnauthorized={() => clearSession("Your session expired. Sign in again to continue.")}
              onPendingChange={setQaPending}
            />
          ) : workspace && selectedWorkspace ? (
            <>
              <section className="overview-grid" aria-label="Workspace overview">
                <article className="overview-card primary-overview">
                  <p className="section-kicker">Workspace</p>
                  <h2>{workspace.name}</h2>
                  <p className="workspace-slug">/{workspace.slug}</p>
                  <span className="status-pill active-status">
                    <span aria-hidden="true" />
                    {formatEnumLabel(workspace.status)}
                  </span>
                </article>
                <article className="overview-card">
                  <p className="section-kicker">Your access</p>
                  <h2>{formatEnumLabel(selectedWorkspace.role)}</h2>
                  <p className="muted">
                    Joined {formatJoinedAt(selectedWorkspace.joined_at)}
                  </p>
                </article>
                <article className="overview-card">
                  <p className="section-kicker">Members</p>
                  <h2>{isAdministrator ? members.length : "—"}</h2>
                  <p className="muted">
                    {isAdministrator ? "Visible to administrators" : "Administrator access required"}
                  </p>
                </article>
              </section>

              {isAdministrator ? (
                <section className="members-section" aria-labelledby="members-title">
                  <div className="section-heading">
                    <div>
                      <p className="section-kicker">Access control</p>
                      <h2 id="members-title">Workspace members</h2>
                      <p className="muted">Manage roles and membership status for this workspace.</p>
                    </div>
                  </div>

                  <form className="add-member-form" onSubmit={handleAddMember}>
                    <div className="field-group grow-field">
                      <label htmlFor="new-member-id">Existing user UUID</label>
                      <input
                        id="new-member-id"
                        value={newMemberId}
                        onChange={(event) => setNewMemberId(event.target.value)}
                        placeholder="00000000-0000-0000-0000-000000000000"
                        pattern="[0-9a-fA-F-]{36}"
                        required
                      />
                    </div>
                    <div className="field-group">
                      <label htmlFor="new-member-role">Role</label>
                      <select
                        id="new-member-role"
                        value={newMemberRole}
                        onChange={(event) => setNewMemberRole(event.target.value as MembershipRole)}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>{formatEnumLabel(role)}</option>
                        ))}
                      </select>
                    </div>
                    <button className="primary-button compact-button" type="submit" disabled={memberPending === "new"}>
                      {memberPending === "new" ? "Adding…" : "Add member"}
                    </button>
                  </form>

                  <div className="member-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Member</th>
                          <th scope="col">Role</th>
                          <th scope="col">Status</th>
                          <th scope="col">Joined</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.map((member) => {
                          const isPending = memberPending === member.id;
                          return (
                            <tr key={member.id}>
                              <td>
                                <div className="member-identity">
                                  <span className="user-avatar" aria-hidden="true">{initials(member.name)}</span>
                                  <span>
                                    <strong>{member.name}</strong>
                                    <small>{member.email}</small>
                                  </span>
                                </div>
                              </td>
                              <td>
                                <label className="sr-only" htmlFor={`role-${member.id}`}>Role for {member.name}</label>
                                <select
                                  id={`role-${member.id}`}
                                  value={member.role}
                                  disabled={isPending}
                                  onChange={(event) => void handleMemberUpdate(member, { role: event.target.value as MembershipRole })}
                                >
                                  {ROLES.map((role) => (
                                    <option key={role} value={role}>{formatEnumLabel(role)}</option>
                                  ))}
                                </select>
                              </td>
                              <td>
                                <label className="sr-only" htmlFor={`status-${member.id}`}>Status for {member.name}</label>
                                <select
                                  id={`status-${member.id}`}
                                  className={`status-select status-${member.status}`}
                                  value={member.status}
                                  disabled={isPending}
                                  onChange={(event) => void handleMemberUpdate(member, { status: event.target.value as MembershipStatus })}
                                >
                                  {STATUSES.map((status) => (
                                    <option key={status} value={status}>{formatEnumLabel(status)}</option>
                                  ))}
                                </select>
                              </td>
                              <td className="joined-cell">{isPending ? "Updating…" : formatJoinedAt(member.joined_at)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {members.length === 0 && (
                      <p className="table-empty">No members are available in this workspace.</p>
                    )}
                  </div>
                </section>
              ) : (
                <section className="permission-card">
                  <div aria-hidden="true">i</div>
                  <span>
                    <strong>Member management is restricted</strong>
                    <p>Only a system administrator can view or change workspace members.</p>
                  </span>
                </section>
              )}
            </>
          ) : (
            <section className="empty-state">
              <h2>Workspace unavailable</h2>
              <p>Select a workspace again or sign in to retry.</p>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
