import { can } from "./api";
import { recordsAll } from "./api";
import React, { useState, useEffect } from "react";
import {
  Plus,
  Search,
  Download,
  Check,
  ArrowUpRight,
  Upload,
} from "lucide-react";
import {
  api,
  post,
  patch,
  Row,
  money,
  date,
  uid,
  statuses,
  localInput,
} from "./api";
import { specs, labels, optionLabels } from "./recordspec";
import { Badge, Empty, Modal, Field, Notice, Loading, useResource } from "./ui";
export function RecordEditor({
  kind,
  row,
  close,
  saved,
}: {
  kind: string;
  row?: Row;
  close: () => void;
  saved: () => void;
}) {
  const spec = specs[kind],
    [values, setValues] = useState<Record<string, any>>(() => {
      const v: Record<string, any> = {};
      for (const f of spec.fields) {
        let val = row?.data[f.key];
        if (["money", "percent"].includes(f.type || "") && val !== undefined)
          val /= 100;
        if (f.type === "datetime" && val) val = localInput(val);
        if (f.type === "guardians" && !val)
          val = row?.data.guardian
            ? [
                {
                  name: row.data.guardian,
                  relationship: "家长",
                  contact: row.data.contact || "",
                },
              ]
            : [];
        v[f.key] =
          val ??
          f.default ??
          (f.type === "check" ? false : f.type === "platforms" ? [] : "");
      }
      return v;
    });
  const [busy, setBusy] = useState(false),
    [approvalId] = useState(uid),
    [error, setError] = useState("");
  const refs = useResource(async () => {
    const result: Record<string, any[]> = {};
    for (const ref of [
      ...new Set(spec.fields.filter((f) => f.ref).map((f) => f.ref!)),
    ]) {
      try {
        result[ref] =
          ref === "member"
            ? await api("/members")
            : ref === "class" && !can("class.read")
              ? await api("/operations/class-choices")
              : await recordsAll(ref);
      } catch {
        result[ref] = [];
      }
    }
    return result;
  }, [kind]);
  function change(key: string, value: any) {
    const next = { ...values, [key]: value };
    if (key === "order_id" && kind === "enrollment") {
      const order = refs.value?.order?.find((x) => x.id === value);
      if (order) {
        next.student_id = order.data.student_id;
        next.class_id = order.data.class_id || "";
      }
    }
    setValues(next);
  }
  async function submit(e: React.FormEvent, approval = false) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data: Record<string, any> = {};
      for (const f of spec.fields) {
        let value = values[f.key];
        if (["money", "percent"].includes(f.type || ""))
          value = Math.round(Number(value || 0) * 100);
        else if (f.type === "number") value = Number(value || 0);
        else if (f.type === "datetime" && value)
          value = new Date(value).toISOString();
        if (["next_run_at", "effective_from"].includes(f.key) && !value)
          value = null;
        data[f.key] = value;
      }
      if (approval) {
        const definitions = await api("/studio/definitions?kind=workflow");
        const flow = definitions.find(
          (d: any) => d.binding === kind && d.enabled && d.published_version,
        );
        if (!flow) throw new Error("该业务尚未启用审批模板");
        await post(`/studio/workflows/${flow.id}/instances`, {
          request_id: "approval:" + approvalId,
          record_id: row?.id || "",
          payload: { business: data },
        });
        window.alert("已提交审批，可在表单与流程中查看进度");
        saved();
        close();
        return;
      }
      if (row)
        await patch("/records/" + kind + "/" + row.id, {
          data,
          version: row.version,
        });
      else await post("/records/" + kind, { data });
      saved();
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={(row ? "编辑" : "新增") + spec.title} close={close}>
      <form onSubmit={submit}>
        <div className="form-body">
          {error && <Notice tone="error">{error}</Notice>}
          <div className="form-grid">
            {spec.fields.map((f) => (
              <div
                className={
                  ["textarea", "platforms"].includes(f.type || "") ? "full" : ""
                }
                key={f.key}
              >
                {f.type === "guardians" ? (
                  <div className="full">
                    <h3>{f.label}</h3>
                    {(values[f.key] || []).map((g: any, j: number) => (
                      <div className="guardian-row" key={j}>
                        {[
                          ["name", "家长称呼"],
                          ["relationship", "关系"],
                          ["contact", "家长手机号"],
                        ].map(([key, label]) => (
                          <Field key={key} label={label}>
                            <input
                              value={g[key] || ""}
                              onChange={(e) =>
                                change(
                                  f.key,
                                  values[f.key].map((v: any, n: number) =>
                                    n === j
                                      ? { ...v, [key]: e.target.value }
                                      : v,
                                  ),
                                )
                              }
                            />
                          </Field>
                        ))}
                        <button
                          className="button small"
                          type="button"
                          onClick={() =>
                            change(
                              f.key,
                              values[f.key].filter(
                                (_: any, n: number) => n !== j,
                              ),
                            )
                          }
                        >
                          移除
                        </button>
                      </div>
                    ))}
                    <button
                      className="button small"
                      type="button"
                      onClick={() =>
                        change(f.key, [
                          ...(values[f.key] || []),
                          { name: "", relationship: "家长", contact: "" },
                        ])
                      }
                    >
                      添加家长
                    </button>
                  </div>
                ) : f.type === "check" ? (
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={Boolean(values[f.key])}
                      onChange={(e) => change(f.key, e.target.checked)}
                    />
                    {f.label}
                  </label>
                ) : f.type === "platforms" ? (
                  <Field label={f.label}>
                    <div className="button-row">
                      {[
                        ["xiaohongshu", "小红书"],
                        ["douyin", "抖音"],
                        ["channels", "视频号"],
                      ].map(([k, l]) => (
                        <label className="check" key={k}>
                          <input
                            type="checkbox"
                            checked={values[f.key].includes(k)}
                            onChange={(e) =>
                              change(
                                f.key,
                                e.target.checked
                                  ? [...values[f.key], k]
                                  : values[f.key].filter(
                                      (x: string) => x !== k,
                                    ),
                              )
                            }
                          />
                          {l}
                        </label>
                      ))}
                    </div>
                  </Field>
                ) : (
                  <Field label={f.label + (f.required ? " *" : "")}>
                    {f.type === "textarea" ? (
                      <textarea
                        required={f.required}
                        value={values[f.key]}
                        onChange={(e) => change(f.key, e.target.value)}
                      />
                    ) : f.type === "ref" ? (
                      <select
                        required={f.required}
                        value={values[f.key]}
                        onChange={(e) => change(f.key, e.target.value)}
                      >
                        <option value="">请选择</option>
                        {refs.value?.[f.ref!]?.map((x) => (
                          <option
                            key={x.id}
                            value={f.ref === "member" ? x.user_id : x.id}
                          >
                            {x.data?.name || x.name || x.id.slice(0, 8)}
                          </option>
                        ))}
                      </select>
                    ) : f.type === "select" ? (
                      <select
                        value={values[f.key]}
                        onChange={(e) => change(f.key, e.target.value)}
                      >
                        {!f.required && !f.default && (
                          <option value="">请选择</option>
                        )}
                        {f.options?.map((x) => (
                          <option key={x} value={x}>
                            {statuses[x] || optionLabels[x] || x}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        required={f.required}
                        type={
                          f.type === "datetime"
                            ? "datetime-local"
                            : ["number", "money", "percent"].includes(
                                  f.type || "",
                                )
                              ? "number"
                              : f.type === "date"
                                ? "date"
                                : "text"
                        }
                        step={
                          ["money", "percent"].includes(f.type || "")
                            ? "0.01"
                            : undefined
                        }
                        min={
                          ["number", "money", "percent"].includes(f.type || "")
                            ? "0"
                            : undefined
                        }
                        value={values[f.key]}
                        onChange={(e) => change(f.key, e.target.value)}
                      />
                    )}
                  </Field>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="form-footer">
          <button type="button" className="button" onClick={close}>
            取消
          </button>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={(e) => submit(e, true)}
          >
            提交审批
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "保存中…" : "保存记录"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function MoneyModal({
  row,
  kind,
  close,
  saved,
}: {
  row: Row;
  kind: "payments" | "refunds";
  close: () => void;
  saved: () => void;
}) {
  const [amount, setAmount] = useState(
      (kind === "payments"
        ? row.data.due_fen - row.data.paid_fen
        : row.data.paid_fen) / 100,
    ),
    [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [requestId] = useState(uid),
    [withdrawal, setWithdrawal] = useState(false),
    [enrollmentIds, setEnrollmentIds] = useState<string[]>([]);
  const context = useResource<any>(
    () =>
      kind === "refunds"
        ? api(`/orders/${row.id}/refund-context`)
        : Promise.resolve(null),
    [row.id, kind],
  );
  async function requestApproval() {
    try {
      const defs = await api("/studio/definitions?kind=workflow");
      const flow = defs.find(
        (d: any) => d.binding === "refund" && d.enabled && d.published_version,
      );
      if (!flow) throw new Error("机构尚未启用退款审批模板");
      await post(`/studio/workflows/${flow.id}/instances`, {
        request_id: "approval:" + requestId,
        record_id: row.id,
        payload: {
          business: {
            amount_fen: Math.round(amount * 100),
            reason: note,
            withdrawal,
            enrollment_ids: [...enrollmentIds].sort(),
          },
        },
      });
      window.alert("退款审批已提交");
      close();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <Modal title={kind === "payments" ? "登记收款" : "登记退款"} close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/orders/" + row.id + "/" + kind, {
              amount_fen: Math.round(amount * 100),
              note,
              ...(kind === "refunds"
                ? { reason: note, withdrawal, enrollment_ids: enrollmentIds }
                : {}),
              request_id: requestId,
            });
            saved();
            close();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-body">
          <Notice>以实际到账或退款记录为准。订单：{row.data.name}</Notice>
          {error && <Notice tone="error">{error}</Notice>}
          {kind === "refunds" && context.value && (
            <div className="refund-context">
              <h3>退款时的课时信息</h3>
              {context.value.enrollments.map((e: any) => (
                <div className="ops-keyline" key={e.enrollment_id}>
                  <span>
                    购买 {e.purchased_units} · 已上 {e.attended_units} · 未上{" "}
                    {e.remaining_units}
                  </span>
                  {withdrawal && e.status === "active" && (
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={enrollmentIds.includes(e.enrollment_id)}
                        onChange={(ev) =>
                          setEnrollmentIds(
                            ev.target.checked
                              ? [...enrollmentIds, e.enrollment_id]
                              : enrollmentIds.filter(
                                  (x) => x !== e.enrollment_id,
                                ),
                          )
                        }
                      />
                      结束此报名
                    </label>
                  )}
                </div>
              ))}
              <Field label="退款类型">
                <select
                  value={withdrawal ? "withdraw" : "continue"}
                  onChange={(e) => {
                    setWithdrawal(e.target.value === "withdraw");
                    setEnrollmentIds([]);
                  }}
                >
                  <option value="continue">部分退款，继续就读</option>
                  <option value="withdraw">退读退费，结束所选报名</option>
                </select>
              </Field>
              <p className="muted">金额由财务核对录入，课时信息会保留快照。</p>
            </div>
          )}
          <Field label="金额（元）">
            <input
              required
              type="number"
              step="0.01"
              min="0.01"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </Field>
          <Field
            label={
              kind === "refunds" ? "退款原因（必填）" : "交易说明或流水编号"
            }
          >
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required
            />
          </Field>
        </div>
        <div className="form-footer">
          {kind === "refunds" && (
            <button className="button" type="button" onClick={requestApproval}>
              发起退费审批
            </button>
          )}
          <button className="button primary" disabled={busy}>
            {busy ? "登记中…" : "确认登记"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function AttendanceModal({
  row,
  close,
  saved,
}: {
  row: Row;
  close: () => void;
  saved: () => void;
}) {
  const data = useResource(
      async () => (await api("/records/lesson")).items as Row[],
      [],
    ),
    [lesson, setLesson] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [requestId] = useState(uid);
  return (
    <Modal title="学员签到" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/enrollments/" + row.id + "/attendance", {
              lesson_id: lesson,
              request_id: requestId,
            });
            saved();
            close();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-body">
          {error && <Notice tone="error">{error}</Notice>}
          <Notice>签到扣减1课时，重复签到不会再次扣减。</Notice>
          <Field label="选择本班课程">
            <select
              required
              value={lesson}
              onChange={(e) => setLesson(e.target.value)}
            >
              <option value="">请选择课程</option>
              {data.value
                ?.filter(
                  (x) =>
                    x.data.class_id === row.data.class_id &&
                    x.data.status !== "cancelled",
                )
                .map((x) => (
                  <option value={x.id} key={x.id}>
                    {x.data.name} · {date(x.data.starts_at, true)}
                  </option>
                ))}
            </select>
          </Field>
          {!row.data.class_id && (
            <Notice>报名记录尚未关联班级，请核对报名安排。</Notice>
          )}
        </div>
        <div className="form-footer">
          <button
            className="button primary"
            disabled={busy || !row.data.class_id}
          >
            {busy ? "签到中…" : "确认到课"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function RecordPage({ kind, role }: { kind: string; role: string }) {
  const [search, setSearch] = useState(""),
    [skip, setSkip] = useState(0),
    [editing, setEditing] = useState<Row | null | undefined>(undefined),
    [moneyRow, setMoneyRow] = useState<{
      row: Row;
      kind: "payments" | "refunds";
    } | null>(null),
    [attend, setAttend] = useState<Row | null>(null),
    [transferring, setTransferring] = useState<Row | null>(null),
    [notice, setNotice] = useState("");
  const data = useResource<{ items: Row[]; total: number }>(
    () =>
      api(
        "/records/" +
          kind +
          "?q=" +
          encodeURIComponent(search) +
          "&skip=" +
          skip,
      ),
    [kind, search, skip],
  );
  const references = useResource(async () => {
    const result: Record<string, string> = {};
    for (const name of [
      ...new Set(specs[kind].fields.filter((f) => f.ref).map((f) => f.ref!)),
    ]) {
      try {
        const rows =
          name === "member" ? await api("/members") : await recordsAll(name);
        for (const row of rows)
          result[row.id] = row.data?.name || row.name || row.id.slice(0, 6);
        if (name === "member")
          for (const row of rows) result[row.user_id] = row.name;
      } catch {}
    }
    return result;
  }, [kind]);
  useEffect(() => setSkip(0), [kind, search]);
  const spec = specs[kind],
    canWrite = can(kind + ".write");
  const columns =
    kind === "order" && !can("order.write")
      ? ["name", "student_id", "course_id", "payment_status"]
      : kind === "student" && !can("education.read") && !can("student.write")
        ? ["name", "grade", "guardian"]
        : spec.columns;
  function cell(row: Row, key: string) {
    const val = row.data[key];
    if (
      key === "name" &&
      ["order", "expense"].includes(kind) &&
      can("finance.read")
    )
      return (
        <button
          className="button link"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("finance-detail", {
                detail: { kind, id: row.id },
              }),
            )
          }
        >
          {val}
        </button>
      );
    if (key.endsWith("_fen")) return money(val);
    if (key.endsWith("_bps")) return Number(val || 0) / 100 + "%";
    if (key.endsWith("_id")) return references.value?.[val] || "—";
    if (["stage", "status"].includes(key)) return <Badge value={val} />;
    if (["approved", "confirmed", "enabled"].includes(key))
      return (
        <Badge
          value={val ? "approved" : "draft"}
          label={val ? "已确认" : "未启用"}
        />
      );
    if (key.endsWith("_at")) return date(val, true);
    if (key === "form") return optionLabels[val] || val;
    if (Array.isArray(val))
      return val
        .map(
          (v) =>
            ({ xiaohongshu: "小红书", douyin: "抖音", channels: "视频号" })[
              v as string
            ] || v,
        )
        .join(" / ");
    return String(val ?? "—").slice(0, 90);
  }
  return (
    <>
      {notice && <Notice>{notice}</Notice>}
      <div className="panel">
        <div className="toolbar">
          <div className="search">
            <Search size={16} />
            <input
              aria-label={"搜索" + spec.title}
              placeholder={"搜索" + spec.title + "…"}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="button-row">
            <a
              className="button small"
              href={"/api/v1/exports/" + kind + "?format=xlsx"}
            >
              <Download size={13} />
              导出
            </a>
            {canWrite && (
              <button
                className="button primary small"
                onClick={() => setEditing(null)}
              >
                <Plus size={14} />
                新增{spec.title}
              </button>
            )}
          </div>
        </div>
        {data.error ? (
          <div className="error-panel">
            <Notice tone="error">{data.error}</Notice>
          </div>
        ) : data.loading ? (
          <Loading />
        ) : !data.value?.items.length ? (
          <Empty
            title={"还没有" + spec.title}
            text={spec.text}
            action={
              canWrite ? (
                <button className="button" onClick={() => setEditing(null)}>
                  <Plus size={14} />
                  添加第一条
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map((key) => (
                    <th key={key}>{labels[key] || key}</th>
                  ))}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.value.items.map((row) => (
                  <tr key={row.id}>
                    {columns.map((key) => (
                      <td key={key}>{cell(row, key)}</td>
                    ))}
                    <td>
                      <div className="button-row">
                        {canWrite && kind !== "enrollment" && (
                          <button
                            className="button link"
                            onClick={() =>
                              kind === "enrollment"
                                ? setTransferring(row)
                                : setEditing(row)
                            }
                          >
                            编辑
                          </button>
                        )}
                        {kind === "order" && can("finance.write") && (
                          <>
                            {row.data.paid_fen < row.data.due_fen && (
                              <button
                                className="button link"
                                onClick={() =>
                                  setMoneyRow({ row, kind: "payments" })
                                }
                              >
                                收款
                              </button>
                            )}
                            {row.data.paid_fen > 0 && (
                              <button
                                className="button link"
                                onClick={() =>
                                  setMoneyRow({ row, kind: "refunds" })
                                }
                              >
                                退款
                              </button>
                            )}
                          </>
                        )}
                        {kind === "enrollment" && can("attendance.write") && (
                          <button
                            className="button link"
                            onClick={() => setAttend(row)}
                          >
                            <Check size={13} />
                            签到
                          </button>
                        )}
                        {kind === "knowledge" &&
                          canWrite &&
                          row.data.approved && (
                            <button
                              className="button link"
                              onClick={async () => {
                                try {
                                  await post("/runs", {
                                    kind: "knowledge_index",
                                    request_id: uid(),
                                    input: { record_id: row.id },
                                  });
                                  setNotice(
                                    "已提交索引任务，每次最多处理5段；可再次提交处理剩余段落。",
                                  );
                                } catch (e) {
                                  setNotice((e as Error).message);
                                }
                              }}
                            >
                              建立检索索引
                            </button>
                          )}
                        {kind === "feedback" && canWrite && (
                          <button
                            className="button link"
                            onClick={async () => {
                              try {
                                await post("/runs", {
                                  kind: "feedback",
                                  request_id: uid(),
                                  input: { feedback_id: row.id },
                                });
                                setNotice(
                                  "反馈生成任务已提交，请稍后刷新查看。",
                                );
                              } catch (e) {
                                setNotice((e as Error).message);
                              }
                            }}
                          >
                            AI反馈
                          </button>
                        )}
                        {kind === "topic" && canWrite && (
                          <a
                            className="button link"
                            href={
                              "#content?topic=" +
                              encodeURIComponent(row.data.name)
                            }
                          >
                            创作
                            <ArrowUpRight size={12} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-bottom">
          <span>
            共 {data.value?.total || 0} 条记录 · 数据仅对当前机构授权成员可见
          </span>
          <div className="button-row">
            <button
              className="button small"
              disabled={skip === 0}
              onClick={() => setSkip(Math.max(0, skip - 100))}
            >
              上一页
            </button>
            <span>第 {Math.floor(skip / 100) + 1} 页</span>
            <button
              className="button small"
              disabled={skip + 100 >= (data.value?.total || 0)}
              onClick={() => setSkip(skip + 100)}
            >
              下一页
            </button>
          </div>
        </div>
      </div>
      {editing !== undefined && (
        <RecordEditor
          kind={kind}
          row={editing || undefined}
          close={() => setEditing(undefined)}
          saved={data.refresh}
        />
      )}{" "}
      {moneyRow && (
        <MoneyModal
          {...moneyRow}
          close={() => setMoneyRow(null)}
          saved={data.refresh}
        />
      )}{" "}
      {transferring && (
        <TransferModal
          row={transferring}
          close={() => setTransferring(null)}
          saved={data.refresh}
        />
      )}
      {attend && (
        <AttendanceModal
          row={attend}
          close={() => setAttend(null)}
          saved={data.refresh}
        />
      )}
    </>
  );
}
export function FinanceExtra({ mode }: { mode: string }) {
  const data = useResource<any[]>(
      () => api(mode === "ledger" ? "/ledger" : "/settlements"),
      [mode],
    ),
    [notice, setNotice] = useState("");
  return (
    <div className="panel">
      <div className="toolbar">
        <strong style={{ fontSize: 12 }}>
          {mode === "ledger" ? "实际收退款流水" : "渠道结算明细"}
        </strong>
        {mode === "ledger" && (
          <label className="button small">
            <Upload size={13} />
            导入收款 CSV
            <input
              type="file"
              accept=".csv"
              hidden
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const form = new FormData();
                form.append("file", file);
                try {
                  const result = await api("/imports/payments", {
                    method: "POST",
                    body: form,
                  });
                  setNotice("已核对 " + result.imported + " 笔交易");
                  data.refresh();
                } catch (e) {
                  setNotice((e as Error).message);
                }
              }}
            />
          </label>
        )}
      </div>
      {notice && <Notice>{notice}</Notice>}
      {data.error ? (
        <Notice tone="error">{data.error}</Notice>
      ) : !data.value?.length ? (
        <Empty text="完成订单收款后，这里会出现对应的流水和结算记录。" />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {(mode === "ledger"
                  ? ["类型", "金额", "订单编号", "时间", "操作"]
                  : ["订单", "净收款", "分润比例", "应结算"]
                ).map((x) => (
                  <th key={x}>{x}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.value.map((row) => (
                <tr key={row.id || row.order_id}>
                  {mode === "ledger" ? (
                    <>
                      <td>
                        {{ payment: "收款", refund: "退款", reversal: "冲正" }[
                          row.entry_type as string
                        ] || row.entry_type}
                      </td>
                      <td>{money(row.amount_fen)}</td>
                      <td>
                        <button
                          className="button link"
                          onClick={() =>
                            window.dispatchEvent(
                              new CustomEvent("finance-detail", {
                                detail: { kind: "ledger", id: row.id },
                              }),
                            )
                          }
                        >
                          {row.order_id.slice(0, 10)} · 查看票据
                        </button>
                      </td>
                      <td>{date(row.created_at, true)}</td>
                      <td>
                        <button
                          className="button link"
                          onClick={async () => {
                            if (
                              !window.confirm(
                                "确认冲正这笔流水？原记录会保留。",
                              )
                            )
                              return;
                            try {
                              await post("/ledger/" + row.id + "/reverse", {
                                request_id: uid(),
                              });
                              data.refresh();
                            } catch (e) {
                              setNotice((e as Error).message);
                            }
                          }}
                        >
                          冲正
                        </button>
                        <button
                          className="button link"
                          onClick={async () => {
                            const note = window.prompt("填写冲正原因");
                            if (!note?.trim()) return;
                            try {
                              const definitions = await api(
                                  "/studio/definitions?kind=workflow",
                                ),
                                flow = definitions.find(
                                  (d: any) =>
                                    d.binding === "reversal" && d.enabled,
                                );
                              if (!flow)
                                throw Error(
                                  "负责人尚未启用冲正审批模板，可按当前权限直接登记",
                                );
                              await post(
                                `/studio/workflows/${flow.id}/instances`,
                                {
                                  record_id: row.id,
                                  payload: { business: { note } },
                                  request_id: uid(),
                                },
                              );
                              setNotice(
                                "冲正审批已提交，请在表单与流程查看待办",
                              );
                            } catch (e) {
                              setNotice((e as Error).message);
                            }
                          }}
                        >
                          提交冲正审批
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{row.name}</td>
                      <td>{money(row.net_fen)}</td>
                      <td>{row.commission_bps / 100}%</td>
                      <td>{money(row.commission_fen)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ReceiptIntake() {
  const [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [funding, setFunding] = useState("platform");
  return (
    <div className="panel settings-card" style={{ marginBottom: 20 }}>
      <h2>票据识别与核对</h2>
      <p>上传票据后生成待核对费用草稿；核对金额、日期和用途后，再确认入账。</p>
      {notice && <Notice>{notice}</Notice>}
      <div className="button-row">
        <select
          className="input"
          style={{ width: 170 }}
          value={funding}
          onChange={(e) => setFunding(e.target.value)}
        >
          <option value="platform">平台额度</option>
          <option value="byok">机构自带 Key</option>
        </select>
        <label className="button">
          <Upload size={14} />
          {busy ? "提交中…" : "上传票据并识别"}
          <input
            type="file"
            hidden
            disabled={busy}
            accept="image/png,image/jpeg,application/pdf"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true);
              try {
                const f = new FormData();
                f.append("file", file);
                f.append("purpose", "receipt");
                const asset = await api("/assets", { method: "POST", body: f });
                await post("/runs", {
                  kind: "ocr",
                  request_id: uid(),
                  funding,
                  input: { asset_id: asset.id },
                });
                setNotice(
                  "识别任务已提交。完成后刷新费用台账，核对草稿再确认入账。",
                );
              } catch (e) {
                setNotice((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
      </div>
    </div>
  );
}
export function SettlementStatements() {
  const data = useResource<any[]>(() => api("/settlement-statements"), []),
    channels = useResource<any[]>(
      async () => (await api("/records/channel")).items,
      [],
    ),
    [channel, setChannel] = useState(""),
    [period, setPeriod] = useState(() => {
      const d = new Date();
      d.setMonth(d.getMonth() - 1);
      return d.toISOString().slice(0, 7);
    }),
    [notice, setNotice] = useState("");
  return (
    <div className="panel settings-card space-top">
      <h2>固定月度结算单</h2>
      <p>
        按已结束月份的净现金流水与订单生效比例结算；后续退款在退款月份形成负向调整。
      </p>
      {notice && <Notice>{notice}</Notice>}
      <form
        className="button-row"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await post("/settlement-statements", {
              channel_id: channel,
              period,
            });
            data.refresh();
            setNotice("月度结算单已固定，重复提交会返回同一张单据。");
          } catch (e) {
            setNotice((e as Error).message);
          }
        }}
      >
        <select
          className="input"
          style={{ width: 220 }}
          required
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
        >
          <option value="">选择合作渠道</option>
          {channels.value?.map((x) => (
            <option key={x.id} value={x.id}>
              {x.data.name}
            </option>
          ))}
        </select>
        <input
          className="input"
          style={{ width: 180 }}
          aria-label="结算月份"
          type="month"
          required
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        />
        <button className="button primary">生成结算单</button>
      </form>
      {data.value?.map((x) => (
        <details key={x.id} className="space-top">
          <summary style={{ fontSize: 12 }}>
            {x.period} · {money(x.amount_fen)} · 单号 {x.id.slice(0, 10)}
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单</th>
                  <th>当月净现金</th>
                  <th>比例</th>
                  <th>结算金额</th>
                </tr>
              </thead>
              <tbody>
                {x.entries.map((row: any) => (
                  <tr key={row.order_id}>
                    <td>{row.order}</td>
                    <td>{money(row.net_fen)}</td>
                    <td>{row.commission_bps / 100}%</td>
                    <td>{money(row.commission_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}
export function EducationReport() {
  const data = useResource<any>(() => api("/education/weekly-report"), []);
  return (
    <div className="panel settings-card" style={{ marginBottom: 20 }}>
      <h2>最近7天班级周报</h2>
      <p>按已完成排课与真实签到记录汇总，缺勤、待补课和课时不足分别提示。</p>
      {data.error && <Notice tone="error">{data.error}</Notice>}
      <div className="button-row">
        {data.value?.classes.map((c: any) => (
          <span className="badge" key={c.name}>
            {c.name} · 完成 {c.lessons_completed} 节 · 到课 {c.attendance_count}{" "}
            人次
          </span>
        ))}
      </div>
      <div className="button-row space-top">
        <Badge
          value={data.value?.absent.length ? "unknown" : "active"}
          label={"缺勤 " + (data.value?.absent.length || 0)}
        />
        <Badge
          value="draft"
          label={"待补课 " + (data.value?.makeup_pending.length || 0)}
        />
        <Badge
          value="draft"
          label={"课时不足 " + (data.value?.low_credits.length || 0)}
        />
      </div>
    </div>
  );
}

function TransferModal({
  row,
  close,
  saved,
}: {
  row: Row;
  close: () => void;
  saved: () => void;
}) {
  const classes = useResource<any[]>(
      async () => (await api("/records/class")).items,
      [],
    ),
    [cls, setCls] = useState(row.data.class_id || ""),
    [reason, setReason] = useState(""),
    [effective, setEffective] = useState(""),
    [notice, setNotice] = useState("");
  const [approvalId] = useState(uid);
  async function submit(approval = false) {
    try {
      const payload = {
        class_id: cls,
        reason,
        effective_at: effective ? new Date(effective).toISOString() : null,
      };
      if (!reason.trim()) throw Error("请填写调班原因");
      if (approval) {
        const defs = await api("/studio/definitions?kind=workflow"),
          flow = defs.find((d: any) => d.binding === "transfer" && d.enabled);
        if (!flow) throw Error("负责人尚未启用调班审批流程");
        await post(`/studio/workflows/${flow.id}/instances`, {
          record_id: row.id,
          payload: { business: payload },
          request_id: "approval:" + approvalId,
        });
      } else await post(`/enrollments/${row.id}/transfer`, payload);
      saved();
      window.dispatchEvent(new Event("ops-refresh"));
      close();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  return (
    <Modal title="调班 / 退班登记" close={close}>
      <div className="form-body">
        <Notice>
          保留原班级历史，已发生的出勤和课返考核不随当前班级改变。
        </Notice>
        {notice && <Notice tone="error">{notice}</Notice>}
        <Field label="新班级">
          <select value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="">暂不分班</option>
            {classes.value?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.data.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="生效时间（留空为当前）">
          <input
            type="datetime-local"
            value={effective}
            onChange={(e) => setEffective(e.target.value)}
          />
        </Field>
        <Field label="调班原因">
          <textarea
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
      </div>
      <div className="form-footer">
        <button className="button" onClick={() => submit(true)}>
          提交调班审批
        </button>
        <button className="button primary" onClick={() => submit()}>
          确认调班
        </button>
      </div>
    </Modal>
  );
}
