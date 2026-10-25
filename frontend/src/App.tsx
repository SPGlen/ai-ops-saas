import DemoPage, { DemoModeBar } from "./DemoPage";
import React, { useState, useEffect } from "react";
import {
  LayoutDashboard,
  PenLine,
  CalendarDays,
  Users,
  MessagesSquare,
  GraduationCap,
  Wallet,
  BookOpen,
  Settings,
  Sprout,
  ChevronRight,
  Menu,
  LogOut,
  ShieldCheck,
  HeartHandshake,
  Building2,
} from "lucide-react";
import { api, post, SessionInfo, roles, can, pagePermission } from "./api";
import { Loading, Notice, PageTitle } from "./ui";
import Dashboard from "./Dashboard";
import {
  StudentDirectory,
  AdmissionIntake,
  ReportPage,
  FeedbackKPIPanel,
  FinanceOverview,
  FinanceDetailHost,
  OperationsSettings,
} from "./OperationsPage";
import { StudioPage } from "./StudioPage";
import { AuthPage, PublicPage, InboxPage } from "./AccessPages";
import { InvitePage, AuthorizationPage } from "./StaffPage";
import { FamilyFeedbackPanel, RevenueOverview } from "./ManagementPage";
import { SocialWorkspace } from "./SocialWorkspace";
import SettingsPage, { PlatformPage } from "./SettingsPage";
import {
  RecordPage,
  FinanceExtra,
  ReceiptIntake,
  SettlementStatements,
  EducationReport,
} from "./BusinessPage";
import { ContentPage, PublishingPage } from "./ContentPage";
import MatrixPage from "./MatrixPage";
const nav = [
  ["demo", "企业演示总览", LayoutDashboard, []],
  ["dashboard", "工作台", LayoutDashboard, []],
  ["leads", "招生线索", Users, []],
  ["students", "学员档案", BookOpen, []],
  ["academics", "教务管理", GraduationCap, []],
  ["finance", "财务台账", Wallet, []],
  ["revenue", "营收总览", Wallet, []],
  ["matrix", "自媒体矩阵", CalendarDays, []],
  ["content", "内容工作室", PenLine, []],
  ["publishing", "发布与复盘", CalendarDays, []],
  ["reports", "经营周报 / 月报", LayoutDashboard, []],
  ["authorization", "成员与授权", ShieldCheck, []],
  ["knowledge", "课程知识库", Sprout, []],
  ["community", "社群运营", HeartHandshake, []],
  ["inbox", "咨询接待", MessagesSquare, []],
  ["studio", "表单与流程", Settings, []],
  ["operations", "经营规则与提醒", ShieldCheck, []],
  ["settings", "机构与连接", Settings, []],
] as const;
function Group({ me, page }: { me: SessionInfo; page: string }) {
  const groups: Record<
    string,
    { title: string; text: string; items: [string, string][] }
  > = {
    academics: {
      title: "让每一堂课，有序发生",
      text: "排课、签到、课时与课返完成考核，在这里连起来。",
      items: [
        ["class", "班级"],
        ["lesson", "排课"],
        ["enrollment", "报名与课时"],
        ["leave", "请假与补课"],
        ["family_feedback", "学员家长反馈"],
      ],
    },
    students: {
      title: "每一位学员，都被看见",
      text: "管理学员与家长联系资料，跟进课程学习进度。",
      items: [["student", "学员档案"]],
    },
    leads: {
      title: "把每一次连接，照顾好",
      text: "从家长咨询到试听报名，记录每一步跟进。",
      items: [
        ["lead", "招生线索"],
        ["channel", "合作渠道"],
      ],
    },
    finance: {
      title: "每一笔收支，清清楚楚",
      text: "订单、流水与渠道结算相互关联。金额以实际记录为准。",
      items: [
        ["order", "课程订单"],
        ["expense", "费用票据"],
        ["ledger", "收退款流水"],
        ["settlement", "渠道结算"],
      ],
    },
    knowledge: {
      title: "用确认过的事实，回答与创作",
      text: "课程、价格、优惠和赛事依据按版本维护；只有已审核资料会被智能体引用。",
      items: [["knowledge", "机构知识库"]],
    },
    community: {
      title: "把社群经营成长期的连接",
      text: "安排活动，准备分组文案，记录具备官方权限的触达结果。",
      items: [["community", "活动与发送任务"]],
    },
  };
  if (page === "finance" && !can("finance.read")) {
    groups.finance.title = "负责范围内的课程订单";
    groups.finance.text = "招生查看本人订单；教务查看报名所需的付款状态。";
  }
  const group = groups[page],
    [tab, setTab] = useState(group.items[0][0]);
  useEffect(() => setTab(group.items[0][0]), [page]);
  const choices = group.items.filter(([k]) =>
    can(["ledger", "settlement"].includes(k) ? "finance.read" : k + ".read"),
  );
  if (!choices.length) return <Notice>当前岗位无权访问此页面。</Notice>;
  const selected = choices.some((x) => x[0] === tab) ? tab : choices[0][0];
  return (
    <>
      <PageTitle
        eyebrow={page.toUpperCase()}
        title={group.title}
        text={group.text}
      />
      {choices.length > 1 && (
        <div className="tabs">
          {choices.map(([k, label]) => (
            <button
              key={k}
              className={"tab " + (tab === k ? "active" : "")}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {selected === "family_feedback" && <FamilyFeedbackPanel />}
      {selected === "expense" && <ReceiptIntake />}
      {page === "academics" && can("education.read") && <FeedbackKPIPanel />}
      {page === "leads" && selected === "lead" && <AdmissionIntake />}
      {page === "finance" && can("finance.read") && selected === "order" && (
        <FinanceOverview />
      )}
      {["ledger", "settlement"].includes(selected) ? (
        <FinanceExtra mode={selected} />
      ) : (
        selected !== "family_feedback" && (
          <RecordPage key={selected} kind={selected} role={me.role} />
        )
      )}{" "}
      {selected === "settlement" && <SettlementStatements />}
    </>
  );
}
export default function App() {
  const [me, setMe] = useState<SessionInfo | null>(null),
    [loading, setLoading] = useState(true),
    [hash, setHash] = useState(location.hash.slice(1) || "dashboard"),
    [menu, setMenu] = useState(false),
    [error, setError] = useState("");
  async function refresh() {
    try {
      setMe(await api("/auth/me"));
      setError("");
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (!location.pathname.startsWith("/book/")) void refresh();
    const f = () => {
      setHash(location.hash.slice(1) || "dashboard");
      setMenu(false);
      window.scrollTo(0, 0);
    };
    addEventListener("hashchange", f);
    const timer = setInterval(refresh, 5000);
    addEventListener("focus", refresh);
    addEventListener("permissions-refresh", refresh);
    return () => {
      removeEventListener("hashchange", f);
      clearInterval(timer);
      removeEventListener("focus", refresh);
      removeEventListener("permissions-refresh", refresh);
    };
  }, []);
  useEffect(() => {
    if (!me?.tenant_id) return;
    const refreshData = () => window.dispatchEvent(new Event("ops-refresh"));
    if (me.features?.demo_mode) {
      const timer = setInterval(refreshData, 5000);
      return () => clearInterval(timer);
    }
    const source = new EventSource(
      `/api/v1/operations/events?tenant_id=${me.tenant_id}`,
    );
    source.addEventListener("refresh", refreshData);
    const fallback = setInterval(() => {
      if (source.readyState !== EventSource.OPEN) refreshData();
    }, 5000);
    return () => {
      source.close();
      clearInterval(fallback);
    };
  }, [me?.tenant_id, me?.features?.demo_mode]);
  if (location.pathname.startsWith("/invite")) return <InvitePage />;
  if (location.pathname.startsWith("/book/"))
    return (
      <PublicPage
        slug={decodeURIComponent(location.pathname.split("/")[2] || "")}
      />
    );
  if (loading) return <Loading />;
  if (!me || ["/verify", "/reset"].includes(location.pathname))
    return <AuthPage ready={refresh} />;
  const requested =
      me.user.platform_admin && !me.tenants.length
        ? "platform"
        : hash.split("?")[0],
    available = nav.filter(
      (n) =>
        (n[0] !== "demo" || me.features?.demo_mode) &&
        (n[0] !== "inbox" || me.features?.consultation) &&
        (!pagePermission[n[0]] ||
          can(pagePermission[n[0]]) ||
          (n[0] === "finance" && can("order.read")) ||
          (n[0] === "academics" && can("schedule.read"))),
    ),
    page =
      requested === "platform" && me.user.platform_admin
        ? "platform"
        : available.some((n) => n[0] === requested)
          ? requested
          : "dashboard";
  const title =
      page === "platform"
        ? "平台管理"
        : page === "finance" && !can("finance.read")
          ? "课程订单"
          : nav.find((n) => n[0] === page)?.[1],
    tenant = me.tenants.find((t) => t.id === me.tenant_id);
  return (
    <div className="app">
      <aside className={"sidebar " + (menu ? "open" : "")}>
        <a className="brand" href="#dashboard">
          <span className="brand-mark">知</span>
          <div>
            知营<small>ZHIYING · OPS</small>
          </div>
        </a>
        <div className="nav-label">工作空间</div>
        <nav>
          {available.map(([key, label, Icon], i) => (
            <React.Fragment key={key}>
              {key === "authorization" && (
                <div className="nav-label">机构管理</div>
              )}
              <a
                className={"nav-item " + (page === key ? "active" : "")}
                href={"#" + key}
              >
                <Icon size={17} strokeWidth={1.7} />
                {key === "finance" && !can("finance.read") ? "课程订单" : label}
              </a>
            </React.Fragment>
          ))}
          {me.user.platform_admin && (
            <a
              className={"nav-item " + (page === "platform" ? "active" : "")}
              href="#platform"
            >
              <ShieldCheck size={17} />
              平台管理
            </a>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <Sprout size={21} color="#d9eab6" />
            <h4>从一份课程资料开始</h4>
            <p>
              确认课程事实，让内容和客服
              <br />
              说得清楚，也说得可信。
            </p>
            <a href="#knowledge">
              <button>整理知识库 ↗</button>
            </a>
          </div>
          <div className="sidebar-footer">让运营更从容 · 知营</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={19} />
            </button>
            <span>机构工作空间</span>
            <ChevronRight size={12} />
            <strong>{title}</strong>
          </div>
          <div className="top-actions">
            <select
              className="org-select"
              aria-label="当前机构"
              value={me.tenant_id || ""}
              onChange={async (e) => {
                try {
                  await post("/auth/switch-tenant", {
                    tenant_id: e.target.value,
                  });
                  location.reload();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              {!me.tenant_id && (
                <option value="">
                  {me.user.platform_admin ? "平台管理员" : "请选择机构"}
                </option>
              )}
              {me.tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <span className="avatar">{me.user.name.slice(0, 1)}</span>
            <span className="user-label">
              {me.user.name}
              <small>{me.roles.map((r) => roles[r] || r).join(" / ")}</small>
            </span>
            <button
              className="icon-button"
              aria-label="退出登录"
              title="退出登录"
              onClick={async () => {
                await post("/auth/logout");
                setMe(null);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main className="workspace" key={me.tenant_id + ":" + me.authz_version}>
          {me.features?.demo_mode && <DemoModeBar me={me} ready={refresh} />}
          {can("finance.read") && <FinanceDetailHost />}
          {error && <Notice tone="error">{error}</Notice>}
          {me.tenant_id && !me.entitlement?.active && (
            <Notice>
              机构使用期已结束或已暂停。您仍可查看与导出已有记录，新增和自动任务已停止。请联系平台管理员延期。
            </Notice>
          )}
          {tenant?.name.includes("演示") && me.user.platform_admin && (
            <Notice>
              当前账号具有平台管理员和机构负责人权限。验证员工视角请退出，在登录页展开“开发演示”选择教师、招生或财务账号。
              <button
                className="button small"
                onClick={async () => {
                  await post("/auth/logout");
                  setMe(null);
                }}
              >
                切换员工演示账号
              </button>
            </Notice>
          )}
          {tenant?.name.includes("演示") && !me.features?.demo_mode && (
            <Notice>
              当前为演示机构，页面展示已保存的示例业务记录。真实模型和外部账号连接需在机构设置中配置。
            </Notice>
          )}
          {!me.tenant_id && !me.user.platform_admin ? (
            <Notice>
              当前账号没有选定可用机构。请接受邀请、选择已加入的机构，或联系负责人恢复权限。
            </Notice>
          ) : page === "demo" && me.features?.demo_mode ? (
            <DemoPage me={me} />
          ) : page === "dashboard" ? (
            <Dashboard me={me} />
          ) : page === "matrix" ? (
            <MatrixPage />
          ) : page === "content" ? (
            <ContentPage role={me.role} />
          ) : page === "publishing" ? (
            <>
              <PublishingPage />
              {me.features?.consultation && <SocialWorkspace />}
            </>
          ) : page === "students" ? (
            <StudentDirectory demo={Boolean(me.features?.demo_mode)} />
          ) : page === "reports" ? (
            <ReportPage />
          ) : page === "studio" ? (
            <StudioPage />
          ) : page === "operations" ? (
            <OperationsSettings />
          ) : page === "inbox" ? (
            <InboxPage />
          ) : page === "authorization" ? (
            <AuthorizationPage />
          ) : page === "revenue" ? (
            <RevenueOverview />
          ) : page === "settings" ? (
            <SettingsPage role={me.role} refreshMe={refresh} />
          ) : page === "platform" ? (
            <>
              <PlatformPage />
            </>
          ) : (
            <Group key={page} me={me} page={page} />
          )}
        </main>
      </div>
    </div>
  );
}
