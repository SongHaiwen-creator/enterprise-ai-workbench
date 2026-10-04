import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { PlatformNavigation } from "@/app/components/platform-navigation";
import { displayMessage, formatEnumLabel, formatJoinedAt, formatTimestamp } from "@/utils/presentation";

afterEach(cleanup);

describe("中文界面与公开介绍", () => {
  it("provides a real long landing page and platform entry without a login form", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("让企业知识可问，业务操作可控。");
    expect(screen.queryByLabelText("密码")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始使用" })).toHaveAttribute("href", "/app");
    const index = screen.getByRole("navigation", { name: "功能模块索引" });
    expect(within(index).getAllByRole("link")).toHaveLength(6);
    expect(screen.getByAltText(/抽象插画/)).toHaveAttribute("src", expect.stringContaining("hero-knowledge"));
    expect(screen.getAllByText("交互示例")).toHaveLength(6);
  });

  it("allows keyboard interaction with citations, scenarios and approval state examples", async () => {
    render(<Home />);
    const user = userEvent.setup();
    const citation = screen.getByRole("button", { name: /差旅管理制度/ });
    citation.focus(); await user.keyboard("{Enter}");
    expect(citation).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("合成资料，仅用于展示引用交互。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "权限申请" }));
    expect(screen.getByText("需要人工审核")).toBeInTheDocument();
    const approval = screen.getByLabelText("审批中心交互示例");
    await user.click(within(approval).getByRole("button", { name: "查看下一步" }));
    expect(within(approval).getByText("未执行")).toBeInTheDocument();
    await user.click(within(approval).getByRole("button", { name: "查看下一步" }));
    expect(within(approval).getByText("已成功")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "运行结果" }));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("keeps roles and wire values intact while showing Chinese and explicit time zones", () => {
    expect(formatEnumLabel("system_admin")).toBe("系统管理员");
    expect(formatEnumLabel("unknown_identifier")).toBe("unknown_identifier");
    expect(formatJoinedAt(null)).toBe("尚未加入");
    expect(formatTimestamp("2026-10-03T01:02:03Z")).toContain("09:02:03（北京时间）");
    expect(displayMessage("Not authorized for this workspace", 403)).toBe("你没有访问此工作空间的权限。");
    expect(displayMessage("unknown server failure", 503)).toBe("服务暂不可用，请稍后重试。");
    expect(displayMessage("原始中文提示", 409)).toBe("原始中文提示");
    expect(displayMessage("User-entered prose")).toBe("User-entered prose");
  });

  it("uses a workspace select and grouped permission-aware navigation", async () => {
    const onWorkspace = vi.fn(); const onArea = vi.fn();
    render(<PlatformNavigation workspaces={[
      { id: "a", name: "产品团队", slug: "a", role: "employee", status: "active", joined_at: null },
      { id: "b", name: "运营团队", slug: "b", role: "employee", status: "active", joined_at: null },
    ]} selectedId="a" currentUser={{ id: "user", name: "林小雨", email: "demo@example.com", status: "active" }} area="assistant" canManageOperations={false} pending={false} onWorkspace={onWorkspace} onArea={onArea} onLogout={vi.fn()} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "当前工作空间" }), "b");
    expect(onWorkspace).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
    expect(screen.getByRole("button", { name: "智能助手" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "执行日志" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "知识问答" }));
    expect(onArea).toHaveBeenCalledWith("knowledge-qa");
  });
});
