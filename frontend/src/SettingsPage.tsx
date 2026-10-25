import { AISettingsPanel } from "./AIControls";
import { can } from "./api";
import { StaffPanel } from "./StaffPage";
import React, { useState } from "react";
import {
  Plus,
  KeyRound,
  Link2,
  QrCode,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import {
  api,
  post,
  patch,
  roles,
  platforms,
  date,
  money,
  localInput,
} from "./api";
import {
  Field,
  Notice,
  PageTitle,
  Badge,
  Empty,
  Modal,
  useResource,
  AsyncButton,
} from "./ui";
function IntegrationForm({
  provider,
  close,
  saved,
}: {
  provider: string;
  close: () => void;
  saved: () => void;
}) {
  const [secret, setSecret] = useState(""),
    [values, setValues] = useState<Record<string, string>>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal
      title={
        provider === "aliyun"
          ? "连接阿里云百炼"
          : provider === "deepseek"
            ? "连接 DeepSeek 官方 API"
            : "连接企业微信官方客服"
      }
      close={close}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/integrations/" + provider, {
              method: "PUT",
              body: JSON.stringify({ secret, config: values }),
            });
            setSecret("");
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
          <Notice>
            凭证在服务端加密保存。已保存的值不会返回界面，更新时请完整替换。
          </Notice>
          {error && <Notice tone="error">{error}</Notice>}
          <Field label={provider !== "wecom" ? "API Key" : "客服 Secret"}>
            <input
              type="password"
              autoComplete="new-password"
              value={secret}
              required
              onChange={(e) => setSecret(e.target.value)}
            />
          </Field>
          {(provider === "deepseek"
            ? []
            : provider === "aliyun"
              ? [
                  ["base_url", "媒体API地域地址（留空为北京）"],
                  ["text_base_url", "文字与视觉模型业务空间地址（可选）"],
                ]
              : [
                  ["corpid", "企业 ID"],
                  ["open_kfid", "客服账号 ID"],
                  ["token", "回调 Token"],
                  ["encoding_aes_key", "回调 EncodingAESKey"],
                ]
          ).map(([k, label]) => (
            <Field key={k} label={label}>
              <input
                required={provider === "wecom"}
                type={
                  ["token", "encoding_aes_key"].includes(k)
                    ? "password"
                    : "text"
                }
                value={values[k] || ""}
                onChange={(e) => setValues({ ...values, [k]: e.target.value })}
                placeholder={
                  k === "base_url"
                    ? "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    : ""
                }
              />
            </Field>
          ))}
        </div>
        <div className="form-footer">
          <button className="button primary" disabled={busy}>
            保存连接
          </button>
        </div>
      </form>
    </Modal>
  );
}
function Accounts() {
  const data = useResource<any[]>(() => api("/social-accounts"), []),
    [form, setForm] = useState(false),
    [platform, setPlatform] = useState("xiaohongshu"),
    [name, setName] = useState(""),
    [error, setError] = useState(""),
    [login, setLogin] = useState<any>(null),
    [qr, setQr] = useState(""),
    [busy, setBusy] = useState(false);
  async function action(a: any, op: string) {
    setBusy(true);
    try {
      const result = await post("/social-accounts/" + a.id + "/" + op);
      if (op === "login") {
        setLogin(a);
        const image = await post("/social-accounts/" + a.id + "/login-image");
        setQr(image.image || image.qr_image || "");
      }
      if (op === "login-image") {
        setQr(result.image || "");
      }
      if (op === "status") {
        data.refresh();
        if (result.status === "connected") setLogin(null);
      }
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel settings-card full">
      <div className="button-row" style={{ justifyContent: "space-between" }}>
        <h2>机构发布账号</h2>
        <button className="button small" onClick={() => setForm(true)}>
          <Plus size={13} />
          添加账号
        </button>
      </div>
      <p>机构独立云端浏览器。首次登录及过期重登由机构扫码完成。</p>
      {error && <Notice tone="error">{error}</Notice>}
      {data.value?.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>账号名称</th>
                <th>平台</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.value.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{platforms[a.platform]}</td>
                  <td>
                    <Badge value={a.status} />
                  </td>
                  <td>
                    <div className="button-row">
                      <button
                        className="button small"
                        disabled={busy}
                        onClick={() => action(a, "login")}
                      >
                        <QrCode size={12} />
                        扫码登录
                      </button>
                      <button
                        className="button link"
                        disabled={busy}
                        onClick={() => action(a, "status")}
                      >
                        检查连接
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty text="添加机构自己的小红书、抖音和视频号账号。" />
      )}
      {form && (
        <Modal title="添加发布账号" close={() => setForm(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await post("/social-accounts", { name, platform });
                setForm(false);
                data.refresh();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <div className="form-body">
              <Field label="平台">
                <select
                  value={platform}
                  onChange={(e) => setPlatform(e.target.value)}
                >
                  {Object.entries(platforms).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="账号备注">
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
            </div>
            <div className="form-footer">
              <button className="button primary">添加账号</button>
            </div>
          </form>
        </Modal>
      )}
      {login && (
        <Modal title="机构账号扫码登录" close={() => setLogin(null)}>
          <div className="form-body">
            <Notice>
              请用对应平台手机应用扫码。如果出现验证码或安全验证，请先在账号端完成处理。
            </Notice>
            {qr ? (
              <img alt="平台登录二维码" src={qr} style={{ width: "100%" }} />
            ) : (
              <Notice>正在准备登录界面，请刷新二维码。</Notice>
            )}
            <div className="button-row">
              <button
                className="button"
                onClick={() => action(login, "login-image")}
              >
                刷新二维码
              </button>
              <button
                className="button"
                onClick={() => action(login, "status")}
              >
                已扫码，检查登录状态
              </button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  );
}
export default function SettingsPage({
  role,
  refreshMe,
}: {
  role: string;
  refreshMe: () => void;
}) {
  const info = useResource<any>(() => api("/tenant"), []),
    usage = useResource<any>(
      () =>
        can("usage.read")
          ? api("/usage")
          : Promise.resolve({ items: [], buckets: [], quotas: {} }),
      [],
    ),
    integrations = useResource<any[]>(
      () => (role === "owner" ? api("/integrations") : Promise.resolve([])),
      [],
    ),
    [settings, setSettings] = useState<any>(null),
    [notice, setNotice] = useState(""),
    [connection, setConnection] = useState("");
  const values = settings || info.value?.settings || {},
    set = (key: string, v: any) => setSettings({ ...values, [key]: v }),
    editable = role === "owner";
  async function save() {
    try {
      await patch("/tenant", {
        brand: values.brand || "",
        audience: values.audience || "",
        tone: values.tone || "清楚、真实、有用",
        publishing_enabled: !!values.publishing_enabled,
        auto_publish: !!values.auto_publish,
        funding: values.funding || "platform",
      });
      setNotice("机构设置已保存");
      info.refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  const resourceLabels: Record<string, string> = {
    text_tokens: "文字用量 Token",
    images: "AI图片（张）",
    video_seconds: "AI视频（秒）",
    speech_characters: "配音字符",
    cost_fen: "费用上限（分）",
  };
  return (
    <>
      <PageTitle
        eyebrow="ORGANIZATION"
        title="机构与连接"
        text="让团队、资料和工具，在同一处准备就绪。"
      />
      {notice && <Notice>{notice}</Notice>}
      {info.error && <Notice tone="error">{info.error}</Notice>}
      <div className="settings-grid">
        <section className="panel settings-card">
          <h2>品牌与自动运行</h2>
          <p>内容与客服将共用机构资料；课程、价格和赛事依据请到知识库确认。</p>
          <Field label="机构介绍">
            <textarea
              disabled={!editable}
              value={values.brand || ""}
              onChange={(e) => set("brand", e.target.value)}
            />
          </Field>
          <Field label="主要受众">
            <input
              disabled={!editable}
              value={values.audience || ""}
              onChange={(e) => set("audience", e.target.value)}
            />
          </Field>
          <Field label="表达风格">
            <input
              disabled={!editable}
              value={values.tone || ""}
              onChange={(e) => set("tone", e.target.value)}
            />
          </Field>
          <Field label="模型费用来源">
            <select
              disabled={!editable}
              value={values.funding || "platform"}
              onChange={(e) => set("funding", e.target.value)}
            >
              <option value="platform">平台赠送额度</option>
              <option value="byok">机构自带 Key</option>
            </select>
          </Field>
          <label className="check">
            <input
              type="checkbox"
              disabled={!editable}
              checked={!!values.publishing_enabled}
              onChange={(e) => set("publishing_enabled", e.target.checked)}
            />
            授权已连接的机构账号执行发布
          </label>
          <label className="check">
            <input
              type="checkbox"
              disabled={!editable}
              checked={!!values.auto_publish}
              onChange={(e) => set("auto_publish", e.target.checked)}
            />
            允许已启用的内容计划自动创作和发布
          </label>
          {editable && (
            <button className="button primary space-top" onClick={save}>
              保存机构设置
            </button>
          )}
        </section>
        <section className="panel settings-card">
          <h2>使用期与模型额度</h2>
          <p>
            软件使用期与模型额度分别计算。未配置的赠送额度为0；费用来源由机构主动选择。
          </p>
          <div className="kv">
            <span>软件使用状态</span>
            <Badge
              value={info.value?.entitlement.active ? "active" : "suspended"}
              label={info.value?.entitlement.active ? "使用中" : "已到期或暂停"}
            />
          </div>
          <div className="kv">
            <span>有效至</span>
            <span>{date(info.value?.entitlement.until, true)}</span>
          </div>
          {Object.entries(resourceLabels).map(([k, label]) => {
            const b = usage.value?.buckets?.find((b: any) => b.resource === k),
              quota = info.value?.settings.quotas?.[k] || 0,
              total = (b?.used || 0) + (b?.reserved || 0);
            return (
              <div className="quota-row" key={k}>
                <div>
                  <span>{label}</span>
                  <span>
                    {b?.used || 0} 已用 + {b?.reserved || 0} 预占 / {quota}
                  </span>
                </div>
                <div className="progress">
                  <div
                    style={{
                      width:
                        Math.min(100, quota ? (total / quota) * 100 : 0) + "%",
                    }}
                  />
                </div>
              </div>
            );
          })}
          <Notice>
            在线购买套餐将在后续开放。使用期结束后仍可查看与导出已有记录。
          </Notice>
          <a href="/api/v1/exports/order?format=xlsx" className="button small">
            导出订单记录
          </a>
        </section>
        {editable && (
          <section className="panel settings-card">
            <h2>服务连接</h2>
            <p>密钥仅用于当前机构。平台额度耗尽时，不会自动使用机构 Key。</p>
            {[
              ["aliyun", "阿里云百炼"],
              ["deepseek", "DeepSeek 官方 API"],
              ["wecom", "企业微信官方客服"],
            ].map(([k, label]) => {
              const exists = integrations.value?.find(
                (x) => x.provider === k && x.configured && x.active,
              );
              return (
                <div className="kv" key={k}>
                  <span>
                    {label} · {exists ? "已配置" : "待配置"}
                  </span>
                  <div className="button-row">
                    <button
                      className="button link"
                      onClick={() => setConnection(k)}
                    >
                      {exists ? "替换凭证" : "连接"}
                    </button>
                    {editable && (
                      <AsyncButton
                        className="button link"
                        action={async () => {
                          await api("/integrations/" + k, { method: "DELETE" });
                          integrations.refresh();
                        }}
                      >
                        撤销
                      </AsyncButton>
                    )}
                  </div>
                </div>
              );
            })}
            <p style={{ marginTop: 16, fontSize: 10 }}>
              企微回调地址：{location.origin}/api/v1/webhooks/wecom/
              {info.value?.id}
            </p>
          </section>
        )}
        <section className="panel settings-card">
          <h2>机构预约入口</h2>
          <p>每个机构有独立的预约与网页客服入口，来源参数会进入线索记录。</p>
          <Field label="预约链接">
            <input
              readOnly
              value={
                location.origin +
                "/book/" +
                (info.value?.slug || "") +
                "?source=机构分享"
              }
            />
          </Field>
          <div className="button-row">
            <a
              className="button"
              target="_blank"
              rel="noreferrer"
              href={"/book/" + info.value?.slug}
            >
              <Link2 size={13} />
              打开家长入口
            </a>
            <button
              className="button"
              onClick={async () => {
                await navigator.clipboard.writeText(
                  location.origin +
                    "/book/" +
                    info.value?.slug +
                    "?source=机构分享",
                );
                setNotice("预约链接已复制");
              }}
            >
              复制链接
            </button>
            <a
              className="button"
              href={"/api/v1/tenant/booking-qr"}
              target="_blank"
              rel="noreferrer"
            >
              <QrCode size={13} />
              预约二维码
            </a>
          </div>
        </section>
        {editable && <AISettingsPanel key={integrations.value?.map(x => `${x.provider}:${x.active}:${x.configured}`).join("|")} />}
        <StaffPanel />
        {editable && <Accounts />}
      </div>
      {can("usage.read") && <UsageDetails />}
      {connection && (
        <IntegrationForm
          provider={connection}
          close={() => setConnection("")}
          saved={integrations.refresh}
        />
      )}{" "}
    </>
  );
}
export function PlatformPage() {
  const data = useResource<any>(() => api("/platform"), []),
    [editing, setEditing] = useState<any>(null),
    [cfg, setCfg] = useState<any>(null),
    [notice, setNotice] = useState("");
  const values = cfg || data.value?.settings || {};
  return (
    <>
      <PageTitle title="平台管理" text="管理开放期、机构权益与模型计价参数。" />
      {notice && <Notice>{notice}</Notice>}
      {data.error && <Notice tone="error">{data.error}</Notice>}
      <section className="panel settings-card">
        <h2>全局开放配置</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await patch("/platform", {
                free_until: values.free_until
                  ? new Date(values.free_until).toISOString()
                  : null,
                registration_open: values.registration_open ?? true,
                prices: values.plans?.prices || {},
                catalog: values.plans?.catalog || [],
              });
              setNotice("平台配置已保存");
              data.refresh();
            } catch (e) {
              setNotice((e as Error).message);
            }
          }}
        >
          <Field label="全局免费截止时间">
            <input
              type="datetime-local"
              value={localInput(values.free_until)}
              onChange={(e) =>
                setCfg({
                  ...values,
                  free_until: e.target.value
                    ? new Date(e.target.value).toISOString()
                    : null,
                })
              }
            />
          </Field>
          <label className="check">
            <input
              type="checkbox"
              checked={values.registration_open ?? true}
              onChange={(e) =>
                setCfg({ ...values, registration_open: e.target.checked })
              }
            />
            开放机构注册
          </label>
          <div className="form-grid space-top">
            {[
              ["text_million_fen", "百炼每百万文字Token估算（分）"],
              [
                "deepseek_flash_input_million_fen",
                "DeepSeek Flash百万输入（分）",
              ],
              [
                "deepseek_flash_output_million_fen",
                "DeepSeek Flash百万输出（分）",
              ],
              [
                "deepseek_flash_cached_million_fen",
                "DeepSeek Flash百万缓存输入（分）",
              ],
              ["deepseek_pro_input_million_fen", "DeepSeek Pro百万输入（分）"],
              ["deepseek_pro_output_million_fen", "DeepSeek Pro百万输出（分）"],
              [
                "deepseek_pro_cached_million_fen",
                "DeepSeek Pro百万缓存输入（分）",
              ],
              ["image_fen", "每张图片（分）"],
              ["video_second_fen", "每秒视频（分）"],
              ["speech_thousand_fen", "每千配音字符（分）"],
            ].map(([k, label]) => (
              <Field label={label} key={k}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={values.plans?.prices?.[k] || 0}
                  onChange={(e) =>
                    setCfg({
                      ...values,
                      plans: {
                        ...values.plans,
                        prices: {
                          ...values.plans?.prices,
                          [k]: Number(e.target.value),
                        },
                      },
                    })
                  }
                />
              </Field>
            ))}
          </div>
          <div className="divider" />
          <h2>套餐目录</h2>
          <Notice>
            当前维护权益与参考价格，在线购买尚未开放。分配套餐后，仍需确认机构有效期及额度。
          </Notice>
          {(values.plans?.catalog || []).map((p: any, i: number) => (
            <div className="form-grid" key={p.id}>
              {[
                ["name", "套餐名称"],
                ["term_days", "有效天数"],
                ["price_fen", "参考价格（元）"],
              ].map(([k, label]) => (
                <Field label={label} key={k}>
                  <input
                    type={k === "name" ? "text" : "number"}
                    min={k === "term_days" ? 1 : 0}
                    step={k === "price_fen" ? "0.01" : "1"}
                    value={k === "price_fen" ? p[k] / 100 : p[k]}
                    onChange={(e) => {
                      const catalog = [...values.plans.catalog];
                      catalog[i] = {
                        ...p,
                        [k]:
                          k === "name"
                            ? e.target.value
                            : Math.round(
                                Number(e.target.value) *
                                  (k === "price_fen" ? 100 : 1),
                              ),
                      };
                      setCfg({
                        ...values,
                        plans: { ...values.plans, catalog },
                      });
                    }}
                  />
                </Field>
              ))}
            </div>
          ))}
          <button
            type="button"
            className="button small"
            onClick={() =>
              setCfg({
                ...values,
                plans: {
                  ...values.plans,
                  catalog: [
                    ...(values.plans?.catalog || []),
                    {
                      id: "plan-" + Date.now(),
                      name: "机构基础版",
                      term_days: 30,
                      price_fen: 0,
                      quotas: {},
                      enabled: false,
                    },
                  ],
                },
              })
            }
          >
            添加套餐
          </button>
          <div className="space-top">
            <button className="button primary">保存平台配置</button>
          </div>
        </form>
      </section>
      <section className="panel space-top">
        <div className="toolbar">
          <strong>机构权益</strong>
          <Badge value="draft" label="在线支付尚未开放" />
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>机构</th>
                <th>状态</th>
                <th>单机构延期至</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.value?.tenants.map((t: any) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>
                    <Badge value={t.status} />
                  </td>
                  <td>{date(t.free_until, true)}</td>
                  <td>
                    <button
                      className="button link"
                      onClick={() => setEditing(t)}
                    >
                      配置权益
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {editing && (
        <Modal
          title={editing.name + " · 机构权益"}
          close={() => setEditing(null)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await patch("/platform/tenants/" + editing.id, {
                  status: editing.status,
                  free_until: editing.free_until
                    ? new Date(editing.free_until).toISOString()
                    : null,
                  quotas: editing.quotas,
                  plan_id: editing.plan_id || "",
                  account_limit: editing.account_limit ?? 9,
                });
                setEditing(null);
                data.refresh();
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          >
            <div className="form-body">
              <Field label="矩阵账号数量上限">
                <input
                  type="number"
                  min={0}
                  max={500}
                  value={editing.account_limit ?? 9}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      account_limit: Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="分配套餐">
                <select
                  value={editing.plan_id || ""}
                  onChange={(e) =>
                    setEditing({ ...editing, plan_id: e.target.value })
                  }
                >
                  <option value="">仅免费开放期</option>
                  {data.value?.settings?.plans?.catalog?.map((p: any) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.term_days}天
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="机构状态">
                <select
                  value={editing.status}
                  onChange={(e) =>
                    setEditing({ ...editing, status: e.target.value })
                  }
                >
                  <option value="active">正常</option>
                  <option value="suspended">暂停</option>
                </select>
              </Field>
              <Field label="机构延期至">
                <input
                  type="datetime-local"
                  value={localInput(editing.free_until)}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      free_until: e.target.value
                        ? new Date(e.target.value).toISOString()
                        : null,
                    })
                  }
                />
              </Field>
              {[
                ["text_tokens", "每月文字Token"],
                ["images", "每月图片张数"],
                ["video_seconds", "每月视频秒数"],
                ["speech_characters", "每月配音字符数"],
                ["cost_fen", "每月费用上限（分）"],
              ].map(([k, label]) => (
                <Field label={label} key={k}>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={editing.quotas[k] || 0}
                    onChange={(e) =>
                      setEditing({
                        ...editing,
                        quotas: {
                          ...editing.quotas,
                          [k]: Number(e.target.value),
                        },
                      })
                    }
                  />
                </Field>
              ))}
            </div>
            <div className="form-footer">
              <button className="button primary">保存机构权益</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function UsageDetails() {
  const data = useResource<any>(() => api("/usage"), [], 10000);
  const labels: Record<string, string> = {
    text_tokens: "文字Token",
    images: "图片",
    video_seconds: "视频秒数",
    speech_characters: "配音字符",
  };
  return (
    <section className="panel space-top">
      <div className="toolbar">
        <strong>模型调用与费用明细</strong>
        <span className="text-muted" style={{ fontSize: 10 }}>
          按任务锁定的单价估算，最终以供应商账单为准
        </span>
      </div>
      {data.error ? (
        <Notice tone="error">{data.error}</Notice>
      ) : !data.value?.items?.length ? (
        <Empty
          title="尚无模型调用"
          text="平台额度和机构自带Key的用量会分别记录在这里。"
        />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>类型</th>
                <th>费用来源</th>
                <th>模型</th>
                <th>预占 / 已用</th>
                <th>估算费用</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {data.value.items
                .filter((x: any) => x.resource !== "cost_fen")
                .slice(0, 40)
                .map((x: any) => (
                  <tr key={x.id}>
                    <td>{date(x.created_at, true)}</td>
                    <td>{labels[x.resource] || x.resource}</td>
                    <td>{x.funding === "byok" ? "机构Key" : "平台额度"}</td>
                    <td>
                      {x.model_usage?.route?.model || "历史／媒体任务"}
                      <small>
                        {x.model_usage?.route?.provider || "aliyun"}
                      </small>
                    </td>
                    <td>
                      {x.reserved} / {x.actual}
                      {x.estimated ? "（用量估计）" : ""}
                    </td>
                    <td>
                      {x.state !== "settled"
                        ? "待结算"
                        : !x.unit_rate_fen
                          ? "未配置单价"
                          : money(x.cost_fen)}
                    </td>
                    <td>
                      <Badge
                        value={x.state === "settled" ? "succeeded" : "pending"}
                        label={x.state === "settled" ? "已结算" : "预占中"}
                      />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
