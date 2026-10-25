import { AIReportSummary } from "./AIControls";
import React, { useEffect, useState } from "react";
import {
  Users,
  Upload,
  Download,
  CheckCircle2,
  BarChart3,
  Calendar,
  Plus,
  FileText,
  Bell,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
  Legend,
} from "recharts";
import {
  api,
  post,
  patch,
  can,
  money,
  date,
  uid,
  Row,
  SessionInfo,
} from "./api";
import {
  PageTitle,
  Loading,
  Notice,
  Modal,
  Field,
  Badge,
  Empty,
  useResource,
} from "./ui";
import { recordsAll } from "./api";
import { RecordEditor } from "./BusinessPage";
import {
  FamilyFeedbackPanel,
  ReportFeedbackSummary,
  SavedOperatingReports,
} from "./ManagementPage";

export const localDay = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(
    new Date(),
  );
export const detail = (kind: string, id: string) =>
  window.dispatchEvent(
    new CustomEvent("finance-detail", { detail: { kind, id } }),
  );
const percent = (v: any) =>
  v === null || v === undefined ? "暂无数据" : `${v}%`;
const statLabels: Record<string, string> = {
  new_leads: "新增线索",
  trial_attendees: "到场试听",
  lead_conversion_rate: "线索转化率",
  trial_conversion_rate: "试听转化率",
  new_students: "新增在读",
  additional_enrollments: "续费 / 加报 / 重新入读",
  opening_students: "期初在读",
  population: "本月学员基数",
  withdrawn_students: "退读学员",
  attrition_rate: "流失率",
  expected_attendance: "应到人次",
  actual_attendance: "实到人次",
  attendance_rate: "出勤率",
  excused_absences: "请假人次",
  unexcused_absences: "未请假缺勤",
  feedback_expected: "应完成课返",
  feedback_completed: "已完成课返",
  feedback_overdue: "课返逾期",
  feedback_completion_rate: "课返完成率",
  makeup_completed: "补课完成",
  makeup_pending: "待补课",
  refund_count: "退款笔数",
};
function StatCards({ values, keys }: { values: any; keys: string[] }) {
  return (
    <div className="ops-stats">
      {keys.map((k) => (
        <div className="panel ops-stat" key={k}>
          <span>{statLabels[k] || k}</span>
          <strong>
            {k.endsWith("_rate") ? percent(values?.[k]) : (values?.[k] ?? "—")}
          </strong>
        </div>
      ))}
    </div>
  );
}

export function StudentDirectory({ demo = false }: { demo?: boolean }) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState("active"),
    [teacher, setTeacher] = useState(""),
    [cls, setCls] = useState<string | null>(null),
    [student, setStudent] = useState(""),
    [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const groups = useResource<any[]>(
    () =>
      api(
        `/classes/students?q=${encodeURIComponent(q)}&status=${status}&teacher_id=${teacher}`,
      ),
    [q, status, teacher],
  );
  const staff = useResource<any[]>(() => api("/members"), []);
  const profile = useResource<any>(
    () =>
      student ? api(`/students/${student}/profile`) : Promise.resolve(null),
    [student],
  );
  const list = groups.value?.filter((c) => cls === null || c.id === cls) || [];
  return (
    <>
      <PageTitle
        eyebrow="STUDENTS & FAMILIES"
        title="以班级为起点，照顾每个家庭"
        text="学员、家长、课时与出勤，放在同一份档案。"
      />
      <div className="panel ops-toolbar">
        <input
          className="input"
          aria-label="搜索学员或家长"
          placeholder="搜索学员、家长或电话"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="input"
          aria-label="在读状态"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="active">在读</option>
          <option value="withdrawn">已退读</option>
          <option value="all">全部状态</option>
        </select>
        {can("class.read") && (
          <select
            className="input"
            aria-label="按老师筛选"
            value={teacher}
            onChange={(e) => setTeacher(e.target.value)}
          >
            <option value="">全部老师</option>
            {staff.value
              ?.filter((m) =>
                m.roles?.some((r: string) => ["owner", "teacher"].includes(r)),
              )
              .map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
          </select>
        )}
        {can("student.write") && (
          <button className="button primary" onClick={() => setEditing(null)}>
            <Plus size={15} />
            新增学员档案
          </button>
        )}
      </div>
      {groups.error && <Notice tone="error">{groups.error}</Notice>}
      {groups.loading ? (
        <Loading />
      ) : (
        <div className="ops-directory">
          <aside className="panel class-list">
            <button
              className={cls === null ? "selected" : ""}
              onClick={() => setCls(null)}
            >
              全部班级{" "}
              <span>{groups.value?.reduce((n, c) => n + c.count, 0)}</span>
            </button>
            {groups.value?.map((c) => (
              <button
                key={c.id}
                className={cls === c.id ? "selected" : ""}
                onClick={() => setCls(c.id)}
              >
                {c.name}
                <span>{c.count}</span>
              </button>
            ))}
          </aside>
          <div>
            {list.map((c) => (
              <section className="panel class-roster" key={c.id}>
                <header>
                  <h2>{c.name}</h2>
                  <span>{c.count} 位学员</span>
                </header>
                {!c.students.length ? (
                  <Empty
                    title="当前没有匹配的学员"
                    text="可调整筛选条件，或由教务确认分班。"
                  />
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>学员</th>
                          <th>年级</th>
                          <th>家长</th>
                          <th>家长手机号</th>
                          <th>剩余课时</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.students.map((s: any) => (
                          <tr key={s.id}>
                            <td>
                              <button
                                className="button link"
                                onClick={() => setStudent(s.id)}
                              >
                                {s.data.name}
                              </button>
                            </td>
                            <td>{s.data.grade || "—"}</td>
                            <td>
                              {s.data.guardian ||
                                s.data.guardians
                                  ?.map((g: any) => g.name)
                                  .join("、") ||
                                "—"}
                            </td>
                            <td
                              className="phone-number"
                              title={
                                demo ? "虚构示例手机号，仅用于演示" : undefined
                              }
                            >
                              {s.data.contact || "—"}
                            </td>
                            <td>
                              {s.enrollments
                                .map((e: any) => e.remaining)
                                .join(" / ") || "未开通"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ))}
          </div>
        </div>
      )}
      {editing !== undefined && (
        <RecordEditor
          kind="student"
          row={editing || undefined}
          close={() => setEditing(undefined)}
          saved={() => groups.refresh()}
        />
      )}
      {student && (
        <Modal
          title={profile.value?.data?.name || "学员档案"}
          close={() => setStudent("")}
          wide
        >
          {profile.error ? (
            <Notice tone="error">{profile.error}</Notice>
          ) : !profile.value ? (
            <Loading />
          ) : (
            <div className="form-body">
              <div className="ops-profile-head">
                <div className="avatar">
                  {profile.value.data.name.slice(0, 1)}
                </div>
                <div>
                  <h2>{profile.value.data.name}</h2>
                  <p>{profile.value.data.grade || "年级待补充"}</p>
                </div>
                {can("student.write") && (
                  <button
                    className="button small"
                    onClick={() => {
                      setEditing(profile.value);
                      setStudent("");
                    }}
                  >
                    编辑档案
                  </button>
                )}
              </div>
              <h3>家长与手机号</h3>
              {(profile.value.data.guardians?.length
                ? profile.value.data.guardians
                : [
                    {
                      name: profile.value.data.guardian,
                      contact: profile.value.data.contact,
                      relationship: "家长",
                    },
                  ]
              ).map((g: any, j: number) => (
                <div className="ops-keyline" key={j}>
                  <strong>{g.name || "待补充"}</strong>
                  <span>{g.relationship || "家长"}</span>
                  <a
                    className="phone-number"
                    title={demo ? "虚构示例手机号，仅用于演示" : undefined}
                    href={!demo && g.contact ? `tel:${g.contact}` : undefined}
                  >
                    {g.contact || "家长手机号未填写"}
                  </a>
                </div>
              ))}
              {profile.value.data.notes && (
                <>
                  <h3>档案备注</h3>
                  <p>{profile.value.data.notes}</p>
                </>
              )}
              <h3>报名与课时</h3>
              {profile.value.enrollments?.map((e: any) => (
                <div className="ops-keyline" key={e.id}>
                  <strong>{e.data.program_name || e.data.name}</strong>
                  <Badge value={e.data.status || "active"} />
                  <span>剩余 {e.data.remaining} 课时</span>
                </div>
              ))}
              <h3>出勤记录</h3>
              {profile.value.attendance?.length ? (
                <ul>
                  {profile.value.attendance.map((a: any) => (
                    <li key={a.id}>{date(a.created_at, true)} · 已签到</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">当前授权范围内暂无出勤记录。</p>
              )}
              {profile.value.family_feedback_allowed && (
                <FamilyFeedbackPanel studentId={student} />
              )}
              {profile.value.orders && (
                <>
                  <h3>财务关联</h3>
                  {profile.value.orders.map((o: any) => (
                    <button
                      key={o.id}
                      className="button"
                      onClick={() => detail("order", o.id)}
                    >
                      {o.data.name} · {money(o.data.paid_fen)}
                    </button>
                  ))}
                </>
              )}
            </div>
          )}
        </Modal>
      )}
    </>
  );
}

export function FeedbackKPIPanel() {
  const rows = useResource<any[]>(() => api("/education/feedback-kpis"), []),
    [notice, setNotice] = useState("");
  return (
    <section className="panel ops-section">
      <header>
        <div>
          <h2>课返完成 KPI</h2>
          <p>每班每次课一次，仅记录完成状态和时间。</p>
        </div>
        <Badge value="active" label="默认课后24小时" />
      </header>
      {notice && <Notice>{notice}</Notice>}
      {rows.error && <Notice tone="error">{rows.error}</Notice>}
      {!rows.value?.length ? (
        <Empty
          title="暂无需要确认的课返"
          text="已结束的有效课次会自动生成考核记录，取消课次不考核。"
        />
      ) : (
        <>
          <StatCards
            values={{
              feedback_expected: rows.value.length,
              feedback_completed: rows.value.filter((r) => r.completed_at)
                .length,
              feedback_overdue: rows.value.filter((r) => r.overdue).length,
            }}
            keys={[
              "feedback_expected",
              "feedback_completed",
              "feedback_overdue",
            ]}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>课次</th>
                  <th>截止时间</th>
                  <th>完成时间</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.value.map((r) => (
                  <tr key={r.id}>
                    <td>{r.lesson_name}</td>
                    <td>{date(r.due_at, true)}</td>
                    <td>{date(r.completed_at, true)}</td>
                    <td>
                      <Badge
                        value={
                          r.completed_at
                            ? "completed"
                            : r.overdue
                              ? "failed"
                              : "pending"
                        }
                        label={
                          r.completed_at
                            ? "已完成"
                            : r.overdue
                              ? "逾期"
                              : "待完成"
                        }
                      />
                    </td>
                    <td>
                      <button
                        className="button small"
                        disabled={!!r.completed_at && !can("enrollment.write")}
                        title={
                          r.completed_at && !can("enrollment.write")
                            ? "如需更正请联系教务"
                            : undefined
                        }
                        onClick={async () => {
                          try {
                            const completed = !r.completed_at;
                            let note = "";
                            if (!completed || can("enrollment.write")) {
                              note =
                                window.prompt(
                                  "填写确认或纠正说明",
                                  "课后已完成家长反馈",
                                ) || "";
                              if (!note) return;
                            }
                            await patch(`/education/feedback-kpis/${r.id}`, {
                              completed,
                              version: r.version,
                              note,
                            });
                            rows.refresh();
                          } catch (e) {
                            setNotice((e as Error).message);
                          }
                        }}
                      >
                        {r.completed_at ? "纠正记录" : "确认课返已完成"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

export function AdmissionIntake() {
  const [templateId, setTemplateId] = useState("");
  const templates = useResource<any[]>(
    () => api("/studio/definitions?kind=form"),
    [],
  );
  const batches = useResource<any[]>(
      () => api("/admissions/imports"),
      [],
      5000,
    ),
    [selected, setSelected] = useState(""),
    [data, setData] = useState<any>(null),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [edits, setEdits] = useState<any[]>([]),
    [checked, setChecked] = useState<Record<number, boolean>>({});
  const reviewLabels: Record<string, string> = {
    external_row_id: "线索编号",
    student_name: "学员",
    grade: "年级",
    name: "家长",
    relationship: "关系",
    contact: "电话",
    source: "来源",
    class_name: "意向班级",
    owner_name: "招生负责人",
    trial_at: "预约时间",
    stage: "跟进阶段",
    registration_note: "报名信息（待核对）",
    loss_reason: "流失原因",
    notes: "备注",
  };
  const reviewKeys = Array.from(
    new Set([
      ...Object.keys(reviewLabels),
      ...edits.flatMap((r) => Object.keys(r.data || {})),
    ]),
  );
  async function load(id: string) {
    try {
      const v = await api(`/admissions/imports/${id}`);
      setData(v);
      setEdits(v.rows.map((r: any) => ({ ...r, data: { ...r.data } })));
      setChecked(
        Object.fromEntries(
          v.rows.map((r: any, j: number) => [
            j,
            !r.blocked && r.status !== "imported",
          ]),
        ),
      );
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  useEffect(() => {
    if (!selected) return;
    load(selected);
    const t = setInterval(() => {
      if (!data || ["queued", "processing"].includes(data.status))
        load(selected);
    }, 3000);
    return () => clearInterval(t);
  }, [selected, data?.status]);
  return (
    <section className="panel ops-section">
      <header>
        <div>
          <h2>招生表 · 扫描录入</h2>
          <select
            aria-label="招生表模板"
            className="input"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          >
            <option value="">默认招生表</option>
            {templates.value
              ?.filter((t) => t.binding === "lead" && t.published_version)
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · V{t.published_version}
                </option>
              ))}
          </select>
          <p>下载统一模板，上传Excel或扫描件，核对后进入实时招生表。</p>
        </div>
        <div className="button-row">
          <a
            className="button small"
            href={
              "/api/v1/admissions/template/xlsx?definition_id=" + templateId
            }
          >
            <Download size={14} />
            Excel模板
          </a>
          <a
            className="button small"
            href={"/api/v1/admissions/template/pdf?definition_id=" + templateId}
            target="_blank"
            rel="noreferrer"
          >
            打印模板
          </a>
          {can("lead.write") && (
            <label className="button primary small">
              <Upload size={14} />
              {busy ? "上传中…" : "上传招生表"}
              <input
                hidden
                type="file"
                accept=".xlsx,image/png,image/jpeg,application/pdf"
                disabled={busy}
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setBusy(true);
                  try {
                    const body = new FormData();
                    body.append("file", f);
                    body.append("definition_id", templateId);
                    const r = await api("/admissions/imports", {
                      method: "POST",
                      body,
                    });
                    setSelected(r.id);
                    batches.refresh();
                  } catch (e) {
                    setNotice((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            </label>
          )}
        </div>
      </header>
      {notice && <Notice>{notice}</Notice>}
      {batches.value?.length ? (
        <div className="ops-import-list">
          {batches.value.slice(0, 8).map((b) => (
            <button
              key={b.id}
              className="button small"
              onClick={() => setSelected(b.id)}
            >
              {date(b.created_at, true)} · <Badge value={b.status} />
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">
          支持25MB以内、最多20页或500行。扫描中的报名和退费标记不会直接记账。
        </p>
      )}
      {selected && (
        <Modal
          title="核对招生表识别结果"
          close={() => {
            setSelected("");
            setData(null);
          }}
          wide
        >
          {!data ? (
            <Loading />
          ) : (
            <div className="form-body">
              {notice && <Notice>{notice}</Notice>}
              <Notice>
                请核对原图和每一行。正式报名、收退款以系统业务记录为准；电话相同的不同孩子不会自动合并。
              </Notice>
              {data.error && <Notice tone="error">{data.error}</Notice>}
              {["queued", "processing"].includes(data.status) ? (
                <Loading />
              ) : (
                <>
                  <div className="ops-import-preview">
                    <aside>
                      <a
                        className="button"
                        href={`/api/v1/assets/${data.asset_id}/download`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        打开原文件核对 ↗
                      </a>
                      <p>模板版本：{data.template_version}</p>
                      <img
                        alt="上传的招生表原件（Excel请打开原文件）"
                        src={`/api/v1/assets/${data.asset_id}/download`}
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                      <p>识别进度：{data.progress}%</p>
                      <Badge value={data.status} />
                    </aside>
                    <div className="table-scroll">
                      <table className="import-grid">
                        <thead>
                          <tr>
                            <th>导入</th>
                            {reviewKeys.map((k) => (
                              <th key={k}>
                                {reviewLabels[k] || k.replace("custom:", "")}
                              </th>
                            ))}
                            <th>核对提醒</th>
                            <th>匹配原记录</th>
                            <th>结果</th>
                          </tr>
                        </thead>
                        <tbody>
                          {edits.map((r, j) => (
                            <tr key={j}>
                              <td>
                                <input
                                  type="checkbox"
                                  aria-label={`导入第${j + 1}行`}
                                  disabled={
                                    r.blocked || r.status === "imported"
                                  }
                                  checked={!!checked[j]}
                                  onChange={(e) =>
                                    setChecked({
                                      ...checked,
                                      [j]: e.target.checked,
                                    })
                                  }
                                />
                              </td>
                              {reviewKeys.map((k) => (
                                <td key={k}>
                                  <input
                                    aria-label={`第${j + 1}行${k}`}
                                    className={
                                      r.cell_issues?.[k]
                                        ? "scan-cell-warning"
                                        : ""
                                    }
                                    title={r.cell_issues?.[k] || ""}
                                    value={r.data[k] || ""}
                                    onChange={(e) =>
                                      setEdits(
                                        edits.map((v, n) =>
                                          n === j
                                            ? {
                                                ...v,
                                                data: {
                                                  ...v.data,
                                                  [k]: e.target.value,
                                                },
                                              }
                                            : v,
                                        ),
                                      )
                                    }
                                  />
                                </td>
                              ))}
                              <td>
                                <small>{r.issues?.join("；")}</small>
                              </td>
                              <td>
                                <select
                                  value={r.match_id || ""}
                                  onChange={(e) =>
                                    setEdits(
                                      edits.map((v, n) =>
                                        n === j
                                          ? { ...v, match_id: e.target.value }
                                          : v,
                                      ),
                                    )
                                  }
                                >
                                  <option value="">新建家庭线索</option>
                                  {r.match_id && (
                                    <option value={r.match_id}>
                                      更新已匹配记录
                                    </option>
                                  )}
                                  {r.candidates
                                    ?.filter((c: any) => c.id !== r.match_id)
                                    .map((c: any) => (
                                      <option key={c.id} value={c.id}>
                                        {c.name}
                                      </option>
                                    ))}
                                </select>
                              </td>
                              <td>
                                {r.error || (
                                  <Badge value={r.status || "pending"} />
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="button-row">
                    {can("lead.write") && edits.length > 0 && (
                      <button
                        className="button primary"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            const rows = edits.flatMap((r, index) =>
                              checked[index]
                                ? [
                                    {
                                      index,
                                      data: r.data,
                                      match_id: r.match_id,
                                    },
                                  ]
                                : [],
                            );
                            const result = await post(
                              `/admissions/imports/${selected}/confirm`,
                              { version: data.version, rows },
                            );
                            setNotice(
                              `已处理${result.results.length}行，冲突行可核对后单独重试`,
                            );
                            await load(selected);
                            batches.refresh();
                            window.dispatchEvent(new Event("ops-refresh"));
                          } catch (e) {
                            setNotice((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        确认导入选中行
                      </button>
                    )}
                    {data.status === "failed" && (
                      <button
                        className="button"
                        onClick={async () => {
                          await post(`/admissions/imports/${selected}/retry`);
                          load(selected);
                        }}
                      >
                        重新识别
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </Modal>
      )}
    </section>
  );
}

export function ReportPage() {
  const [kind, setKind] = useState("weekly"),
    [period, setPeriod] = useState(localDay()),
    [cls, setCls] = useState(""),
    [notice, setNotice] = useState("");
  const data = useResource<any>(
    () => api(`/reports/${kind}?period=${period}&class_id=${cls}`),
    [kind, period, cls],
  );
  const classes = useResource<any[]>(
    () =>
      can("class.read")
        ? api("/records/class").then((x) => x.items)
        : Promise.resolve([]),
    [],
  );
  const d = data.value,
    keys =
      kind === "weekly"
        ? [
            "new_leads",
            "trial_attendees",
            "lead_conversion_rate",
            "trial_conversion_rate",
            "new_students",
            "withdrawn_students",
            "refund_count",
            "feedback_completion_rate",
          ]
        : [
            "opening_students",
            "new_students",
            "withdrawn_students",
            "attrition_rate",
            "attendance_rate",
            "excused_absences",
            "unexcused_absences",
            "feedback_completion_rate",
          ];
  return (
    <>
      <PageTitle
        eyebrow="WEEKLY & MONTHLY"
        title="用同一组数据，看清经营变化"
        text="招生、财务、学员家长反馈与教务按真实记录汇总；周一及每月1日自动生成上一周期报表。"
      />
      <div className="panel ops-toolbar">
        <div className="tabs">
          {[
            ["weekly", "周报"],
            ["monthly", "月报"],
          ].map(([v, l]) => (
            <button
              key={v}
              className={"tab " + (kind === v ? "active" : "")}
              onClick={() => {
                setKind(v);
                setPeriod(
                  v === "monthly" ? localDay().slice(0, 7) : localDay(),
                );
              }}
            >
              {l}
            </button>
          ))}
        </div>
        <input
          className="input"
          type={kind === "monthly" ? "month" : "date"}
          aria-label="报表周期"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        />
        {can("class.read") && (
          <select
            className="input"
            aria-label="报表班级"
            value={cls}
            onChange={(e) => setCls(e.target.value)}
          >
            <option value="">负责范围内全部班级</option>
            {classes.value?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.data.name}
              </option>
            ))}
          </select>
        )}
        {can("tenant.manage") && (
          <button
            className="button"
            onClick={async () => {
              try {
                const r = await post(
                  `/report-snapshots/${kind}?period=${period}`,
                );
                setNotice(`已保存第${r.version}版报表快照`);
                window.dispatchEvent(new Event("ops-refresh"));
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          >
            保存报表版本
          </button>
        )}
      </div>
      {notice && <Notice>{notice}</Notice>}
      {can("tenant.manage") && <SavedOperatingReports />}
      {data.error ? (
        <Notice tone="error">{data.error}</Notice>
      ) : !d ? (
        <Loading />
      ) : (
        <>
          <p className="muted">
            {date(d.from)} 至{" "}
            {date(new Date(new Date(d.to).getTime() - 1).toISOString())} ·
            数据更新于 {date(d.as_of, true)}
          </p>
          {d.baseline_status !== "confirmed" && (
            <Notice>
              历史期初在读资料待负责人校准。流失率显示“暂无数据”，不会按零值触发或解除异常。
            </Notice>
          )}
          {d.summary?.length > 0 && (
            <section className="panel ops-section">
              <h2>经营摘要</h2>
              <p className="muted">
                系统按已登记事实自动汇总，金额与比例由业务规则计算。
              </p>
              <ul>
                {d.summary.map((line: string, j: number) => (
                  <li key={j}>{line}</li>
                ))}
              </ul>
            </section>
          )}
          <StatCards
            values={d.metrics}
            keys={keys.filter((k) => k in d.metrics)}
          />
          <ReportFeedbackSummary data={d.family_feedback} />
          {can("education.read") && (
            <section className="panel ops-section">
              <h2>{kind === "monthly" ? "班级月度出勤" : "班级本周出勤"}</h2>
              <p>请假计入未出勤，取消课程不计入。按上课时的班级名单计算。</p>
              {d.classes?.length ? (
                <>
                  <div className="chart-box">
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={d.classes}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="expected" name="应到" fill="#d4e2cf" />
                        <Bar dataKey="actual" name="实到" fill="#34654a" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>班级</th>
                          <th>应到</th>
                          <th>实到</th>
                          <th>出勤率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.classes.map((c: any) => (
                          <tr key={c.id}>
                            <td>{c.name}</td>
                            <td>{c.expected}</td>
                            <td>{c.actual}</td>
                            <td>{percent(c.attendance_rate)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <Empty
                  title="暂无可计算的出勤"
                  text="结束的课次、班级名册和签到齐备后自动汇总。"
                />
              )}
            </section>
          )}
          <div className="ops-two">
            {can("order.read") && (
              <section className="panel ops-section">
                <h2>退读与退款原因</h2>
                {!d.withdrawals?.length && !d.refunds?.length ? (
                  <p className="muted">本期暂无记录。</p>
                ) : (
                  <ul>
                    {d.withdrawals?.map((r: any, j: number) => (
                      <li key={"w" + j}>
                        {date(r.date)} · 退读 · {r.reason}
                      </li>
                    ))}
                    {d.refunds?.map((r: any, j: number) => (
                      <li key={"r" + j}>
                        {date(r.date)} ·{" "}
                        {r.withdrawal ? "退读退费" : "继续就读的退款"} ·{" "}
                        {r.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
            {can("lead.read") && (
              <section className="panel ops-section">
                <h2>未成交原因</h2>
                {d.lost_leads?.length ? (
                  <ul>
                    {d.lost_leads.map((l: any) => (
                      <li key={l.id}>
                        {l.name} · {l.reason}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">本期暂无未成交记录。</p>
                )}
              </section>
            )}
          </div>
          {(d.finance || d.revenue) && (
            <section className="panel ops-section">
              <h2>财务摘要</h2>
              <div className="ops-stats">
                {Object.entries((d.finance || d.revenue).totals).map(
                  ([k, v]) => (
                    <div className="ops-stat" key={k}>
                      <span>
                        {
                          {
                            received_fen: "实收",
                            refund_fen: "退款",
                            net_fen: "净收",
                            expense_fen: "已确认费用",
                            cash_difference_fen: "收支差额",
                          }[k]
                        }
                      </span>
                      <strong>{money(v as number)}</strong>
                    </div>
                  ),
                )}
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}

export function FinanceOverview() {
  const [detailDay, setDetailDay] = useState(""),
    [detailMetric, setDetailMetric] = useState("");
  const metricLabels: Record<string, string> = {
    received_fen: "实收",
    refund_fen: "退款",
    net_fen: "净收",
    expense_fen: "已确认费用",
    cash_difference_fen: "收支差额",
  };
  const chinaDay = (value: string) => {
    const d = new Date(value);
    return Number.isFinite(d.getTime())
      ? new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(
          d,
        )
      : "";
  };
  const [start, setStart] = useState(localDay().slice(0, 7) + "-01"),
    [end, setEnd] = useState(localDay()),
    [cls, setCls] = useState(""),
    [channel, setChannel] = useState("");
  const choices = useResource<any>(() => api("/finance/options"), []);
  const data = useResource<any>(
    () =>
      api(
        `/finance/overview?start=${start}T00:00:00%2B08:00&end=${end}T23:59:59%2B08:00&class_id=${cls}&channel=${channel}`,
      ),
    [start, end, cls, channel],
  );
  return (
    <section className="panel ops-section">
      <header>
        <div>
          <h2>收支概览</h2>
          <p>点击明细核对每笔流水、票据和课时快照。</p>
        </div>
      </header>
      <div className="ops-toolbar">
        <Field label="开始日期">
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <Field label="结束日期">
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </Field>
        <Field label="财务班级">
          <select value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="">全部班级</option>
            {choices.value?.classes.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="来源渠道">
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="">全部渠道</option>
            {choices.value?.channels.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {data.error && <Notice tone="error">{data.error}</Notice>}
      {data.value && (
        <>
          <div className="ops-stats">
            {Object.entries(data.value.totals).map(([k, v]) => (
              <button
                className="ops-stat"
                key={k}
                aria-label={"查看" + metricLabels[k] + "明细"}
                onClick={() => {
                  setDetailMetric(k);
                  document
                    .getElementById("financial-transactions")
                    ?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                <span>
                  {
                    {
                      received_fen: "实收",
                      refund_fen: "退款",
                      net_fen: "净收",
                      expense_fen: "已确认费用",
                      cash_difference_fen: "收支差额",
                    }[k]
                  }
                </span>
                <strong>{money(v as number)}</strong>
              </button>
            ))}
          </div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart
                data={data.value.chart}
                onClick={(event: any) => {
                  const day =
                    event?.activeLabel ||
                    event?.activePayload?.[0]?.payload?.date;
                  if (typeof day === "string") setDetailDay(day);
                  document
                    .getElementById("financial-transactions")
                    ?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" />
                <YAxis tickFormatter={(v) => (v / 100).toFixed(0)} />
                <Tooltip formatter={(v: any) => money(Number(v))} />
                <Legend />
                <Area
                  dataKey="received_fen"
                  name="实收"
                  stroke="#34654a"
                  fill="#dce9d3"
                />
                <Area
                  dataKey="refund_fen"
                  name="退款"
                  stroke="#b88355"
                  fill="#f5e8d9"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {(detailDay || detailMetric) && (
            <div className="ops-keyline">
              <strong>
                {detailDay} · {metricLabels[detailMetric] || "全部收支"}
              </strong>
              <button
                className="button small"
                onClick={() => {
                  setDetailDay("");
                  setDetailMetric("");
                }}
              >
                显示全部明细
              </button>
            </div>
          )}
          <div id="financial-transactions" className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单 / 费用</th>
                  <th>类型</th>
                  <th>金额</th>
                  <th>日期</th>
                  <th>票据与明细</th>
                </tr>
              </thead>
              <tbody>
                {data.value.transactions
                  .filter(
                    (t: any) =>
                      (!detailDay || chinaDay(t.date) === detailDay) &&
                      detailMetric !== "expense_fen" &&
                      (detailMetric !== "received_fen" ||
                        (t.category || t.type) === "payment") &&
                      (detailMetric !== "refund_fen" ||
                        (t.category || t.type) === "refund"),
                  )
                  .map((t: any) => (
                    <tr key={t.id}>
                      <td>{t.name}</td>
                      <td>
                        {
                          { payment: "收款", refund: "退款", reversal: "冲正" }[
                            t.type as string
                          ]
                        }
                      </td>
                      <td>{money(t.amount_fen)}</td>
                      <td>{date(t.date, true)}</td>
                      <td>
                        <button
                          className="button link"
                          onClick={() => detail("ledger", t.id)}
                        >
                          查看票据与详情
                        </button>
                      </td>
                    </tr>
                  ))}
                {data.value.expenses
                  .filter(
                    (e: any) =>
                      (!detailDay ||
                        chinaDay(e.data.date || e.created_at) === detailDay) &&
                      !["received_fen", "refund_fen", "net_fen"].includes(
                        detailMetric,
                      ),
                  )
                  .map((e: any) => (
                    <tr key={e.id}>
                      <td>{e.data.name}</td>
                      <td>费用</td>
                      <td>{money(e.data.amount_fen)}</td>
                      <td>{e.data.date}</td>
                      <td>
                        <button
                          className="button link"
                          onClick={() => detail("expense", e.id)}
                        >
                          查看票据与详情
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

export function FinanceDetailHost() {
  const [selected, setSelected] = useState<{ kind: string; id: string } | null>(
      null,
    ),
    [notice, setNotice] = useState("");
  useEffect(() => {
    const f = (e: Event) => setSelected((e as CustomEvent).detail);
    window.addEventListener("finance-detail", f);
    return () => window.removeEventListener("finance-detail", f);
  }, []);
  const data = useResource<any>(
    () =>
      selected
        ? api(`/finance/details/${selected.kind}/${selected.id}`)
        : Promise.resolve(null),
    [selected?.kind, selected?.id],
  );
  if (!selected) return null;
  const d = data.value;
  return (
    <Modal title="财务明细与票据" close={() => setSelected(null)} wide>
      <div className="form-body">
        {notice && <Notice>{notice}</Notice>}
        {data.error ? (
          <Notice tone="error">{data.error}</Notice>
        ) : !d ? (
          <Loading />
        ) : (
          <>
            <h2>
              {d.record.data?.name || d.order?.data?.name || "收退款流水"}
            </h2>
            <div className="ops-keyline">
              <strong>
                {money(
                  d.record.amount_fen ??
                    d.record.data?.amount_fen ??
                    d.record.data?.paid_fen,
                )}
              </strong>
              <span>
                {d.record.note ||
                  d.record.data?.notes ||
                  "完整流水保留，调整使用冲正。"}
              </span>
            </div>
            {d.refund_context && (
              <>
                <h3>退款时的课时快照</h3>
                <p>
                  原因：{d.refund_context.reason} ·{" "}
                  {d.refund_context.withdrawal ? "退读退费" : "继续就读"}
                </p>
                {d.refund_context.snapshot?.enrollments?.map((e: any) => (
                  <div className="ops-keyline" key={e.enrollment_id}>
                    <span>购买 {e.purchased_units}</span>
                    <span>已上 {e.attended_units}</span>
                    <span>未上 {e.remaining_units}</span>
                  </div>
                ))}
              </>
            )}
            {d.order && (
              <section className="ops-section">
                <h3>关联订单收款情况</h3>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart
                      data={[
                        {
                          name: "应收",
                          amount: (d.order.data.due_fen || 0) / 100,
                        },
                        {
                          name: "当前净收",
                          amount: (d.order.data.paid_fen || 0) / 100,
                        },
                      ]}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" />
                      <YAxis unit="元" />
                      <Tooltip />
                      <Bar dataKey="amount" name="金额（元）" fill="#34654a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            )}
            <h3>票据原件</h3>
            <div className="ops-receipts">
              {d.assets.map((a: any) => (
                <a
                  key={a.id}
                  href={`/api/v1/assets/${a.id}/download`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {a.mime.startsWith("image/") ? (
                    <img src={`/api/v1/assets/${a.id}/download`} alt={a.name} />
                  ) : (
                    <FileText size={40} />
                  )}
                  <span>{a.name} ↗</span>
                </a>
              ))}
            </div>
            {!d.assets.length && (
              <p className="muted">暂无关联票据，可上传补充。</p>
            )}
            {can("finance.write") && (
              <label className="button">
                <Upload size={14} />
                关联票据
                <input
                  hidden
                  type="file"
                  accept="image/png,image/jpeg,application/pdf"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    try {
                      const body = new FormData();
                      body.append("file", file);
                      body.append("purpose", "receipt");
                      const asset = await api("/assets", {
                        method: "POST",
                        body,
                      });
                      await post("/finance/receipt-links", {
                        kind: selected.kind,
                        record_id: selected.id,
                        asset_id: asset.id,
                      });
                      data.refresh();
                      setNotice("票据已关联");
                    } catch (e) {
                      setNotice((e as Error).message);
                    }
                  }}
                />
              </label>
            )}
            {d.ocr.length > 0 && (
              <>
                <h3>识别与核对</h3>
                {d.ocr.map((r: any, j: number) => (
                  <div key={j}>
                    <Badge value={r.status} />
                    <p>
                      {r.output?.record_id
                        ? "识别结果已生成费用草稿，请核对后确认。"
                        : "识别记录已保留。"}
                    </p>
                  </div>
                ))}
              </>
            )}
            <h3>审批记录</h3>
            {d.approvals?.map((a: any) => (
              <div className="ops-keyline" key={a.id}>
                <span>
                  V{a.definition_version} · {date(a.created_at, true)}
                </span>
                <Badge value={a.status} />
              </div>
            ))}
            <h3>操作记录</h3>
            <ul>
              {d.audit.map((a: any) => (
                <li key={a.id}>
                  {date(a.created_at, true)} · {a.action}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Modal>
  );
}

export function OperationsSettings() {
  const data = useResource<any>(() => api("/operations/settings"), []),
    classOptions = useResource<any[]>(
      () => api("/operations/class-choices"),
      [],
    ),
    alerts = useResource<any[]>(() => api("/operations/alerts"), []),
    notices = useResource<any[]>(() => api("/notifications"), []),
    snapshots = useResource<any[]>(() => api("/report-snapshots"), []),
    [form, setForm] = useState<any>(null),
    [webhook, setWebhook] = useState(""),
    [message, setMessage] = useState(""),
    [savedSnapshot, setSavedSnapshot] = useState<any>(null);
  useEffect(() => {
    if (data.value)
      setForm((previous: any) =>
        previous
          ? {
              ...previous,
              baseline_confirmed: data.value.baseline_confirmed,
              notice_configured: data.value.notice_configured,
              notice_version: data.value.notice_version,
            }
          : data.value,
      );
  }, [data.value]);
  if (!form) return <Loading />;
  async function save() {
    try {
      const {
        feedback_hours,
        week_day,
        week_hour,
        month_day,
        month_hour,
        rules,
      } = form;
      await api("/operations/settings", {
        method: "PUT",
        body: JSON.stringify({
          feedback_hours,
          week_day,
          week_hour,
          month_day,
          month_hour,
          rules,
        }),
      });
      setMessage("机构规则已保存");
      data.refresh();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="OPERATING RULES"
        title="把关注的指标，设成日常提醒"
        text="负责人配置机构指标、推送安排与通知连接。"
      />
      {message && <Notice>{message}</Notice>}
      <section className="panel ops-section">
        <h2>课返与报表时间</h2>
        <div className="form-grid">
          {[
            ["feedback_hours", "课返时限（小时）"],
            ["week_day", "周报发送星期（0为周一）"],
            ["week_hour", "周报发送小时"],
            ["month_day", "月报发送日期"],
            ["month_hour", "月报发送小时"],
          ].map(([k, l]) => (
            <Field key={k} label={l}>
              <input
                type="number"
                value={form[k]}
                onChange={(e) =>
                  setForm({ ...form, [k]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
        </div>
        <h3>异常规则</h3>
        {form.rules.map((r: any, j: number) => (
          <div className="ops-toolbar" key={j}>
            <select
              className="input"
              value={r.metric}
              onChange={(e) =>
                setForm({
                  ...form,
                  rules: form.rules.map((v: any, n: number) =>
                    n === j ? { ...v, metric: e.target.value } : v,
                  ),
                })
              }
            >
              {[
                "attrition_rate",
                "attendance_rate",
                "lead_conversion_rate",
                "trial_conversion_rate",
                "feedback_completion_rate",
              ].map((k) => (
                <option key={k} value={k}>
                  {statLabels[k]}
                </option>
              ))}
            </select>
            <select
              className="input"
              value={r.direction || "gte"}
              onChange={(e) =>
                setForm({
                  ...form,
                  rules: form.rules.map((v: any, n: number) =>
                    n === j ? { ...v, direction: e.target.value } : v,
                  ),
                })
              }
            >
              <option value="gte">达到或超过</option>
              <option value="lte">低于或等于</option>
            </select>
            <input
              className="input"
              aria-label={`规则${j + 1}阈值`}
              type="number"
              min="0"
              max="100"
              value={r.threshold}
              onChange={(e) =>
                setForm({
                  ...form,
                  rules: form.rules.map((v: any, n: number) =>
                    n === j ? { ...v, threshold: Number(e.target.value) } : v,
                  ),
                })
              }
            />
            <span>%</span>
            <select
              className="input"
              aria-label={`规则${j + 1}适用班级`}
              value={r.class_id || ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  rules: form.rules.map((v: any, n: number) =>
                    n === j ? { ...v, class_id: e.target.value } : v,
                  ),
                })
              }
            >
              <option value="">全机构</option>
              {classOptions.value?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.data.name}
                </option>
              ))}
            </select>
            <button
              className="button small"
              onClick={() =>
                setForm({
                  ...form,
                  rules: form.rules.filter((_: any, n: number) => n !== j),
                })
              }
            >
              移除
            </button>
          </div>
        ))}
        <div className="button-row">
          <button
            className="button"
            onClick={() =>
              setForm({
                ...form,
                rules: [
                  ...form.rules,
                  {
                    id: uid(),
                    metric: "attendance_rate",
                    threshold: 70,
                    direction: "lte",
                    class_id: "",
                  },
                ],
              })
            }
          >
            添加指标规则
          </button>
          <button className="button primary" onClick={save}>
            保存机构规则
          </button>
        </div>
        {!form.baseline_confirmed && (
          <div className="notice">
            <div>
              历史期初资料尚未校准。核对历史在读名单后，可确认期初日期。
              <button
                className="button small"
                onClick={async () => {
                  const at = window.prompt(
                    "期初名单在读生效日期（YYYY-MM-DD）",
                    localDay().slice(0, 7) + "-01",
                  );
                  if (!at) return;
                  try {
                    const ens = { items: await recordsAll("enrollment") };
                    await post("/operations/baseline", {
                      effective_at: at + "T00:00:00+08:00",
                      enrollment_ids: ens.items.map((e: Row) => e.id),
                    });
                    data.refresh();
                    setMessage("期初在读名单已确认");
                  } catch (e) {
                    setMessage((e as Error).message);
                  }
                }}
              >
                核对并确认期初名单
              </button>
            </div>
          </div>
        )}
      </section>
      <section className="panel ops-section">
        <h2>负责人管理群机器人</h2>
        <p>通知仅含经营摘要与系统链接，家长电话和儿童明细留在授权工作台中。</p>
        <Badge value={form.notice_configured ? "connected" : "unconfigured"} />
        <Field label="替换Webhook（已保存凭证不回显）">
          <input
            type="password"
            value={webhook}
            autoComplete="off"
            onChange={(e) => setWebhook(e.target.value)}
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…"
          />
        </Field>
        <div className="button-row">
          <button
            className="button"
            onClick={async () => {
              try {
                await api("/notifications/wecom", {
                  method: "PUT",
                  body: JSON.stringify({ webhook, active: true }),
                });
                setWebhook("");
                data.refresh();
                setMessage("Webhook已加密保存");
              } catch (e) {
                setMessage((e as Error).message);
              }
            }}
          >
            保存通知连接
          </button>
          <button
            className="button"
            onClick={async () => {
              try {
                const r = await post("/notifications/test");
                setMessage("测试消息状态：" + r.status);
                notices.refresh();
              } catch (e) {
                setMessage((e as Error).message);
              }
            }}
          >
            发送连接测试
          </button>
          <button
            className="button"
            onClick={async () => {
              await api("/notifications/wecom", {
                method: "PUT",
                body: JSON.stringify({ active: false }),
              });
              data.refresh();
            }}
          >
            撤销通知连接
          </button>
        </div>
      </section>
      <section className="panel ops-section">
        <h2>异常与处理</h2>
        {alerts.value?.length ? (
          alerts.value.map((a) => (
            <div className="ops-keyline" key={a.id}>
              <div>
                <strong>
                  {statLabels[a.metric]} {a.value}%
                </strong>
                <p>
                  {a.period} · 阈值 {a.threshold}% · {a.note}
                </p>
              </div>
              <Badge value={a.status} />
              <button
                className="button small"
                onClick={async () => {
                  const note = window.prompt("处理意见", a.note || "");
                  if (note === null) return;
                  await patch(`/operations/alerts/${a.id}`, { note });
                  alerts.refresh();
                }}
              >
                登记处理
              </button>
            </div>
          ))
        ) : (
          <p className="muted">暂无已触发的异常。</p>
        )}
      </section>
      <section className="panel ops-section">
        <h2>报表版本</h2>
        {snapshots.value?.map((s) => (
          <button
            className="button small"
            key={s.id}
            onClick={() => setSavedSnapshot(s)}
          >
            {s.kind === "weekly" ? "周报" : "月报"} {s.period} · 第{s.version}版
          </button>
        )) || null}
      </section>
      <section className="panel ops-section">
        <h2>通知记录</h2>
        {notices.value?.map((n) => (
          <div className="ops-keyline" key={n.id}>
            <div>
              {n.body}
              <small>{n.error}</small>
            </div>
            <Badge value={n.status} />
            {["failed", "unknown", "unconfigured", "cancelled"].includes(
              n.status,
            ) && (
              <button
                className="button small"
                onClick={async () => {
                  const confirmed =
                    n.status !== "unknown" ||
                    window.confirm(
                      "已在企微核实这条消息没有发送？核实后重试可避免重复。",
                    );
                  if (!confirmed) return;
                  await post(`/notifications/${n.id}/retry`, {
                    verified_not_sent: confirmed,
                  });
                  notices.refresh();
                }}
              >
                核实后重试
              </button>
            )}
          </div>
        ))}
      </section>
      {savedSnapshot && (
        <Modal
          title={`${savedSnapshot.period} 第${savedSnapshot.version}版报表`}
          close={() => setSavedSnapshot(null)}
          wide
        >
          <div className="form-body">
            <p>生成时间 {date(savedSnapshot.created_at, true)}</p>
            <StatCards
              values={savedSnapshot.payload.metrics}
              keys={Object.keys(savedSnapshot.payload.metrics).filter(
                (k) => statLabels[k],
              )}
            />
            <AIReportSummary key={savedSnapshot.id} reportId={savedSnapshot.id} />
          </div>
        </Modal>
      )}
    </>
  );
}

export function DigitalHumanPage() {
  const data = useResource<any>(() => api("/addons/digital-human"), []),
    [note, setNote] = useState(""),
    [message, setMessage] = useState("");
  return (
    <>
      <PageTitle
        eyebrow="PREMIUM ADD-ON"
        title="数字人直播 · 付费增值服务"
        text="先登记机构需求与开通申请，供应商与真实开播后续接入。"
      />
      <section className="panel ops-section">
        <div className="addon-hero">
          <div className="empty-icon">
            <Users size={35} />
          </div>
          <h2>让课程介绍有一位数字讲解员</h2>
          <p>
            可用于课程介绍、招生话术和机构直播。当前供应商未接通，不会创建直播任务或自动扣费。
          </p>
          <Badge value="waiting_authorization" label="待接入" />
        </div>
        {can("tenant.manage") && (
          <>
            <Field label="机构需求">
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="希望使用的平台、直播主题和时段"
              />
            </Field>
            <button
              className="button primary"
              onClick={async () => {
                try {
                  await post("/addons/digital-human/requests", { note });
                  setNote("");
                  setMessage("申请已登记，等待平台报价与接入安排");
                  data.refresh();
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              申请开通 / 获取报价
            </button>
          </>
        )}
        {message && <Notice>{message}</Notice>}
        {data.value?.requests.map((r: any) => (
          <div className="ops-keyline" key={r.id}>
            <div>
              {r.note}
              <small>{r.platform_note || "等待平台处理"}</small>
            </div>
            <Badge value={r.status} />
          </div>
        ))}
      </section>
    </>
  );
}
export function PlatformAddonPanel() {
  const requests = useResource<any[]>(
      () => api("/platform/addon-requests"),
      [],
    ),
    [notice, setNotice] = useState("");
  return (
    <section className="panel ops-section">
      <h2>数字人增值申请与权益</h2>
      <p>当前供应商待接入。审核通过仅记录开通意向，不创建直播或自动扣费。</p>
      {notice && <Notice>{notice}</Notice>}
      {requests.error && <Notice tone="error">{requests.error}</Notice>}
      {requests.value?.map((r) => (
        <div className="ops-keyline" key={r.id}>
          <div>
            <strong>{r.tenant_name}</strong>
            <p>
              {r.note || "未填写需求"} · {date(r.created_at, true)}
            </p>
            <small>{r.platform_note}</small>
          </div>
          <select
            aria-label={r.tenant_name + "权益状态"}
            value={r.status}
            onChange={async (e) => {
              const note = window.prompt(
                "填写处理说明 / 报价约定",
                r.platform_note || "",
              );
              if (note === null) return;
              try {
                await patch(`/platform/addon-requests/${r.tenant_id}/${r.id}`, {
                  status: e.target.value,
                  note,
                });
                requests.refresh();
                setNotice("申请状态已更新");
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          >
            <option value="requested">待处理</option>
            <option value="quoted">已报价</option>
            <option value="approved_pending_integration">已批准，待接入</option>
            <option value="declined">暂不受理</option>
          </select>
        </div>
      ))}
      {!requests.value?.length && (
        <Empty title="暂无增值申请" text="机构负责人提交后可在此处理。" />
      )}
    </section>
  );
}
