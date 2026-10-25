import React from "react";
import { api, SessionInfo, can, money, roles } from "./api";
import { PageTitle, Loading, Notice, Empty, useResource } from "./ui";
import { Users, Wallet, BookOpen, PenLine, CalendarDays } from "lucide-react";
export default function Dashboard({ me }: { me: SessionInfo }) {
  const data = useResource<any>(
    () => api("/dashboard"),
    [me.tenant_id, me.authz_version],
    15000,
  );
  if (data.loading) return <Loading />;
  if (data.error) return <Notice tone="error">{data.error}</Notice>;
  const d = data.value,
    c = d?.counts || {},
    cards: any[] = [];
  if (can("lead.read"))
    cards.push([Users, "本人负责的招生线索", c.lead || 0, "#leads"]);
  if (can("finance.read"))
    cards.push([Wallet, "机构净收款", money(d.net_revenue_fen), "#finance"]);
  if (can("revenue.read") && !can("finance.read"))
    cards.push([
      Wallet,
      "本月机构净收款",
      money(d.revenue?.totals?.net_fen),
      "#revenue",
    ]);
  if (can("education.read"))
    cards.push(
      [CalendarDays, "可见排课", c.lesson || 0, "#academics"],
      [BookOpen, "可见学员", c.student || 0, "#students"],
    );
  if (can("publish.read"))
    cards.push([PenLine, "已发布作品", d.published || 0, "#publishing"]);
  if (can("order.read") && !can("finance.read"))
    cards.push([BookOpen, "可见课程订单", c.order || 0, "#finance"]);
  if (d.feedback_kpi)
    cards.push([
      CalendarDays,
      "待完成课返",
      d.feedback_kpi.expected - d.feedback_kpi.completed,
      "#academics",
    ]);
  if (can("tenant.manage"))
    cards.push([CalendarDays, "经营异常", d.alert_count || 0, "#operations"]);
  return (
    <>
      <PageTitle
        eyebrow="YOUR WORKSPACE"
        title={me.user.name + "，今天也从容一点"}
        text={
          "当前机构：" +
          (me.tenants.find((t) => t.id === me.tenant_id)?.name || "") +
          " · " +
          me.roles.map((r) => roles[r]).join(" / ")
        }
      />
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-tag">机构独立 · 岗位协作</div>
          <h2>
            从自己的工作开始，
            <br />
            让每一次协作有序发生。
          </h2>
          <p>一人可以兼任多个岗位；功能由负责人授权，记录按负责范围展示。</p>
        </div>
      </section>
      <div className="stats-grid">
        {cards.map(([Icon, title, value, link]) => (
          <a className="stat" href={link} key={title}>
            <div className="stat-label">
              <span>{title}</span>
              <Icon size={17} />
            </div>
            <div className="stat-value">{value}</div>
            <small>查看负责范围内的记录 →</small>
          </a>
        ))}
      </div>
      <section className="panel">
        <h2>我的工作入口</h2>
        <div className="button-row" style={{ flexWrap: "wrap" }}>
          {[
            ["lead.read", "招生跟进", "#leads"],
            ["conversation.read", "咨询接待", "#inbox"],
            ["content.read", "内容创作", "#content"],
            ["publish.read", "发布与平台连接", "#publishing"],
            ["education.read", "教务与课堂", "#academics"],
            ["finance.read", "财务台账", "#finance"],
            ["knowledge.read", "课程知识库", "#knowledge"],
          ]
            .filter(
              ([p]) =>
                can(p) &&
                (p !== "conversation.read" || me.features?.consultation),
            )
            .map(([, title, url]) => (
              <a key={url} href={url} className="button">
                进入{title}
              </a>
            ))}
        </div>
      </section>
      {can("lead.read") && (
        <section className="panel">
          <h2>待跟进事项</h2>
          {d.followups?.length ? (
            d.followups.map((r: any) => (
              <p key={r.id}>
                {r.data.name} · {r.data.stage} · {r.data.followup_at}
              </p>
            ))
          ) : (
            <Empty
              title="暂无待跟进事项"
              text="负责人分配后，线索会出现在招生人员工作台。"
            />
          )}
        </section>
      )}
    </>
  );
}
