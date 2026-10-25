import React, { useState } from "react";
import { api, post, patch, roles, date, can } from "./api";
import {
  Field,
  Notice,
  PageTitle,
  useResource,
  Loading,
  Badge,
  Modal,
} from "./ui";
const roleOptions = [
  "owner",
  "admissions",
  "teacher",
  "scheduler",
  "academic_admin",
  "revenue_viewer",
  "finance",
  "content_ops",
];
type Grant = {
  key: string;
  label: string;
  description: string;
  scope: string;
  permissions: string[];
};
export function RoleChecks({
  value,
  onChange,
  catalog = [],
}: {
  value: string[];
  onChange: (v: string[]) => void;
  catalog?: Grant[];
}) {
  return (
    <div className="authorization-options">
      {roleOptions.map((r) => {
        const spec = catalog.find((c) => c.key === r);
        return (
          <label
            key={r}
            className={
              value.includes(r) ? "grant-option selected" : "grant-option"
            }
          >
            <input
              type="checkbox"
              checked={value.includes(r)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...value, r]
                    : value.filter((x) => x !== r),
                )
              }
            />
            <span>
              <strong>{roles[r]}</strong>
              {spec && <small>{spec.description}</small>}
            </span>
          </label>
        );
      })}
    </div>
  );
}
export function AuthorizationPage() {
  return (
    <>
      <PageTitle
        eyebrow="PEOPLE & AUTHORIZATION"
        title="成员与功能授权"
        text="一个人可以兼任多个岗位。负责人统一授权，每项操作仍受机构和业务归属限制。"
      />
      <StaffPanel />
    </>
  );
}
export function StaffPanel() {
  const editable = can("members.manage");
  const members = useResource<any[]>(() => api("/members"), [], 15000);
  const catalog = useResource<{ items: Grant[] }>(
    () =>
      editable ? api("/authorization-catalog") : Promise.resolve({ items: [] }),
    [],
  );
  const invitations = useResource<any[]>(
    () => (editable ? api("/member-invitations") : Promise.resolve([])),
    [],
  );
  const [email, setEmail] = useState(""),
    [chosen, setChosen] = useState(["teacher"]);
  const [editing, setEditing] = useState<any>(null),
    [grants, setGrants] = useState<string[]>([]);
  const [message, setMessage] = useState(""),
    [link, setLink] = useState(""),
    [saving, setSaving] = useState(false);
  const items = catalog.value?.items || [];
  async function save(m: any, selected: string[], status = m.status) {
    if (saving) return;
    setSaving(true);
    try {
      await patch("/members/" + m.id, {
        roles: selected,
        status,
        authz_version: m.authz_version,
      });
      members.refresh();
      setEditing(null);
      window.dispatchEvent(new Event("permissions-refresh"));
      setMessage("功能授权已保存；后续请求与后台任务按最新授权校验。");
    } catch (e) {
      setMessage((e as Error).message);
      members.refresh();
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="panel settings-card full">
      <h2>团队与岗位</h2>
      <p>
        支持一人多岗和多人协作。授课、排班、教务、营收查看及财务分别授权，兼任不会扩大其他模块的数据范围。
      </p>
      {message && <Notice>{message}</Notice>}
      {(members.error || catalog.error) && (
        <Notice tone="error">{members.error || catalog.error}</Notice>
      )}
      {members.loading ? (
        <Loading />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>成员</th>
                <th>邮箱 / 状态</th>
                <th>已授功能</th>
                {editable && <th>授权操作</th>}
              </tr>
            </thead>
            <tbody>
              {members.value?.map((m) => (
                <tr key={m.id}>
                  <td>
                    <strong>{m.name}</strong>
                    <small className="muted"> · V{m.authz_version}</small>
                  </td>
                  <td>
                    {m.email || "—"}
                    <br />
                    <Badge value={m.status} />
                  </td>
                  <td>
                    <div className="grant-tags">
                      {m.roles.map((r: string) => (
                        <span key={r}>{roles[r] || r}</span>
                      ))}
                    </div>
                    {m.status !== "active" && (
                      <small>已停用，所有业务授权暂停</small>
                    )}
                  </td>
                  {editable && (
                    <td>
                      <div className="button-row">
                        <button
                          className="button small"
                          onClick={() => {
                            setEditing(m);
                            setGrants(m.roles);
                            setMessage("");
                          }}
                        >
                          调整授权
                        </button>
                        <button
                          className="button link"
                          disabled={saving}
                          onClick={() =>
                            save(
                              m,
                              m.roles,
                              m.status === "active" ? "disabled" : "active",
                            )
                          }
                        >
                          {m.status === "active" ? "停用" : "恢复"}
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editable && (
        <>
          <details className="authorization-reference">
            <summary>查看功能授权与数据范围</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>授权类型</th>
                    <th>功能</th>
                    <th>数据范围</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.key}>
                      <td>{c.label}</td>
                      <td>{c.description}</td>
                      <td>{c.scope}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <h3>邀请员工</h3>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (saving) return;
              setSaving(true);
              try {
                const out = await post("/member-invitations", {
                  email,
                  roles: chosen,
                });
                setMessage(out.message);
                setLink(out.development_link || "");
                invitations.refresh();
                setEmail("");
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setSaving(false);
              }
            }}
          >
            <Field label="员工邮箱">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <RoleChecks value={chosen} onChange={setChosen} catalog={items} />
            <button
              className="button primary"
              disabled={saving || !chosen.length}
            >
              发送24小时邀请
            </button>
          </form>
          {link && (
            <Notice>
              <a href={link}>打开员工加入页面</a>
            </Notice>
          )}
          {invitations.value?.map((inv) => (
            <div className="ops-keyline" key={inv.id}>
              <span>
                {inv.email} ·{" "}
                {inv.roles.map((r: string) => roles[r]).join(" / ")}
              </span>
              <Badge value={inv.status} />
              <span>{date(inv.expires_at, true)}</span>
              {inv.status === "pending" && (
                <button
                  className="button link"
                  onClick={async () => {
                    try {
                      await api("/member-invitations/" + inv.id, {
                        method: "DELETE",
                      });
                      invitations.refresh();
                    } catch (e) {
                      setMessage((e as Error).message);
                    }
                  }}
                >
                  撤销
                </button>
              )}
            </div>
          ))}
        </>
      )}
      {editing && (
        <Modal
          title={"调整授权 · " + editing.name}
          close={() => setEditing(null)}
          wide
        >
          <div className="form-body">
            <p>
              可同时勾选多个岗位。负责人授权包含本机构全部功能，请按实际职责授予。
            </p>
            <RoleChecks value={grants} onChange={setGrants} catalog={items} />
            <section className="authorization-preview">
              <h3>本次授权范围</h3>
              {grants.length ? (
                <ul>
                  {items
                    .filter((c) =>
                      grants.includes("owner")
                        ? c.key === "owner"
                        : grants.includes(c.key),
                    )
                    .map((c) => (
                      <li key={c.key}>
                        <strong>{c.label}：</strong>
                        {c.scope}
                      </li>
                    ))}
                </ul>
              ) : (
                <p>至少选择一项授权；如需撤销全部访问，请停用成员。</p>
              )}
            </section>
            <button
              className="button primary"
              disabled={saving || !grants.length}
              onClick={() => save(editing, grants)}
            >
              保存授权
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
export function InvitePage() {
  const token = new URLSearchParams(location.search).get("token") || "",
    data = useResource<any>(
      () => api("/auth/invitation?token=" + encodeURIComponent(token)),
      [token],
    );
  const [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="auth-shell">
      <aside className="auth-story">
        <div className="brand">
          <span className="brand-mark">知</span>
          <div>
            知营<small>团队邀请</small>
          </div>
        </div>
        <h1>
          加入你的机构，
          <br />
          从自己的工作开始。
        </h1>
        <p>员工无需创建机构。机构和岗位由邀请确定。</p>
      </aside>
      <main className="auth-main">
        <form
          className="auth-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await post("/auth/accept-invitation", { token, name, password });
              location.assign("/");
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h1>{data.value?.tenant_name || "接受机构邀请"}</h1>
          {data.loading ? (
            <Loading />
          ) : data.error ? (
            <Notice tone="error">{data.error}</Notice>
          ) : (
            <>
              <p>
                {data.value.email} ·{" "}
                {data.value.roles.map((r: string) => roles[r]).join(" / ")}
              </p>
              <Field label="姓名（新账号必填）">
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="密码（已有账号填写当前密码）">
                <input
                  type="password"
                  minLength={12}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </Field>
              <button className="button primary" disabled={busy}>
                接受邀请并进入机构
              </button>
            </>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          <a href="/">返回登录</a>
        </form>
      </main>
    </div>
  );
}
