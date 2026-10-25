import React, { useState, useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useNodesState,
  useEdgesState,
  MarkerType,
  useReactFlow,
  useNodesInitialized,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Plus,
  Save,
  Upload,
  Download,
  Play,
  CheckCircle2,
  ArrowUp,
  ArrowDown,
  Trash2,
} from "lucide-react";
import { api, post, patch, can, uid, roles, date } from "./api";
import {
  PageTitle,
  Field,
  Modal,
  Notice,
  Loading,
  Badge,
  Empty,
  useResource,
} from "./ui";

import { specs } from "./recordspec";
type F = Record<string, any>;
const fieldTypes: Record<string, string> = {
  text: "单行文本",
  textarea: "多行文本",
  number: "数字",
  money: "金额",
  date: "日期",
  datetime: "日期时间",
  select: "单选",
  multiselect: "多选",
  boolean: "勾选",
  attachment: "附件",
  reference: "业务关联",
  table: "明细子表",
};
const bindings: Record<string, string> = {
  independent: "独立表单",
  lead: "招生",
  student: "学员",
  class: "班级",
  leave: "请假",
  transfer: "调班",
  refund: "退读退费",
  reversal: "账务冲正",
  expense: "费用",
  enrollment: "报名确认",
};
const nodeTypes: Record<string, string> = {
  start: "开始",
  form: "填写 / 确认",
  approval: "审批",
  condition: "条件分支",
  parallel: "并行分支",
  join: "汇合",
  notify: "通知",
  action: "业务动作",
  end: "结束",
};
const businessLabels: Record<string, string> = {
  amount_fen: "金额（分）",
  reason: "原因",
  withdrawal: "是否退读",
  enrollment_ids: "退读报名编号",
  student_id: "学员编号",
  name: "名称",
  contact: "家长手机号",
  guardian: "家长",
  grade: "年级",
  class_id: "班级编号",
  notes: "说明",
  status: "状态",
  program_name: "报名项目",
  price_fen: "学费（分）",
  purchased_units: "购买课时",
  discount_fen: "优惠（分）",
};
function RoleChoices({
  value,
  change,
}: {
  value: string[];
  change: (v: string[]) => void;
}) {
  return (
    <div className="studio-role-choices">
      {Object.entries(roles)
        .filter(([k]) => k !== "operator")
        .map(([k, label]) => (
          <label key={k}>
            <input
              type="checkbox"
              checked={value.includes(k)}
              onChange={(e) =>
                change(
                  e.target.checked
                    ? [...value, k]
                    : value.filter((x) => x !== k),
                )
              }
            />
            {label}
          </label>
        ))}
    </div>
  );
}
function RefInput({
  f,
  value,
  change,
  disabled,
}: {
  f: F;
  value: any;
  change: (v: any) => void;
  disabled?: boolean;
}) {
  const data = useResource<any[]>(
    () =>
      f.ref === "member"
        ? api("/members").then((rows) =>
            rows.map((r: any) => ({ id: r.user_id, data: { name: r.name } })),
          )
        : f.ref === "ledger"
          ? api("/ledger").then((rows) =>
              rows.map((r: any) => ({
                id: r.id,
                data: {
                  name:
                    (r.entry_type === "payment"
                      ? "收款"
                      : r.entry_type === "refund"
                        ? "退款"
                        : "冲正") +
                    " · ¥" +
                    (r.amount_fen / 100).toFixed(2) +
                    " · " +
                    date(r.created_at, true),
                },
              })),
            )
          : f.ref === "class" && !can("class.read")
            ? api("/operations/class-choices")
            : api("/records/" + f.ref).then((x) => x.items),
    [f.ref],
  );
  return (
    <select
      disabled={disabled}
      value={value || ""}
      onChange={(e) => change(e.target.value)}
      required={f.required}
    >
      <option value="">请选择</option>
      {data.value?.map((r) => (
        <option key={r.id} value={r.id}>
          {r.data.name || r.id}
        </option>
      ))}
    </select>
  );
}
function visible(f: F, values: F) {
  const r = f.visible_when;
  if (!r || !Object.keys(r).length) return true;
  const v = values[r.field];
  if (r.op === "eq" || !r.op) return v === r.value;
  if (r.op === "ne") return v !== r.value;
  if (r.op === "exists") return v !== undefined && v !== "";
  return true;
}
export function FormFields({
  fields,
  values,
  change,
}: {
  fields: F[];
  values: F;
  change: (v: F) => void;
}) {
  return (
    <div className="form-grid studio-form-fields">
      {fields
        .filter((f) => visible(f, values))
        .map((f) => {
          const v = values[f.key],
            update = (value: any) => change({ ...values, [f.key]: value }),
            disabled = f.editable === false;
          return (
            <div
              key={f.key}
              className={
                ["textarea", "table", "attachment"].includes(f.type)
                  ? "full"
                  : ""
              }
            >
              {f.group && <p className="studio-group-label">{f.group}</p>}
              <Field label={f.label + (f.required ? " *" : "")}>
                {f.type === "textarea" ? (
                  <textarea
                    required={f.required}
                    disabled={disabled}
                    value={v || ""}
                    onChange={(e) => update(e.target.value)}
                  />
                ) : f.type === "boolean" ? (
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={disabled}
                      checked={!!v}
                      onChange={(e) => update(e.target.checked)}
                    />
                    是
                  </label>
                ) : f.type === "select" || f.type === "multiselect" ? (
                  <select
                    disabled={disabled}
                    required={f.required}
                    multiple={f.type === "multiselect"}
                    value={v || (f.type === "multiselect" ? [] : "")}
                    onChange={(e) =>
                      update(
                        f.type === "multiselect"
                          ? Array.from(e.target.selectedOptions).map(
                              (x) => x.value,
                            )
                          : e.target.value,
                      )
                    }
                  >
                    {f.type === "select" && <option value="">请选择</option>}
                    {(f.options || []).map((o: string) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                ) : f.type === "reference" ? (
                  <RefInput
                    f={f}
                    value={v}
                    change={update}
                    disabled={disabled}
                  />
                ) : f.type === "attachment" ? (
                  <div>
                    <input
                      type="file"
                      disabled={disabled}
                      accept="image/png,image/jpeg,application/pdf"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        const body = new FormData();
                        body.append("file", file);
                        body.append("purpose", "document");
                        try {
                          const a = await api("/assets", {
                            method: "POST",
                            body,
                          });
                          update([...(v || []), a.id]);
                        } catch (e) {
                          window.alert((e as Error).message);
                        }
                      }}
                    />
                    {(v || []).map((aid: string) => (
                      <a
                        className="button small"
                        key={aid}
                        href={"/api/v1/assets/" + aid + "/download"}
                        target="_blank"
                        rel="noreferrer"
                      >
                        附件 ↗
                      </a>
                    ))}
                  </div>
                ) : f.type === "table" ? (
                  <div>
                    {(v || []).map((row: F, j: number) => (
                      <div className="studio-subrow" key={j}>
                        <FormFields
                          fields={f.fields || []}
                          values={row}
                          change={(newRow) =>
                            update(
                              v.map((r: F, n: number) =>
                                n === j ? newRow : r,
                              ),
                            )
                          }
                        />
                        {!disabled && (
                          <button
                            type="button"
                            className="button small"
                            onClick={() =>
                              update(v.filter((_: any, n: number) => n !== j))
                            }
                          >
                            移除此行
                          </button>
                        )}
                      </div>
                    ))}
                    {!disabled && (
                      <button
                        type="button"
                        className="button small"
                        onClick={() => update([...(v || []), {}])}
                      >
                        添加明细行
                      </button>
                    )}
                  </div>
                ) : (
                  <input
                    required={f.required}
                    disabled={disabled}
                    type={
                      {
                        number: "number",
                        money: "number",
                        date: "date",
                        datetime: "datetime-local",
                      }[f.type as string] || "text"
                    }
                    min={f.min}
                    max={f.max}
                    step={f.type === "money" ? "0.01" : "any"}
                    value={v ?? ""}
                    onChange={(e) =>
                      update(
                        f.type === "number"
                          ? Number(e.target.value)
                          : e.target.value,
                      )
                    }
                  />
                )}
              </Field>
            </div>
          );
        })}
    </div>
  );
}
function FieldSettings({
  field: f,
  change,
}: {
  field: F;
  change: (v: F) => void;
}) {
  const set = (k: string, v: any) => change({ ...f, [k]: v });
  return (
    <>
      <Field label="字段名称">
        <input value={f.label} onChange={(e) => set("label", e.target.value)} />
      </Field>
      <Field label="字段标识（字母数字下划线）">
        <input value={f.key} onChange={(e) => set("key", e.target.value)} />
      </Field>
      <Field label="字段类型">
        <select value={f.type} onChange={(e) => set("type", e.target.value)}>
          {Object.entries(fieldTypes).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </Field>
      <Field label="分组标题">
        <input
          value={f.group || ""}
          onChange={(e) => set("group", e.target.value)}
        />
      </Field>
      <label className="check">
        <input
          type="checkbox"
          checked={!!f.required}
          onChange={(e) => set("required", e.target.checked)}
        />
        必填
      </label>
      {["select", "multiselect"].includes(f.type) && (
        <Field label="选项（每行一个）">
          <textarea
            value={(f.options || []).join("\n")}
            onChange={(e) =>
              set("options", e.target.value.split("\n").filter(Boolean))
            }
          />
        </Field>
      )}
      {["number", "money"].includes(f.type) && (
        <div className="form-grid">
          {["min", "max"].map((k) => (
            <Field label={k === "min" ? "最小值" : "最大值"} key={k}>
              <input
                type="number"
                value={f[k] ?? ""}
                onChange={(e) =>
                  set(
                    k,
                    e.target.value === "" ? undefined : Number(e.target.value),
                  )
                }
              />
            </Field>
          ))}
        </div>
      )}
      {f.type === "reference" && (
        <Field label="关联业务">
          <select
            value={f.ref || "student"}
            onChange={(e) => set("ref", e.target.value)}
          >
            {["student", "class", "lead", "order", "enrollment", "lesson"].map(
              (v) => (
                <option key={v} value={v}>
                  {bindings[v] || v}
                </option>
              ),
            )}
          </select>
        </Field>
      )}
      {f.type === "table" && (
        <div>
          <h4>明细字段</h4>
          {(f.fields || []).map((child: F, j: number) => (
            <div className="studio-child" key={j}>
              <input
                aria-label="明细名称"
                value={child.label}
                onChange={(e) =>
                  set(
                    "fields",
                    f.fields.map((v: F, n: number) =>
                      n === j ? { ...v, label: e.target.value } : v,
                    ),
                  )
                }
              />
              <select
                value={child.type}
                onChange={(e) =>
                  set(
                    "fields",
                    f.fields.map((v: F, n: number) =>
                      n === j ? { ...v, type: e.target.value } : v,
                    ),
                  )
                }
              >
                {Object.entries(fieldTypes)
                  .filter(([k]) => k !== "table")
                  .map(([k, l]) => (
                    <option value={k} key={k}>
                      {l}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                onClick={() =>
                  set(
                    "fields",
                    f.fields.filter((_: any, n: number) => n !== j),
                  )
                }
              >
                ×
              </button>
            </div>
          ))}
          <button
            className="button small"
            onClick={() =>
              set("fields", [
                ...(f.fields || []),
                {
                  key: "detail_" + ((f.fields || []).length + 1),
                  label: "明细项",
                  type: "text",
                },
              ])
            }
          >
            添加明细字段
          </button>
        </div>
      )}
      <details>
        <summary>条件显示</summary>
        <Field label="依赖字段标识">
          <input
            value={f.visible_when?.field || ""}
            onChange={(e) =>
              set(
                "visible_when",
                e.target.value
                  ? {
                      ...(f.visible_when || {}),
                      field: e.target.value,
                      op: f.visible_when?.op || "eq",
                    }
                  : undefined,
              )
            }
          />
        </Field>
        <Field label="显示条件值">
          <input
            value={f.visible_when?.value ?? ""}
            onChange={(e) =>
              set("visible_when", {
                ...(f.visible_when || {}),
                value: e.target.value,
              })
            }
          />
        </Field>
      </details>
      <details>
        <summary>查看与编辑岗位</summary>
        <p>查看岗位</p>
        <RoleChoices
          value={
            f.read_roles || Object.keys(roles).filter((k) => k !== "operator")
          }
          change={(v) => set("read_roles", v)}
        />
        <p>编辑岗位</p>
        <RoleChoices
          value={
            f.edit_roles || Object.keys(roles).filter((k) => k !== "operator")
          }
          change={(v) => set("edit_roles", v)}
        />
      </details>
    </>
  );
}
function DefinitionEditor({
  row,
  close,
  saved,
}: {
  row: any;
  close: () => void;
  saved: () => void;
}) {
  const [d, setD] = useState(row),
    [fields, setFields] = useState<F[]>(row.draft.fields || []),
    [selected, setSelected] = useState(0),
    [nodeId, setNodeId] = useState(""),
    [nodes, setNodes, onNodesChange] = useNodesState<any>(
      row.draft.nodes || [],
    ),
    [edges, setEdges, onEdgesChange] = useEdgesState<any>(
      row.draft.edges || [],
    ),
    [notice, setNotice] = useState(""),
    [preview, setPreview] = useState(false),
    [values, setValues] = useState<F>({}),
    [testInput, setTestInput] = useState("{}"),
    [versions, setVersions] = useState<any[]>([]),
    [busy, setBusy] = useState(false),
    [drag, setDrag] = useState(-1);
  const members = useResource<any[]>(() => api("/members"), []),
    forms = useResource<any[]>(() => api("/studio/definitions?kind=form"), []),
    workflows = useResource<any[]>(
      () => api("/studio/definitions?kind=workflow"),
      [],
    );
  const onConnect = useCallback(
    (p: any) =>
      setEdges((es) =>
        addEdge(
          {
            ...p,
            id: uid(),
            markerEnd: { type: MarkerType.ArrowClosed },
            data: { branch: "yes" },
          },
          es,
        ),
      ),
    [setEdges],
  );
  const spec = () =>
    d.kind === "form"
      ? { fields, columns: 2, workflow_id: d.draft.workflow_id || "" }
      : { nodes, edges };
  async function save() {
    const updated = await patch(`/studio/definitions/${d.id}`, {
      name: d.name,
      kind: d.kind,
      binding: d.binding,
      spec: spec(),
      version: d.version,
      enabled: d.enabled,
    });
    setD(updated);
    saved();
    return updated;
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function move(from: number, to: number) {
    if (to < 0 || to >= fields.length) return;
    const v = [...fields],
      item = v.splice(from, 1)[0];
    v.splice(to, 0, item);
    setFields(v);
    setSelected(to);
  }
  const n = nodes.find((x) => x.id === nodeId),
    nd = n?.data || {},
    setNode = (k: string, v: any) =>
      setNodes((list) =>
        list.map((x) =>
          x.id === nodeId ? { ...x, data: { ...x.data, [k]: v } } : x,
        ),
      );
  return (
    <Modal
      title={d.kind === "form" ? "表单设计器" : "流程设计器"}
      close={close}
      wide
    >
      <div className="studio-editor">
        <div className="studio-editor-top">
          <input
            className="input"
            aria-label="定义名称"
            value={d.name}
            onChange={(e) => setD({ ...d, name: e.target.value })}
          />
          <Badge
            value={d.published_version ? "published" : "draft"}
            label={
              d.published_version ? `已发布V${d.published_version}` : "尚未发布"
            }
          />
          <span>{bindings[d.binding]}</span>
          <button
            className="button small"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await save();
                setNotice("草稿已保存");
              })
            }
          >
            <Save size={14} />
            保存草稿
          </button>
          <button className="button small" onClick={() => setPreview(true)}>
            <Play size={14} />
            预览 / 试运行
          </button>
          <button
            className="button primary small"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await save();
                const r = await post(`/studio/definitions/${d.id}/publish`);
                setD(r);
                setNotice(
                  `已发布V${r.published_version}，已有实例继续使用原版本`,
                );
                saved();
              })
            }
          >
            校验并发布
          </button>
        </div>
        {notice && <Notice>{notice}</Notice>}
        {d.kind === "form" && (
          <Field label="提交后审批（可选）">
            <select
              value={d.draft.workflow_id || ""}
              onChange={(e) =>
                setD({
                  ...d,
                  draft: { ...d.draft, workflow_id: e.target.value },
                })
              }
            >
              <option value="">直接保存</option>
              {workflows.value
                ?.filter(
                  (w) => w.binding === "independent" && w.published_version,
                )
                .map((w) => (
                  <option value={w.id} key={w.id}>
                    {w.name} · V{w.published_version}
                  </option>
                ))}
            </select>
          </Field>
        )}
        <div className="studio-layout">
          <aside className="studio-palette">
            <h3>{d.kind === "form" ? "添加字段" : "添加节点"}</h3>
            {Object.entries(d.kind === "form" ? fieldTypes : nodeTypes).map(
              ([key, label]) => (
                <button
                  key={key}
                  className="button small"
                  onClick={() => {
                    if (d.kind === "form") {
                      setFields([
                        ...fields,
                        {
                          key: "field_" + uid().slice(0, 6),
                          label,
                          type: key,
                          ...(key === "table" ? { fields: [] } : {}),
                        },
                      ]);
                      setSelected(fields.length);
                    } else {
                      const id = "n" + uid().slice(0, 10);
                      setNodes((list) => [
                        ...list,
                        {
                          id,
                          position: {
                            x: 100 + Math.random() * 250,
                            y: 100 + list.length * 25,
                          },
                          data: {
                            kind: key,
                            label,
                            ...(["approval", "form"].includes(key)
                              ? { roles: ["owner"], mode: "all" }
                              : {}),
                            ...(key === "action" ? { action: "notify" } : {}),
                          },
                        },
                      ]);
                      setNodeId(id);
                    }
                  }}
                >
                  <Plus size={13} />
                  {label}
                </button>
              ),
            )}
            <p className="muted">拖拽调整位置，也可使用列表和排序按钮操作。</p>
          </aside>
          <div className="studio-canvas">
            {d.kind === "form" ? (
              <div className="studio-fields-list">
                {fields.length ? (
                  fields.map((f, j) => (
                    <div
                      key={j}
                      draggable
                      className={
                        "studio-field-tile " +
                        (selected === j ? "selected" : "")
                      }
                      onDragStart={() => setDrag(j)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        if (drag >= 0) move(drag, j);
                        setDrag(-1);
                      }}
                      onClick={() => setSelected(j)}
                    >
                      <span>{f.group || fieldTypes[f.type]}</span>
                      <strong>
                        {f.label}
                        {f.required ? " *" : ""}
                      </strong>
                      <div className="studio-dummy">
                        {f.type === "table"
                          ? "明细表格"
                          : f.type === "boolean"
                            ? "□ 是"
                            : "填写 " + f.label}
                      </div>
                      <div className="button-row">
                        <button
                          className="icon-button"
                          aria-label="上移字段"
                          onClick={(e) => {
                            e.stopPropagation();
                            move(j, j - 1);
                          }}
                        >
                          <ArrowUp size={14} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label="下移字段"
                          onClick={(e) => {
                            e.stopPropagation();
                            move(j, j + 1);
                          }}
                        >
                          <ArrowDown size={14} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label="删除字段"
                          onClick={(e) => {
                            e.stopPropagation();
                            setFields(fields.filter((_, n) => n !== j));
                            setSelected(0);
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <Empty
                    title="从左侧添加第一个字段"
                    text="发布后员工可填写，字段权限在后端再次校验。"
                  />
                )}
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={(_, node) => setNodeId(node.id)}
                fitView
                minZoom={0.1}
              >
                <FitVisibleWorkflow />
                <Background />
                <Controls />
              </ReactFlow>
            )}
          </div>
          <aside className="studio-inspector">
            <h3>属性配置</h3>
            {d.kind === "form" ? (
              fields[selected] ? (
                <FieldSettings
                  field={fields[selected]}
                  change={(f) =>
                    setFields(fields.map((v, j) => (j === selected ? f : v)))
                  }
                />
              ) : (
                <p>选择字段查看属性。</p>
              )
            ) : n ? (
              <>
                <Field label="节点名称">
                  <input
                    value={nd.label || ""}
                    onChange={(e) => setNode("label", e.target.value)}
                  />
                </Field>
                <p>类型：{nodeTypes[nd.kind as string]}</p>
                {["form", "approval"].includes(nd.kind) && (
                  <>
                    <p>处理岗位</p>
                    <RoleChoices
                      value={nd.roles || []}
                      change={(v) => setNode("roles", v)}
                    />
                    <Field label="指定成员（可多选）">
                      <select
                        multiple
                        value={nd.users || []}
                        onChange={(e) =>
                          setNode(
                            "users",
                            Array.from(e.target.selectedOptions).map(
                              (o) => o.value,
                            ),
                          )
                        }
                      >
                        {members.value?.map((m) => (
                          <option key={m.user_id} value={m.user_id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="完成规则">
                      <select
                        value={nd.mode || "all"}
                        onChange={(e) => setNode("mode", e.target.value)}
                      >
                        <option value="all">会签：全部通过</option>
                        <option value="any">任一通过</option>
                      </select>
                    </Field>
                    {nd.kind === "form" && (
                      <Field label="关联已发布表单">
                        <select
                          value={nd.form_definition_id || ""}
                          onChange={(e) =>
                            setNode("form_definition_id", e.target.value)
                          }
                        >
                          <option value="">仅确认 / 使用节点字段</option>
                          {forms.value
                            ?.filter((f) => f.published_version)
                            .map((f) => (
                              <option key={f.id} value={f.id}>
                                {f.name}
                              </option>
                            ))}
                        </select>
                      </Field>
                    )}
                  </>
                )}
                {nd.kind === "condition" && (
                  <>
                    <Field label="判断字段">
                      <input
                        value={nd.condition?.field || ""}
                        onChange={(e) =>
                          setNode("condition", {
                            ...((nd.condition || {}) as F),
                            field: e.target.value,
                            op: nd.condition?.op || "eq",
                          })
                        }
                      />
                    </Field>
                    <Field label="比较方式">
                      <select
                        value={nd.condition?.op || "eq"}
                        onChange={(e) =>
                          setNode("condition", {
                            ...((nd.condition || {}) as F),
                            op: e.target.value,
                          })
                        }
                      >
                        {[
                          ["eq", "等于"],
                          ["ne", "不等于"],
                          ["gte", "大于等于"],
                          ["lte", "小于等于"],
                          ["gt", "大于"],
                          ["lt", "小于"],
                          ["exists", "已填写"],
                        ].map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="比较值">
                      <input
                        value={nd.condition?.value ?? ""}
                        onChange={(e) =>
                          setNode("condition", {
                            ...((nd.condition || {}) as F),
                            value: e.target.value,
                          })
                        }
                      />
                    </Field>
                  </>
                )}
                {nd.kind === "join" && (
                  <Field label="汇合方式">
                    <select
                      value={nd.mode || "all"}
                      onChange={(e) => setNode("mode", e.target.value)}
                    >
                      <option value="all">等待全部分支</option>
                      <option value="any">任一分支完成</option>
                    </select>
                  </Field>
                )}
                {nd.kind === "action" && (
                  <Field label="注册的业务动作">
                    <select
                      value={nd.action || "notify"}
                      onChange={(e) => setNode("action", e.target.value)}
                    >
                      {Object.entries(bindings)
                        .filter(([k]) => k !== "independent")
                        .map(([k, l]) => (
                          <option key={k} value={k}>
                            {l}
                          </option>
                        ))}
                      <option value="notify">发送内部通知</option>
                    </select>
                  </Field>
                )}
                <button
                  className="button small"
                  onClick={() => {
                    setNodes((ns) => ns.filter((v) => v.id !== nodeId));
                    setEdges((es) =>
                      es.filter(
                        (v) => v.source !== nodeId && v.target !== nodeId,
                      ),
                    );
                    setNodeId("");
                  }}
                >
                  删除节点
                </button>
              </>
            ) : (
              <p>在画布中选择节点。</p>
            )}
            {d.kind === "workflow" && (
              <>
                <h4>连线与条件分支</h4>
                {edges.map((e, j) => (
                  <div className="studio-edge-row" key={e.id}>
                    <span>
                      {nodes.find((n) => n.id === e.source)?.data.label} →{" "}
                      {nodes.find((n) => n.id === e.target)?.data.label}
                    </span>
                    {nodes.find((n) => n.id === e.source)?.data.kind ===
                      "condition" && (
                      <select
                        value={e.data?.branch || "yes"}
                        onChange={(ev) =>
                          setEdges((es) =>
                            es.map((v, k) =>
                              k === j
                                ? {
                                    ...v,
                                    label:
                                      ev.target.value === "yes" ? "是" : "否",
                                    data: { branch: ev.target.value },
                                  }
                                : v,
                            ),
                          )
                        }
                      >
                        <option value="yes">是</option>
                        <option value="no">否</option>
                      </select>
                    )}
                    <button
                      type="button"
                      onClick={() =>
                        setEdges((es) => es.filter((v) => v.id !== e.id))
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
              </>
            )}
          </aside>
        </div>
        <footer className="studio-editor-footer">
          {d.kind === "workflow" && (
            <label className="check">
              <input
                type="checkbox"
                checked={d.enabled}
                onChange={(e) => setD({ ...d, enabled: e.target.checked })}
              />
              启用已发布版本
              {d.kind === "workflow" ? "（绑定业务将要求按此流程办理）" : ""}
            </label>
          )}
          <button
            className="button small"
            onClick={() => {
              const blob = new Blob(
                [
                  JSON.stringify(
                    {
                      name: d.name,
                      kind: d.kind,
                      binding: d.binding,
                      spec: spec(),
                    },
                    null,
                    2,
                  ),
                ],
                { type: "application/json" },
              );
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = d.name + ".json";
              a.click();
              URL.revokeObjectURL(a.href);
            }}
          >
            <Download size={14} />
            导出模板
          </button>
          <button
            className="button small"
            onClick={() =>
              run(async () =>
                setVersions(await api(`/studio/definitions/${d.id}/versions`)),
              )
            }
          >
            历史版本
          </button>
          {versions.map((v) => (
            <button
              key={v.id}
              className="button small"
              onClick={() =>
                run(async () => {
                  const r = await post(
                    `/studio/definitions/${d.id}/restore/${v.version}`,
                  );
                  setD(r);
                  setFields(r.draft.fields || []);
                  setNodes(r.draft.nodes || []);
                  setEdges(r.draft.edges || []);
                  setNotice(`V${v.version}已恢复到草稿，再发布才影响后续提交`);
                })
              }
            >
              恢复V{v.version}
            </button>
          ))}
        </footer>
      </div>
      {preview && (
        <Modal
          title="预览与无副作用试运行"
          close={() => setPreview(false)}
          wide
        >
          <div className="form-body">
            {d.kind === "form" ? (
              <FormFields fields={fields} values={values} change={setValues} />
            ) : (
              <Field label="测试数据（JSON）">
                <textarea
                  rows={8}
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                />
              </Field>
            )}
            <button
              className="button primary"
              onClick={() =>
                run(async () => {
                  await save();
                  const out = await post(
                    `/studio/definitions/${d.id}/preview`,
                    {
                      request_id: uid(),
                      values:
                        d.kind === "form" ? values : JSON.parse(testInput),
                    },
                  );
                  setNotice(
                    out.reachable_nodes
                      ? "试运行路径：" + out.reachable_nodes.join(" → ")
                      : "字段校验通过",
                  );
                  setPreview(false);
                })
              }
            >
              校验并试运行
            </button>
          </div>
        </Modal>
      )}
    </Modal>
  );
}

export function StudioPage() {
  const defs = useResource<any[]>(() => api("/studio/definitions"), []),
    tasks = useResource<any[]>(() => api("/studio/tasks"), []),
    instances = useResource<any[]>(() => api("/studio/instances"), []),
    submissions = useResource<any[]>(() => api("/studio/submissions"), []);
  const [tab, setTab] = useState(can("tenant.manage") ? "design" : "forms"),
    [editor, setEditor] = useState<any>(null),
    [create, setCreate] = useState(false),
    [newName, setNewName] = useState(""),
    [kind, setKind] = useState("form"),
    [binding, setBinding] = useState("independent"),
    [notice, setNotice] = useState(""),
    [form, setForm] = useState<any>(null),
    [values, setValues] = useState<F>({}),
    [recordId, setRecordId] = useState(""),
    [selectedTask, setSelectedTask] = useState<any>(null),
    [taskDetail, setTaskDetail] = useState<any>(null),
    [taskNote, setTaskNote] = useState(""),
    [actual, setActual] = useState(false),
    [taskValues, setTaskValues] = useState<F>({}),
    [requestId, setRequestId] = useState(uid()),
    [flowModal, setFlowModal] = useState<any>(null),
    [payload, setPayload] = useState("{}");
  async function run(fn: () => Promise<void>) {
    try {
      await fn();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function refresh() {
    defs.refresh();
    tasks.refresh();
    instances.refresh();
    submissions.refresh();
  }
  async function decide(decision: string) {
    await post(`/studio/tasks/${selectedTask.id}/decision`, {
      decision,
      note: taskNote,
      values:
        selectedTask.node_type === "form"
          ? {
              ...Object.fromEntries(
                Object.entries(taskValues).filter(([key]) =>
                  taskFields.some(
                    (f: F) => f.key === key && f.editable !== false,
                  ),
                ),
              ),
              ...(["refund", "expense", "reversal"].includes(
                selectedTask.binding,
              )
                ? { actual_confirmed: actual }
                : {}),
            }
          : {},
    });
    setSelectedTask(null);
    setTaskDetail(null);
    refresh();
    setNotice("待办处理结果已保存");
  }
  const taskFields =
    taskDetail?.definition_spec?.nodes?.find(
      (n: any) => n.id === selectedTask?.node_id,
    )?.data?.fields || [];
  return (
    <>
      <PageTitle
        eyebrow="FORMS & WORKFLOWS"
        title="机构的表单，按自己的方式运转"
        text="设计、发布、填写、审批；业务权限与财务课时规则统一执行。"
      />
      {notice && <Notice>{notice}</Notice>}
      <div className="tabs">
        {[
          ["design", "设计与模板"],
          ["forms", "填写表单"],
          ["tasks", "审批待办"],
          ["instances", "我的流程"],
          ["submissions", "提交记录"],
        ]
          .filter(([k]) => k !== "design" || can("tenant.manage"))
          .map(([k, l]) => (
            <button
              className={"tab " + (tab === k ? "active" : "")}
              key={k}
              onClick={() => setTab(k)}
            >
              {l}
              {k === "tasks" && tasks.value?.length
                ? " · " + tasks.value.length
                : ""}
            </button>
          ))}
      </div>
      {tab === "design" && (
        <section className="panel ops-section">
          <header>
            <div>
              <h2>表单与流程定义</h2>
              <p>草稿与已发布版本分开保存，模板启用后才约束业务。</p>
            </div>
            <div className="button-row">
              <button
                className="button primary"
                onClick={() => setCreate(true)}
              >
                <Plus size={14} />
                新建设计
              </button>
              <label className="button small">
                <Upload size={14} />
                导入模板
                <input
                  type="file"
                  hidden
                  accept="application/json"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    run(async () => {
                      const value = JSON.parse(await f.text());
                      const d = await post("/studio/definitions", {
                        name: value.name,
                        kind: value.kind,
                        binding: value.binding,
                        spec: value.spec,
                      });
                      setEditor(d);
                      defs.refresh();
                    });
                  }}
                />
              </label>
              <button
                className="button small"
                onClick={() =>
                  run(async () => {
                    const templates = await api("/studio/templates");
                    for (const t of templates) {
                      if (
                        defs.value?.some(
                          (d) => d.name === t.name && d.kind === t.kind,
                        )
                      )
                        continue;
                      await post("/studio/definitions", t);
                    }
                    defs.refresh();
                    setNotice("内置模板已加入草稿，发布和启用后生效");
                  })
                }
              >
                加载招生 / 教务 / 财务模板
              </button>
            </div>
          </header>
          <div className="studio-definition-grid">
            {defs.value?.map((d) => (
              <button
                className="panel studio-definition"
                key={d.id}
                onClick={() => setEditor(d)}
              >
                <span>
                  {d.kind === "form" ? "表单" : "流程"} · {bindings[d.binding]}
                </span>
                <h3>{d.name}</h3>
                <Badge
                  value={d.enabled ? "active" : "draft"}
                  label={
                    d.enabled
                      ? "已启用"
                      : d.published_version
                        ? "已发布，未启用"
                        : "草稿"
                  }
                />
                <small>V{d.published_version} · 点击编辑</small>
              </button>
            ))}
          </div>
          {!defs.value?.length && (
            <Empty
              title="从一张表单或一个流程开始"
              text="可先加载内置模板，再按机构习惯调整。"
            />
          )}
        </section>
      )}
      {tab === "forms" && (
        <section className="panel ops-section">
          <h2>已发布表单</h2>
          <div className="studio-definition-grid">
            {defs.value
              ?.filter((d) => d.kind === "form" && d.published_version)
              .map((d) => (
                <button
                  key={d.id}
                  className="panel studio-definition"
                  onClick={() =>
                    run(async () => {
                      const f = await api(`/studio/forms/${d.id}`);
                      setForm(f);
                      setValues({});
                      setRecordId("");
                      setRequestId(uid());
                    })
                  }
                >
                  <h3>{d.name}</h3>
                  <span>
                    {bindings[d.binding]} · V{d.published_version}
                  </span>
                </button>
              ))}
          </div>
          {!defs.value?.some(
            (d) => d.kind === "form" && d.published_version,
          ) && (
            <Empty
              title="暂无已发布表单"
              text="负责人发布后，符合岗位权限的员工可在这里填写。"
            />
          )}
        </section>
      )}
      {tab === "tasks" && (
        <section className="panel ops-section">
          <h2>当前待办</h2>
          {tasks.error && <Notice tone="error">{tasks.error}</Notice>}
          {tasks.value?.length ? (
            tasks.value.map((t) => (
              <div className="ops-keyline" key={t.id}>
                <div>
                  <strong>{t.name}</strong>
                  <p>
                    {t.node_label} · {bindings[t.binding]}
                  </p>
                </div>
                <Badge value={t.status} />
                {t.status === "unassigned" && can("tenant.manage") ? (
                  <button
                    className="button"
                    onClick={() =>
                      run(async () => {
                        const members = await api("/members");
                        const id = window.prompt(
                          "填写处理人员编号\n" +
                            members
                              .map((m: any) => m.name + "：" + m.user_id)
                              .join("\n"),
                        );
                        if (!id) return;
                        await post(
                          `/studio/tasks/${t.id}/assign?user_id=${id}`,
                        );
                        tasks.refresh();
                      })
                    }
                  >
                    分配处理人
                  </button>
                ) : (
                  <button
                    className="button primary small"
                    onClick={() =>
                      run(async () => {
                        setSelectedTask(t);
                        setTaskNote("");
                        setActual(false);
                        setTaskValues({});
                        setTaskDetail(
                          await api(`/studio/instances/${t.instance_id}`),
                        );
                      })
                    }
                  >
                    {t.can_decide ? "查看并处理" : "查看进度"}
                  </button>
                )}
              </div>
            ))
          ) : (
            <Empty
              title="当前没有待办"
              text="审批、填写或财务确认任务会出现在这里。"
            />
          )}
        </section>
      )}
      {tab === "instances" && (
        <section className="panel ops-section">
          <header>
            <h2>流程记录</h2>
            <div className="button-row">
              {defs.value
                ?.filter((d) => d.kind === "workflow" && d.published_version)
                .map((d) => (
                  <button
                    key={d.id}
                    className="button small"
                    onClick={() => {
                      setFlowModal(d);
                      setPayload("{}");
                      setRecordId("");
                      setRequestId(uid());
                    }}
                  >
                    发起：{d.name}
                  </button>
                ))}
            </div>
          </header>
          {instances.value?.map((r) => (
            <div className="ops-keyline" key={r.id}>
              <div>
                <strong>{r.name}</strong>
                <p>
                  V{r.definition_version} · {date(r.created_at, true)}
                </p>
              </div>
              <Badge value={r.status} />
              {["returned", "rejected", "withdrawn"].includes(r.status) && (
                <button
                  className="button small"
                  onClick={() =>
                    run(async () => {
                      const d = await api(`/studio/instances/${r.id}`);
                      setFlowModal({
                        ...defs.value?.find((x) => x.id === r.definition_id),
                        resubmit_id: r.id,
                      });
                      setRecordId(r.record_id);
                      setPayload(JSON.stringify(d.payload, null, 2));
                      setRequestId(uid());
                    })
                  }
                >
                  修改后重新提交
                </button>
              )}
              {["running", "returned", "approved"].includes(r.status) && (
                <button
                  className="button small"
                  onClick={() =>
                    run(async () => {
                      await post(`/studio/instances/${r.id}/withdraw`);
                      refresh();
                    })
                  }
                >
                  撤回
                </button>
              )}
              {r.status === "approved" && (
                <button
                  className="button primary small"
                  onClick={() =>
                    run(async () => {
                      if (
                        !window.confirm(
                          "已核对本次业务实际发生，确认按审批内容登记？",
                        )
                      )
                        return;
                      await post(`/studio/instances/${r.id}/apply`, {
                        actual_confirmed: true,
                      });
                      refresh();
                      setNotice("已按审批内容登记业务");
                    })
                  }
                >
                  执行已审批业务
                </button>
              )}
            </div>
          ))}
        </section>
      )}
      {tab === "submissions" && (
        <section className="panel ops-section">
          <h2>表单提交记录</h2>
          {submissions.value?.map((s) => (
            <div className="ops-keyline" key={s.id}>
              <div>
                <strong>
                  {s.name} · V{s.definition_version}
                </strong>
                <p>{date(s.created_at, true)}</p>
                <dl className="studio-values">
                  {Object.entries(s.values).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <dt>{k}</dt>
                      <dd>
                        {typeof v === "object" ? JSON.stringify(v) : String(v)}
                      </dd>
                    </React.Fragment>
                  ))}
                </dl>
              </div>
              <Badge value={s.status} />
            </div>
          ))}
        </section>
      )}
      {create && (
        <Modal title="新建表单或流程" close={() => setCreate(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const spec =
                  kind === "form"
                    ? { fields: [] }
                    : {
                        nodes: [
                          {
                            id: "start",
                            position: { x: 50, y: 100 },
                            data: { kind: "start", label: "开始" },
                          },
                          {
                            id: "end",
                            position: { x: 400, y: 100 },
                            data: { kind: "end", label: "完成" },
                          },
                        ],
                        edges: [
                          { id: "first", source: "start", target: "end" },
                        ],
                      };
                const r = await post("/studio/definitions", {
                  name: newName,
                  kind,
                  binding,
                  spec,
                });
                setCreate(false);
                setEditor(r);
                defs.refresh();
              });
            }}
          >
            <div className="form-body">
              <Field label="名称">
                <input
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </Field>
              <Field label="类型">
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="form">表单</option>
                  <option value="workflow">流程</option>
                </select>
              </Field>
              <Field label="绑定业务">
                <select
                  value={binding}
                  onChange={(e) => setBinding(e.target.value)}
                >
                  {Object.entries(bindings).map(([k, l]) => (
                    <option key={k} value={k}>
                      {l}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="form-footer">
              <button className="button primary">创建设计</button>
            </div>
          </form>
        </Modal>
      )}
      {editor && (
        <DefinitionEditor
          row={editor}
          close={() => setEditor(null)}
          saved={refresh}
        />
      )}
      {form && (
        <Modal title={form.definition.name} close={() => setForm(null)} wide>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const writable = Object.fromEntries(
                  Object.entries(values).filter(
                    ([key]) =>
                      form.fields.find((f: F) => f.key === key)?.editable !==
                      false,
                  ),
                );
                await post(`/studio/forms/${form.definition.id}/submissions`, {
                  values: writable,
                  record_id: recordId,
                  request_id: requestId,
                  definition_version: form.version,
                });
                setForm(null);
                refresh();
                setNotice("表单已提交");
              });
            }}
          >
            <div className="form-body">
              {form.definition.binding !== "independent" && (
                <Field label="关联业务记录（可选）">
                  <RefInput
                    f={{
                      ref:
                        (
                          {
                            refund: "order",
                            transfer: "enrollment",
                            reversal: "ledger",
                          } as any
                        )[form.definition.binding] || form.definition.binding,
                    }}
                    value={recordId}
                    change={setRecordId}
                  />
                </Field>
              )}
              <FormFields
                fields={form.fields}
                values={values}
                change={setValues}
              />
            </div>
            <div className="form-footer">
              <button className="button primary">提交表单</button>
            </div>
          </form>
        </Modal>
      )}
      {flowModal && (
        <Modal
          title={
            flowModal.resubmit_id
              ? "修改并重新提交审批"
              : "发起 " + flowModal.name
          }
          close={() => setFlowModal(null)}
          wide
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const path = flowModal.resubmit_id
                  ? `/studio/instances/${flowModal.resubmit_id}/resubmit`
                  : `/studio/workflows/${flowModal.id}/instances`;
                await post(path, {
                  record_id: recordId,
                  payload: JSON.parse(payload),
                  request_id: requestId,
                });
                setFlowModal(null);
                refresh();
                setNotice("流程已发起");
              });
            }}
          >
            <div className="form-body">
              <Notice>
                招生、教务和财务页面也可直接提交对应业务审批。这里提供通用流程发起入口。
              </Notice>
              {flowModal.binding !== "independent" && (
                <Field label="关联业务记录（可选）">
                  <RefInput
                    f={{
                      ref:
                        (
                          {
                            refund: "order",
                            transfer: "enrollment",
                            reversal: "ledger",
                          } as any
                        )[flowModal.binding] || flowModal.binding,
                    }}
                    value={recordId}
                    change={setRecordId}
                  />
                </Field>
              )}
              <WorkflowInput
                definition={flowModal}
                payload={payload}
                change={setPayload}
              />
            </div>
            <div className="form-footer">
              <button className="button primary">提交审批</button>
            </div>
          </form>
        </Modal>
      )}
      {selectedTask && (
        <Modal
          title={selectedTask.node_label}
          close={() => {
            setSelectedTask(null);
            setTaskDetail(null);
          }}
          wide
        >
          <div className="form-body">
            {!taskDetail ? (
              <Loading />
            ) : (
              <>
                <h3>{selectedTask.name}</h3>
                <dl className="studio-values">
                  {Object.entries(
                    taskDetail.payload.business ||
                      taskDetail.payload.values ||
                      taskDetail.payload,
                  ).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <dt>{businessLabels[k] || k}</dt>
                      <dd>
                        {typeof v === "object" ? JSON.stringify(v) : String(v)}
                      </dd>
                    </React.Fragment>
                  ))}
                </dl>
                {taskFields.length > 0 && (
                  <FormFields
                    fields={taskFields}
                    values={taskValues}
                    change={setTaskValues}
                  />
                )}
                <Field label="处理说明">
                  <textarea
                    value={taskNote}
                    onChange={(e) => setTaskNote(e.target.value)}
                  />
                </Field>
                {selectedTask.node_type === "form" &&
                  ["refund", "expense", "reversal"].includes(
                    selectedTask.binding,
                  ) && (
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={actual}
                        onChange={(e) => setActual(e.target.checked)}
                      />
                      已核对票据及实际发生情况，确认登记
                    </label>
                  )}
                {!selectedTask.can_decide ? (
                  <Notice>当前待办由其他成员处理，可查看进度。</Notice>
                ) : (
                  <div className="button-row">
                    <button
                      className="button primary"
                      onClick={() => run(() => decide("approve"))}
                    >
                      {selectedTask.node_type === "form"
                        ? "确认填写 / 实际发生"
                        : "审批通过"}
                    </button>
                    <button
                      className="button"
                      onClick={() => run(() => decide("return"))}
                    >
                      退回修改
                    </button>
                    <button
                      className="button"
                      onClick={() => run(() => decide("reject"))}
                    >
                      驳回
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function WorkflowInput({
  definition,
  payload,
  change,
}: {
  definition: any;
  payload: string;
  change: (s: string) => void;
}) {
  let parsed: any = {};
  try {
    parsed = JSON.parse(payload);
  } catch {}
  const binding = definition.binding;
  let fields: any[] =
    specs[binding]?.fields.map((f) => ({
      ...f,
      type:
        (
          {
            ref: "reference",
            check: "boolean",
            datetime: "datetime",
            guardians: "table",
            percent: "number",
          } as any
        )[f.type || "text"] ||
        f.type ||
        "text",
      fields:
        f.type === "guardians"
          ? [
              { key: "name", label: "家长", type: "text", required: true },
              { key: "relationship", label: "关系", type: "text" },
              { key: "contact", label: "电话", type: "text" },
            ]
          : undefined,
    })) || [];
  if (binding === "refund")
    fields = [
      {
        key: "amount_fen",
        label: "退款金额（元）",
        type: "money",
        required: true,
      },
      { key: "reason", label: "退款原因", type: "textarea", required: true },
    ];
  if (binding === "reversal")
    fields = [
      { key: "note", label: "冲正原因", type: "textarea", required: true },
    ];
  if (binding === "transfer")
    fields = [
      { key: "class_id", label: "新班级", type: "reference", ref: "class" },
      { key: "reason", label: "调班原因", type: "textarea", required: true },
      {
        key: "effective_at",
        label: "生效时间（留空为当前）",
        type: "datetime",
      },
    ];
  if (binding === "independent")
    fields = definition.draft?.nodes?.find((n: any) => n.data.kind === "form")
      ?.data.fields || [{ key: "notes", label: "申请说明", type: "textarea" }];
  const values = { ...(parsed.business || parsed.values || parsed) };
  for (const f of fields)
    if (f.type === "money" && values[f.key] != null)
      values[f.key] = String(Number(values[f.key]) / 100);
  return (
    <>
      <FormFields
        fields={fields}
        values={values}
        change={(next) => {
          const data = { ...next };
          for (const f of fields) {
            if (f.type === "money" && data[f.key] !== undefined)
              data[f.key] = Math.round(Number(data[f.key]) * 100);
            if (f.type === "number" && data[f.key] !== undefined)
              data[f.key] = Number(data[f.key]);
          }
          if (binding === "refund")
            Object.assign(data, { withdrawal: false, enrollment_ids: [] });
          if (binding === "transfer")
            data.effective_at = data.effective_at
              ? new Date(data.effective_at).toISOString()
              : null;
          change(
            JSON.stringify(
              binding === "independent" ? { values: data } : { business: data },
            ),
          );
        }}
      />
      {binding === "refund" && (
        <Notice>
          退读退费请从财务台账的退款入口发起，可同时核对课时并选择结束的报名。
        </Notice>
      )}
    </>
  );
}

function FitVisibleWorkflow() {
  const ready = useNodesInitialized(),
    { fitView } = useReactFlow();
  useEffect(() => {
    if (!ready) return;
    const canvas = document.querySelector(".studio-canvas");
    if (!canvas) return;
    let frame = 0;
    const fit = () => {
      if (canvas.getBoundingClientRect().width > 0) {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          void fitView({ padding: 0.18, minZoom: 0.1, duration: 0 });
        });
      }
    };
    const observer = new ResizeObserver(fit);
    observer.observe(canvas);
    fit();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [ready, fitView]);
  return null;
}
