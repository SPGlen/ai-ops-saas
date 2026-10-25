import React, { useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  api,
  post,
  patch,
  can,
  money,
  date,
  localInput,
  recordsAll,
} from "./api";
import {
  PageTitle,
  Loading,
  Notice,
  Empty,
  Field,
  Modal,
  useResource,
  Badge,
} from "./ui";
export const feedbackCategories: Record<string, string> = {
  teaching: "教学体验",
  schedule: "课程安排",
  service: "服务沟通",
  other: "其他",
};
export function ReportFeedbackSummary({ data }: { data: any }) {
  if (!data) return null;
  return (
    <section className="panel ops-section">
      <h2>学员与家长反馈</h2>
      <div className="ops-stats">
        {[
          ["反馈总数", data.count],
          ["平均评分 / 5", data.average_rating ?? "暂无评分"],
          ["待处理", data.unresolved],
          ["低评分（1至2分）", data.attention],
        ].map(([label, value]) => (
          <div className="ops-stat" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      {data.count ? (
        <>
          <p>
            家长反馈 {data.parents} 条 · 学员反馈 {data.students}{" "}
            条。未评分的记录不参与平均分。
          </p>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
                data={Object.entries(data.categories).map(([key, value]) => ({
                  name: feedbackCategories[key] || key,
                  count: value,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" name="反馈条数" fill="#34654a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p className="muted">本期未记录学员或家长反馈，满意度暂无数据。</p>
      )}
    </section>
  );
}
export function FamilyFeedbackPanel({
  studentId = "",
}: {
  studentId?: string;
}) {
  const rows = useResource<any[]>(
    () => recordsAll("family_feedback"),
    [studentId],
  );
  const refs = useResource<any>(
    async () => ({
      students: await recordsAll("student"),
      classes: await recordsAll("class"),
      enrollments: await recordsAll("enrollment"),
    }),
    [studentId],
  );
  const [editing, setEditing] = useState<any>(undefined),
    [message, setMessage] = useState("");
  const list = (rows.value || []).filter(
    (r) => !studentId || r.data.student_id === studentId,
  );
  return (
    <section className="panel ops-section">
      <div className="ops-keyline">
        <h2>学员家长反馈记录</h2>
        {can("family_feedback.write") && (
          <button className="button primary" onClick={() => setEditing(null)}>
            登记反馈
          </button>
        )}
      </div>
      <p>
        记录学生或家长的实际反馈，自动汇入对应周报、月报。教师课返是否完成另行考核。
      </p>
      {message && <Notice>{message}</Notice>}
      {(rows.error || refs.error) && (
        <Notice tone="error">{rows.error || refs.error}</Notice>
      )}
      {rows.loading ? (
        <Loading />
      ) : !list.length ? (
        <Empty
          title="暂无反馈记录"
          text="收到实际反馈后登记，未收到反馈不自动推断满意度。"
        />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>学员 / 班级</th>
                <th>反馈来源</th>
                <th>类型与评分</th>
                <th>内容及处理</th>
                <th>时间 / 状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id}>
                  <td>
                    {refs.value?.students.find(
                      (s: any) => s.id === r.data.student_id,
                    )?.data.name || "关联学员"}
                    <br />
                    <small>
                      {refs.value?.classes.find(
                        (c: any) => c.id === r.data.class_id,
                      )?.data.name || "未指定班级"}
                    </small>
                  </td>
                  <td>{r.data.respondent === "parent" ? "家长" : "学员"}</td>
                  <td>
                    {feedbackCategories[r.data.category]}
                    <br />
                    {r.data.rating == null ? "未评分" : r.data.rating + " / 5"}
                  </td>
                  <td className="feedback-body">
                    <strong>{r.data.name}</strong>
                    <p>{r.data.body}</p>
                    {r.data.resolution && <p>处理结果：{r.data.resolution}</p>}
                  </td>
                  <td>
                    {date(r.data.recorded_at, true)}
                    <br />
                    <Badge value={r.data.status} />
                  </td>
                  <td>
                    {r.can_edit && (
                      <button
                        className="button link"
                        onClick={() => setEditing(r)}
                      >
                        查看 / 处理
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing !== undefined && refs.value && (
        <FeedbackEditor
          key={editing?.id || "new"}
          row={editing}
          studentId={studentId}
          refs={refs.value}
          close={() => setEditing(undefined)}
          saved={() => {
            rows.refresh();
            setMessage(
              "反馈已保存，对应经营报表自动汇总；历史快照保留原版本。",
            );
          }}
        />
      )}
    </section>
  );
}
function FeedbackEditor({ row, studentId, refs, close, saved }: any) {
  const [form, setForm] = useState<any>({
    ...{
      student_id: studentId,
      class_id: "",
      name: "",
      respondent: "parent",
      category: "teaching",
      rating: "",
      body: "",
      recorded_at: localInput(new Date().toISOString()),
      status: "open",
      resolution: "",
    },
    ...row?.data,
    ...(row ? { recorded_at: localInput(row.data.recorded_at) } : {}),
  });
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  const classIds = new Set(
    refs.enrollments
      .filter((e: any) => e.data.student_id === form.student_id)
      .map((e: any) => e.data.class_id),
  );
  const classes = refs.classes.filter(
    (c: any) => classIds.has(c.id) || c.id === row?.data.class_id,
  );
  const canResolve = can("credit.write");
  return (
    <Modal
      title={row ? "反馈详情与处理" : "登记学员家长反馈"}
      close={close}
      wide
    >
      <form
        className="form-body"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          try {
            const data = {
              ...form,
              rating:
                form.rating === "" || form.rating == null
                  ? null
                  : Number(form.rating),
              recorded_at: new Date(form.recorded_at).toISOString(),
            };
            if (row)
              await patch("/records/family_feedback/" + row.id, {
                data,
                version: row.version,
              });
            else await post("/records/family_feedback", { data });
            saved();
            close();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-grid">
          <Field label="关联学员">
            <select
              aria-label="关联学员"
              required
              disabled={!!row || !!studentId}
              value={form.student_id}
              onChange={(e) =>
                setForm({ ...form, student_id: e.target.value, class_id: "" })
              }
            >
              <option value="">请选择学员</option>
              {refs.students
                .filter(
                  (s: any) =>
                    canResolve ||
                    refs.enrollments.some(
                      (e: any) => e.data.student_id === s.id,
                    ),
                )
                .map((s: any) => (
                  <option key={s.id} value={s.id}>
                    {s.data.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="关联班级">
            <select
              aria-label="关联班级"
              disabled={!!row}
              required={!canResolve}
              value={form.class_id}
              onChange={(e) => set("class_id", e.target.value)}
            >
              <option value="">未指定班级</option>
              {classes.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.data.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="反馈来源">
            <select
              aria-label="反馈来源"
              value={form.respondent}
              onChange={(e) => set("respondent", e.target.value)}
            >
              <option value="parent">家长</option>
              <option value="student">学员</option>
            </select>
          </Field>
          <Field label="反馈类型">
            <select
              aria-label="反馈类型"
              value={form.category}
              onChange={(e) => set("category", e.target.value)}
            >
              {Object.entries(feedbackCategories).map(([v, l]) => (
                <option value={v} key={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
          <Field label="评分（可不填）">
            <select
              aria-label="评分（可不填）"
              value={form.rating ?? ""}
              onChange={(e) => set("rating", e.target.value)}
            >
              <option value="">未评分</option>
              {[1, 2, 3, 4, 5].map((v) => (
                <option key={v} value={v}>
                  {v}分
                </option>
              ))}
            </select>
          </Field>
          <Field label="反馈发生时间">
            <input
              required
              type="datetime-local"
              value={form.recorded_at}
              onChange={(e) => set("recorded_at", e.target.value)}
            />
          </Field>
        </div>
        <Field label="反馈主题">
          <input
            required
            maxLength={100}
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </Field>
        <Field label="实际反馈内容">
          <textarea
            required
            maxLength={3000}
            rows={4}
            value={form.body}
            onChange={(e) => set("body", e.target.value)}
          />
        </Field>
        {canResolve && (
          <>
            <Field label="处理状态">
              <select
                aria-label="处理状态"
                value={form.status}
                onChange={(e) => set("status", e.target.value)}
              >
                <option value="open">待处理</option>
                <option value="resolved">已处理</option>
              </select>
            </Field>
            <Field label="处理结果">
              <textarea
                required={form.status === "resolved"}
                maxLength={2000}
                value={form.resolution}
                onChange={(e) => set("resolution", e.target.value)}
              />
            </Field>
          </>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <button className="button primary" disabled={busy}>
          保存反馈
        </button>
      </form>
    </Modal>
  );
}
export function RevenueOverview() {
  const [start, setStart] = useState(""),
    [end, setEnd] = useState("");
  const data = useResource<any>(
    () =>
      api(
        `/revenue/overview?start=${encodeURIComponent(start ? start + "T00:00:00+08:00" : "")}&end=${encodeURIComponent(end ? end + "T23:59:59.999999+08:00" : "")}`,
      ),
    [start, end],
  );
  return (
    <>
      <PageTitle
        eyebrow="REVENUE OVERVIEW"
        title="整体营收总览"
        text="查看本机构实收、退款与净收趋势。当前入口只提供汇总数据。"
      />
      <section className="panel ops-section">
        <div className="ops-toolbar">
          <Field label="营收起始日期">
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="营收结束日期">
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
        </div>
        {data.error ? (
          <Notice tone="error">{data.error}</Notice>
        ) : !data.value ? (
          <Loading />
        ) : (
          <>
            <div className="ops-stats">
              {Object.entries({
                received_fen: "实收",
                refund_fen: "退款",
                net_fen: "净收",
              }).map(([k, l]) => (
                <div className="ops-stat" key={k}>
                  <span>{l}</span>
                  <strong>{money(data.value.totals[k])}</strong>
                </div>
              ))}
            </div>
            {data.value.chart.length ? (
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart
                    data={data.value.chart.map((r: any) => ({
                      date: r.date,
                      received: r.received_fen / 100,
                      refund: r.refund_fen / 100,
                      net: r.net_fen / 100,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis unit="元" />
                    <Tooltip />
                    <Legend />
                    <Area
                      dataKey="received"
                      name="实收（元）"
                      stroke="#34654a"
                      fill="#d4e2cf"
                    />
                    <Area
                      dataKey="refund"
                      name="退款（元）"
                      stroke="#c37454"
                      fill="#fae7df"
                    />
                    <Area
                      dataKey="net"
                      name="净收（元）"
                      stroke="#4d7290"
                      fill="#dce8f1"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty title="所选期间暂无收退款记录" />
            )}
          </>
        )}
      </section>
    </>
  );
}

export function SavedOperatingReports() {
  const data = useResource<any[]>(() => api("/report-snapshots"), [], 15000);
  const [selected, setSelected] = useState<any>(null);
  return (
    <section className="panel ops-section">
      <h2>自动生成与历史报表</h2>
      <p>
        默认每周一09:00生成上周周报，每月1日09:00生成上月月报。补录形成更正版，原版本保留。
        <a href="#operations">调整生成时间与推送设置 →</a>
      </p>
      {data.error && <Notice tone="error">{data.error}</Notice>}
      {data.value?.length ? (
        <div className="saved-reports">
          {data.value.slice(0, 12).map((r) => (
            <button
              className="button"
              key={r.id}
              onClick={() => setSelected(r)}
            >
              {r.kind === "weekly" ? "周报" : "月报"} {r.period} · V{r.version}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">
          到达生成时间后自动留存，也可以点击“保存报表版本”。
        </p>
      )}
      {selected && (
        <Modal
          title={
            (selected.kind === "weekly" ? "周报" : "月报") +
            " " +
            selected.period +
            " · V" +
            selected.version
          }
          close={() => setSelected(null)}
          wide
        >
          <div className="form-body">
            <p>保存于 {date(selected.created_at, true)} · 本页显示已保存版本</p>
            <h3>经营摘要</h3>
            {selected.payload.summary?.length ? (
              <ul>
                {selected.payload.summary.map((line: string, j: number) => (
                  <li key={j}>{line}</li>
                ))}
              </ul>
            ) : (
              <p>此历史版本未包含经营摘要。</p>
            )}
            <ReportFeedbackSummary data={selected.payload.family_feedback} />
            {selected.payload.finance && (
              <section className="ops-section">
                <h3>财务趋势</h3>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={230}>
                    <BarChart
                      data={selected.payload.finance.chart.map((r: any) => ({
                        date: r.date,
                        net: r.net_fen / 100,
                        expense: r.expense_fen / 100,
                      }))}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="date" />
                      <YAxis unit="元" />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="net" name="净收（元）" fill="#34654a" />
                      <Bar dataKey="expense" name="费用（元）" fill="#c37454" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            )}
          </div>
        </Modal>
      )}
    </section>
  );
}
