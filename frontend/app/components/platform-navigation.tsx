"use client";

import Link from "next/link";

import { useRef } from "react";
import type { CurrentUser, WorkspaceListItem } from "@/utils/api";
import { formatEnumLabel, initials } from "@/utils/presentation";
import { BrandMark, Icon, type IconName } from "./ui-icon";

export type ProductArea = "assistant" | "knowledge-qa" | "knowledge-admin" | "agent-tool-admin" | "approvals" | "execution-logs" | "evaluation-datasets" | "bad-cases" | "workspace";

type Props = {
  workspaces: WorkspaceListItem[]; selectedId: string | null; currentUser: CurrentUser;
  area: ProductArea; canManageOperations: boolean; canManageKnowledge?: boolean; pending: boolean;
  onWorkspace: (workspace: WorkspaceListItem) => void;
  onArea: (area: ProductArea) => void; onLogout: () => void;
};

const groups: { label: string; admin?: boolean; knowledge?: boolean; items: { area: ProductArea; label: string; icon: IconName }[] }[] = [
  { label: "日常使用", items: [{ area: "assistant", label: "智能助手", icon: "sparkles" }, { area: "knowledge-qa", label: "知识问答", icon: "book" }, { area: "approvals", label: "审批中心", icon: "shield" }] },
  { label: "知识维护", knowledge: true, items: [{ area: "knowledge-admin", label: "知识管理", icon: "book" }] },
  { label: "运营管理", admin: true, items: [{ area: "agent-tool-admin", label: "Agent 与工具", icon: "sparkles" }, { area: "execution-logs", label: "执行日志", icon: "list" }, { area: "evaluation-datasets", label: "评测数据集", icon: "layers" }, { area: "bad-cases", label: "问题案例", icon: "list" }] },
  { label: "工作空间", items: [{ area: "workspace", label: "空间与成员", icon: "users" }] },
];

export function PlatformNavigation(props: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  function close() { dialog.current?.close(); trigger.current?.focus(); }
  function navigation(mobile: boolean) {
    return <>
      <Link className="product-lockup" href="/" aria-label="企业 AI 工作台首页"><BrandMark /><strong>企业 AI 工作台</strong></Link>
      <label className="workspace-switcher"><span>当前工作空间</span>
        <select aria-label={mobile ? "切换工作空间" : "当前工作空间"} value={props.selectedId ?? ""} disabled={props.pending || !props.workspaces.length} onChange={event => {
          const workspace = props.workspaces.find(item => item.id === event.target.value);
          if (workspace) props.onWorkspace(workspace);
          if (mobile) close();
        }}>
          {!props.workspaces.length && <option value="">暂无工作空间</option>}
          {props.workspaces.map(item => <option key={item.id} value={item.id}>{item.name} · {formatEnumLabel(item.role)}</option>)}
        </select>
      </label>
      <nav className="product-nav" aria-label={mobile ? "移动端功能导航" : "功能导航"}>
        {groups.filter(group => (!group.admin || props.canManageOperations) && (!group.knowledge || props.canManageKnowledge)).map(group => <div className="nav-group" key={group.label}>
          <p className="nav-group-label">{group.label}</p>
          {group.items.map(item => <button className={props.area === item.area ? "product-link active" : "product-link"} key={item.area} type="button" aria-current={props.area === item.area ? "page" : undefined} disabled={props.pending} onClick={() => { props.onArea(item.area); if (mobile) close(); }}><Icon name={item.icon} /><span>{item.label}</span></button>)}
        </div>)}
      </nav>
      <div className="sidebar-user"><span className="user-avatar">{initials(props.currentUser.name)}</span><span><strong>{props.currentUser.name}</strong><small>{props.currentUser.email}</small></span><button className="icon-button" type="button" aria-label="退出登录" onClick={() => { props.onLogout(); if (mobile) close(); }}><Icon name="logout" /></button></div>
    </>;
  }
  return <>
    <aside className="sidebar">{navigation(false)}</aside>
    <button className="mobile-menu-trigger icon-button" ref={trigger} type="button" aria-label="打开功能导航" aria-haspopup="dialog" onClick={() => dialog.current?.showModal()}><Icon name="menu" /></button>
    <dialog className="mobile-navigation" aria-label="功能目录" ref={dialog} onCancel={close} onClick={event => { if (event.target === event.currentTarget) close(); }} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); close(); } }}>
      <div className="mobile-navigation-panel"><button className="drawer-close icon-button" type="button" aria-label="关闭功能导航" onClick={close}><Icon name="close" /></button>{navigation(true)}</div>
    </dialog>
  </>;
}
