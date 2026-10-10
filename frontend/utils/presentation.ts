const ENUM_LABELS: Record<string, string> = {
  draft: "草稿", production_database: "生产数据库", analytics_warehouse: "分析数据仓库", source_control: "代码管理系统",
  tool_executed: "工具已执行", tool_approval_required: "工具需要审批", tool_not_executed: "工具未执行", approved_execution_succeeded: "批准后执行成功", approved_execution_failed: "批准后执行失败",
  agent_not_found: "智能体不存在", agent_inactive: "智能体已停用", knowledge_base_required: "需要知识库", knowledge_base_not_found: "知识库不存在", knowledge_base_inactive: "知识库已停用", input_too_large: "输入过长", tool_configuration_error: "工具配置错误", tool_unavailable: "工具不可用", tool_execution_failed: "工具执行失败", access_denied: "访问已拒绝", approval_not_found: "审批申请不存在", approval_not_pending: "审批已处理", approval_expired: "审批已过期", approval_invalidated: "审批已失效", approval_busy: "审批正在处理中", approval_execution_failed: "审批执行失败",
  employee: "员工", knowledge_admin: "知识管理员", agent_admin: "智能体管理员", system_admin: "系统管理员",
  active: "已启用", disabled: "已停用", invited: "待加入", absent: "非成员", pending: "待处理", approved: "已批准", rejected: "已拒绝", cancelled: "已取消", expired: "已过期", invalidated: "已失效",
  not_started: "未执行", succeeded: "成功", failed: "失败", running: "运行中", completed: "已完成", passed: "通过", error: "错误", submitted: "已提交", under_review: "审核中", paid: "已支付",
  knowledge_qa: "知识问答", tool_calling: "工具调用", tool_request: "工具请求", permission_boundary: "权限边界", refusal_behavior: "拒绝行为",
  answered: "已回答", unsupported: "资料不足或超出能力范围", executed: "已执行", not_executed: "未执行", approval_required: "需要审批",
  present: "必须包含引用", none: "无", no_available_tool: "无可用工具", no_matching_tool: "无匹配工具", missing_required_arguments: "缺少必要参数",
  same_workspace: "当前工作空间", other_workspace: "其他工作空间", nonexistent: "不存在的空间", forbidden: "无访问权限", not_found: "资源不存在",
  agent_route: "助手请求", knowledge_answer: "知识回答", agent_configuration_read: "读取智能体配置", tool_configuration_read: "读取工具配置", evaluation_dataset_read: "读取评测数据集",
  unsupported_request: "超出能力范围", knowledge_unsupported: "知识依据不足", approval_decision: "审批决定", approval_cancel: "取消申请", approve: "批准", reject: "拒绝",
  read_only: "只读", write_sensitive: "敏感写入", standard: "标准访问", admin: "管理员访问", crm: "客户管理系统", erp: "企业资源系统", analytics: "分析系统", jira: "项目协作系统", gitlab: "代码管理系统",
  routing_match_rate: "请求类型匹配率", tool_selection_match_rate: "工具选择匹配率", tool_outcome_match_rate: "工具结果匹配率", permission_boundary_pass_rate: "权限边界通过率", refusal_behavior_pass_rate: "拒绝行为通过率", citation_requirement_compliance: "引用要求符合率",
  routing_intent: "请求类型", answer_status: "回答状态", citation_requirement: "引用要求", tool_key: "工具标识", outcome: "处理结果", non_execution_reason: "未执行原因", actor_role: "测试角色", actor_membership_status: "测试成员状态", target_context: "目标空间", operation: "操作", expected_http_status: "预期 HTTP 状态", result_category: "结果类型",  response_category: "响应类型", safe_response_required: "要求安全响应",
  provider_error: "模型服务错误", provider_unavailable: "模型服务不可用", generation_failed: "回答生成失败", configuration_error: "配置错误", configuration_changed: "配置已变化", timeout: "请求超时", budget_exhausted: "运行时限已耗尽", permission_denied: "访问已拒绝", internal_error: "内部错误", run_deadline_exceeded: "运行时限已耗尽", run_failed: "运行失败", case_error: "用例错误",
};

export function formatEnumLabel(value: string): string {
  // Unknown values and user-entered identifiers remain intact.
  return ENUM_LABELS[value] ?? value;
}

export function initials(value: string): string {
  const words = value.trim().split(/\s+/).filter(Boolean);
  return words.length ? words.slice(0, 2).map(word => Array.from(word)[0].toUpperCase()).join("") : "?";
}

export function formatJoinedAt(value: string | null): string {
  if (!value) return "尚未加入";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "日期未知" : new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : `${new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date)}（北京时间）`;
}

const MESSAGE_LABELS: Record<string, string> = {
  "Knowledge base context is required for knowledge questions.": "知识类问题需要选择知识库，请选择后重新提交。",
  "This request is outside the configured Agent capabilities.": "此请求超出了当前智能体配置的能力范围。",
  "The retrieved knowledge does not contain enough evidence to answer this question.": "检索到的资料不足以支持回答此问题。",
  "No permitted enterprise capability can safely handle this request.": "没有已授权的企业工具能够安全处理此请求。",
  "The read-only enterprise capability completed successfully.": "只读业务查询已完成。",
  "An approval request was submitted for human review. Nothing was executed.": "申请已提交，等待人工审核。尚未执行任何操作。",
  "Not authorized for this workspace": "你没有访问此工作空间的权限。",
  "Approval not found": "审批申请不存在。", "Approval action not permitted": "你没有处理此申请的权限。", "Approval review not permitted": "你没有审核此申请的权限。",
  "Approval is no longer pending": "申请已不处于待审核状态，请查看最新结果。", "Approval has expired": "申请已过期，请重新提交。", "Approval is no longer valid; submit a new request": "申请已失效，请重新提交。", "Approval is being processed; retry": "申请正在处理中，请稍后重试。",
  "Enterprise Tool request failed": "企业工具请求失败。", "Tool configuration is unavailable": "工具配置暂不可用。", "Tool is no longer active or assigned": "工具已停用或不再关联当前智能体。",
  "Invalid email or password": "邮箱或密码不正确。", "Incorrect email or password": "邮箱或密码不正确。", "Not authenticated": "请先登录。", "Workspace access denied": "你没有访问此工作空间的权限。",
  "Knowledge base not found": "知识库不存在。", "Agent not found": "智能体不存在。", "Knowledge base is disabled": "知识库已停用。",
};

// Presentation only: raw ApiError and model-generated answers are unchanged.
export function displayMessage(value: string, status?: number): string {
  if (MESSAGE_LABELS[value]) return MESSAGE_LABELS[value];
  if (/[\u3400-\u9fff]/.test(value)) return value;
  if (status === undefined) return value;
  if (status === 401) return "登录凭据无效或已过期，请重新登录。";
  if (status === 403) return "你没有执行此操作的权限。";
  if (status === 404) return "资源不存在，或在当前工作空间中不可访问。";
  if (status === 409) return "当前状态不允许此操作，请刷新后查看最新状态。";
  if (status === 422) return "提交内容不符合要求，请检查输入和配置。";
  if (status === 0) return "无法连接服务，请检查连接后重试。";
  if (status >= 500) return "服务暂不可用，请稍后重试。";
  return value;
}
