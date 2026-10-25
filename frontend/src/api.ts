export type Row = {
  id: string;
  kind: string;
  data: Record<string, any>;
  version: number;
  created_at: string;
  updated_at: string;
};
export type SessionInfo = {
  user: { id: string; name: string; email: string; platform_admin: boolean };
  roles: string[];
  permissions: string[];
  authz_version: number;
  features: { consultation: boolean; course_packages: boolean; demo_mode?: boolean };
  tenants: {
    id: string;
    name: string;
    slug: string;
    role: string;
    roles: string[];
    status: string;
  }[];
  tenant_id: string;
  role: string;
  entitlement: { active: boolean; until: string | null };
};
export type ContentItem = {
  id: string;
  title: string;
  form: string;
  current_version: number;
  status: string;
  versions: {
    id: string;
    version: number;
    title: string;
    body: string;
    assets: string[];
    policy_checked: boolean;
    policy_notes: string[];
  }[];
  predictions: {
    id: string;
    version_id: string;
    rubric_version: string;
    payload: Record<string, any>;
  }[];
};
export type Job = {
  id: string;
  kind?: string;
  status: string;
  error: string;
  error_code: string;
  created_at: string;
  scheduled_at?: string;
  external_url?: string;
  output?: Record<string, any>;
  asset_ids?: string[];
  prompt?: string;
  version_id?: string;
  account_id?: string;
};
let activePermissions = new Set<string>();
let activeTenant = "";
export const can = (permission: string) => activePermissions.has(permission);
export const pagePermission: Record<string, string> = {
  dashboard: "",
  content: "content.read",
  matrix: "social.read",
  publishing: "publish.read",
  leads: "lead.read",
  inbox: "conversation.read",
  academics: "education.read",
  students: "student.read",
  finance: "finance.read",
  knowledge: "knowledge.read",
  community: "community.read",
  reports: "reports.read",
  operations: "tenant.manage",
  authorization: "members.manage",
  revenue: "revenue.read",
  studio: "",
  addons: "content.read",
  settings: "",
};
export async function api<T = any>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (activeTenant && !path.startsWith("/auth/"))
    headers.set("X-Tenant-ID", activeTenant);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const csrf = document.cookie
    .split("; ")
    .find((x) => x.startsWith("ops_csrf="))
    ?.split("=")
    .slice(1)
    .join("=");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    ...init,
    headers,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail;
    if (detail?.code === "DEMO_ACCESS_REQUIRED") window.location.replace("/");
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || "请求暂未完成，请重试";
    const fields = detail?.fields
      ?.map((x: any) => x.field + ": " + x.message)
      .join("；");
    if (!path.startsWith("/auth/") && [401, 403, 409].includes(response.status))
      window.dispatchEvent(new Event("permissions-refresh"));
    throw new Error(message + (fields ? " · " + fields : ""));
  }
  if (path === "/auth/me") {
    activePermissions = new Set(result.permissions || []);
    activeTenant = result.tenant_id || "";
    if (result.roles?.includes("owner")) result.role = "owner";
  }
  if (path === "/auth/logout") {
    activePermissions.clear();
    activeTenant = "";
  }
  return result as T;
}
export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const money = (fen: number = 0) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(fen / 100);
export const date = (value?: string | null, full = false) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        ...(full ? { hour: "2-digit", minute: "2-digit" } : {}),
      }).format(new Date(value))
    : "—";
export const uid = () => crypto.randomUUID();
export const roles: Record<string, string> = {
  owner: "机构负责人",
  operator: "运营销售（兼容）",
  admissions: "招生",
  content_ops: "内容运营",
  academic_admin: "教务",
  teacher: "授课",
  scheduler: "排班",
  revenue_viewer: "整体营收查看",
  finance: "财务",
};
export const platforms: Record<string, string> = {
  xiaohongshu: "小红书",
  douyin: "抖音",
  channels: "视频号",
};
export const statuses: Record<string, string> = {
  trial_ready: "试运行成品已完成",
  awaiting_review: "待审核发布",
  waiting_metrics: "等待T+3实绩",
  blocked: "等待处理",
  projected: "计划时段",
  requested: "待审批",
  open: "待处理",
  resolved: "已处理",
  review: "待核对",
  partial: "部分完成",
  conflict: "待处理",
  imported: "已导入",
  unassigned: "待分配",
  returned: "已退回",
  withdrawn: "已退读 / 撤回",
  recovered: "已恢复",
  acknowledged: "已登记处理",
  quoted: "已报价",
  approved_pending_integration: "已确认权益，待接入",
  consumed: "业务已登记",
  made_up: "补课完成",
  reviewed: "复核通过",
  draft: "草稿",
  retrying: "限流等待",
  queued: "待执行",
  processing: "处理中",
  running: "运行中",
  polling: "生成中",
  scheduled: "待发布",
  submitting: "已提交",
  succeeded: "已完成",
  failed: "未完成",
  unknown: "待核实",
  cancelled: "已取消",
  waiting_authorization: "待授权",
  unconfigured: "未连接",
  connected: "已连接",
  new: "新线索",
  contacted: "已联系",
  booked: "已预约",
  attended: "已到场",
  won: "已报名",
  lost: "暂不报名",
  candidate: "候选",
  selected: "已选",
  done: "已完成",
  rejected: "已跳过",
  confirmed: "已确认",
  approved: "已审核",
  sent: "已发送",
  completed: "已完成",
  active: "正常",
  suspended: "已暂停",
  bot: "智能接待",
  human: "人工接待",
  waiting_human: "待人工接待",
  pending: "待确认",
  published: "已发布",
};
export function localInput(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

export async function recordsAll(kind: string): Promise<Row[]> {
  const rows: Row[] = [];
  for (let skip = 0; skip < 5000; skip += 200) {
    const page = await api(`/records/${kind}?skip=${skip}&limit=200`);
    rows.push(...page.items);
    if (page.items.length < 200 || skip + 200 >= page.total)
      return Array.from(new Map(rows.map((r) => [r.id, r])).values());
  }
  throw Error("关联记录超过5000条，请先缩小业务范围");
}
