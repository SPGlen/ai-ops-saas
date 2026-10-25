import { DemoLoginChoices } from "./DemoPage";
import { SocialInboxTools } from "./SocialWorkspace";
import React, { useState } from "react";
import { api, post, patch, uid, money, date, can, roles } from "./api";
import { Badge, Empty, Field, Notice, PageTitle, useResource } from "./ui";
export function AuthPage({ ready }: { ready: () => void }) {
  const demoInfo = useResource<any>(() => api("/demo/info").catch(() => ({enabled:false})), []);
  const demos = useResource<any[]>(
    () => api("/auth/demo-accounts").catch(() => []),
    [],
  );
  const query = new URLSearchParams(location.search),
    [mode, setMode] = useState(
      location.pathname.includes("verify")
        ? "verify"
        : location.pathname.includes("reset")
          ? "reset"
          : "login",
    ),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [name, setName] = useState(""),
    [org, setOrg] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body =
        mode === "login"
          ? { email, password }
          : mode === "register"
            ? { email, password, name, tenant_name: org }
            : mode === "verify"
              ? { token: query.get("token") || "" }
              : mode === "reset"
                ? { token: query.get("token") || "", password }
                : { email };
      const result = await post(
        "/auth/" +
          ({
            login: "login",
            register: "register",
            verify: "verify",
            reset: "reset",
            forgot: "forgot",
            resend: "resend-verification",
          }[mode] || "login"),
        body,
      );
      if (mode === "login") {
        history.replaceState({}, "", "/");
        ready();
      } else setMessage(result.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const titles: Record<string, string> = {
    login: "登录你的工作台",
    register: "创建机构工作台",
    forgot: "找回密码",
    verify: "验证邮箱",
    reset: "设置新密码",
    resend: "重发邮箱验证",
  };
  return (
    <div className="auth-shell">
      <aside className="auth-story">
        <div className="brand">
          <span className="brand-mark">知</span>
          <div>
            知营<small>ZHIYING · EDUCATION OPS</small>
          </div>
        </div>
        <div>
          <h1>
            让好课程被看见，
            <br />
            <em>让日常运营更从容。</em>
          </h1>
          <p>
            从一篇内容，到一次试听，再到每一堂课。
            <br />
            把招生、教务与财务，连成清楚的一条线。
          </p>
          <div className="auth-steps">
            <div>
              <b>01</b>内容获客
            </div>
            <div>
              <b>02</b>招生转化
            </div>
            <div>
              <b>03</b>教学交付
            </div>
          </div>
        </div>
        <p>为教育机构而设计 · 团队协作工作台</p>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <span className="eyebrow">YOUR DAILY WORKSPACE</span>
          <h2 style={{ marginTop: 12 }}>{titles[mode]}</h2>
          <p>
            {mode === "login"
              ? "欢迎回来。把精力留给课程与学员。"
              : "验证邮件会发送到机构负责人邮箱。"}
          </p>
          {error && <Notice tone="error">{error}</Notice>}
          {mode === "login" && demoInfo.value?.enabled && <DemoLoginChoices accounts={demos.value || []} ready={ready} />}
          {mode === "login" && !demoInfo.value?.enabled && !!demos.value?.length && (
            <details>
              <summary>开发演示：选择机构与岗位账号</summary>
              <p>仅用于虚构资料预览；员工账号没有平台管理员权限。</p>
              <div className="demo-accounts">
                {demos.value.map((a: any) => (
                  <button
                    type="button"
                    className="button small"
                    key={a.email + a.tenant_name}
                    onClick={() => {
                      setEmail(a.email);
                      setPassword(a.password);
                    }}
                  >
                    {a.platform_admin ? "平台管理员（全功能）" : a.name} ·{" "}
                    {a.tenant_name.split(" · ")[0]}
                  </button>
                ))}
              </div>
            </details>
          )}
          {message && <Notice tone="success">{message}</Notice>}
          {(!demoInfo.value?.enabled || mode !== "login") && <form onSubmit={submit}>
            {mode === "register" && (
              <>
                <Field label="你的姓名">
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                  />
                </Field>
                <Field label="机构名称">
                  <input
                    required
                    minLength={2}
                    value={org}
                    onChange={(e) => setOrg(e.target.value)}
                  />
                </Field>
              </>
            )}
            {!["verify", "reset"].includes(mode) && (
              <Field label="邮箱">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="name@company.com"
                />
              </Field>
            )}
            {["login", "register", "reset"].includes(mode) && (
              <Field label="密码" hint={mode !== "login" ? "至少12个字符" : ""}>
                <input
                  type="password"
                  required
                  minLength={mode === "login" ? 1 : 12}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                />
              </Field>
            )}
            <button className="button primary" disabled={busy}>
              {busy
                ? "请稍候…"
                : mode === "login"
                  ? "进入工作台"
                  : mode === "register"
                    ? "注册并发送验证邮件"
                    : mode === "verify"
                      ? "确认验证邮箱"
                      : mode === "reset"
                        ? "保存新密码"
                        : "发送重置链接"}
            </button>
          </form>}
          {!demoInfo.value?.enabled && <div className="auth-links">
            <button
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setMessage("");
                setError("");
              }}
            >
              {mode === "login" ? "注册新机构" : "返回登录"}
            </button>
            {mode === "login" && (
              <>
                <button onClick={() => setMode("resend")}>重发验证</button>
                <button onClick={() => setMode("forgot")}>忘记密码</button>
              </>
            )}
          </div>}
        </div>
      </main>
    </div>
  );
}
export function PublicPage({ slug }: { slug: string }) {
  const info = useResource<any>(() => api("/public/" + slug), [slug]),
    [name, setName] = useState(""),
    [grade, setGrade] = useState("一年级"),
    [phone, setPhone] = useState(""),
    [need, setNeed] = useState(""),
    [time, setTime] = useState(""),
    [consent, setConsent] = useState(false),
    [done, setDone] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [chat, setChat] = useState(false);
  return (
    <main className="public-shell">
      <div className="public-brand">
        <span className="brand-mark">知</span>
        {info.value?.name || "课程预约"}
      </div>
      {info.error ? (
        <Notice tone="error">{info.error}</Notice>
      ) : (
        <>
          <section className="public-hero">
            <span className="eyebrow">EXPLORE · CREATE · LEARN</span>
            <h1>
              从一次好奇，
              <br />
              开始探索 AI 的可能。
            </h1>
            <p>
              {info.value?.brand || "了解课程内容，预约一次适合孩子的体验。"}
            </p>
            {info.value?.consultation_enabled && (
              <button className="button" onClick={() => setChat(!chat)}>
                咨询课程
              </button>
            )}
          </section>
          {info.value?.consultation_enabled && chat && (
            <PublicChat slug={slug} />
          )}
          <div className="card-grid space-top">
            {info.value?.courses.map((c: any) => (
              <div className="panel settings-card" key={c.id}>
                <Badge value="approved" label="课程介绍" />
                <h2 style={{ marginTop: 15 }}>{c.name}</h2>
                <p>{c.description}</p>
                <div className="kv">
                  <span>课程与服务说明</span>
                  <strong>
                    {typeof c.price_fen === "number"
                      ? money(c.price_fen)
                      : "费用请联系机构确认"}
                  </strong>
                </div>
              </div>
            ))}
          </div>
          <form
            className="panel public-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const result = await post("/public/" + slug + "/leads", {
                  name,
                  grade,
                  contact: phone,
                  need,
                  contact_time: time,
                  source:
                    new URLSearchParams(location.search).get("source") ||
                    "官网预约",
                  consent,
                  website: "",
                });
                setDone(result.message);
                setError("");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h2 style={{ fontSize: 18, marginBottom: 22 }}>预约一次试听</h2>
            {done ? (
              <Notice tone="success">{done}</Notice>
            ) : (
              <>
                {error && <Notice tone="error">{error}</Notice>}
                <div className="form-grid">
                  <Field label="家长称呼">
                    <input
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </Field>
                  <Field label="孩子年级">
                    <select
                      value={grade}
                      onChange={(e) => setGrade(e.target.value)}
                    >
                      {[
                        "一年级",
                        "二年级",
                        "三年级",
                        "四年级",
                        "五年级",
                        "六年级",
                        "其他",
                      ].map((g) => (
                        <option key={g}>{g}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="联系电话">
                    <input
                      required
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                    />
                  </Field>
                  <Field label="方便联系的时间">
                    <input
                      value={time}
                      onChange={(e) => setTime(e.target.value)}
                      placeholder="例如：工作日18点后"
                    />
                  </Field>
                </div>
                <Field label="想了解什么">
                  <textarea
                    value={need}
                    onChange={(e) => setNeed(e.target.value)}
                  />
                </Field>
                <label className="check">
                  <input
                    required
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  我同意机构为安排试听与课程咨询使用以上信息。
                </label>
                <button
                  className="button primary space-top"
                  disabled={busy || !info.value?.available}
                >
                  {busy
                    ? "提交中…"
                    : info.value?.available
                      ? "提交预约"
                      : "预约暂未开放"}
                </button>
              </>
            )}
          </form>
        </>
      )}
      <p className="public-footer">
        信息仅用于本机构安排课程咨询与试听。
        <br />
        请勿在咨询中发送儿童身份证件等敏感资料。 · 知营提供技术支持
      </p>
    </main>
  );
}
function PublicChat({ slug }: { slug: string }) {
  const [key, setKey] = useState<{ id: string; token: string } | null>(() => {
      try {
        return JSON.parse(sessionStorage.getItem("chat:" + slug) || "null");
      } catch {
        return null;
      }
    }),
    [body, setBody] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const data = useResource<any>(
    () =>
      key
        ? api("/public/" + slug + "/chat/" + key.id, {
            headers: { "X-Public-Token": key.token },
          })
        : Promise.resolve(null),
    [key?.id],
    4000,
  );
  async function start() {
    try {
      const result = await post("/public/" + slug + "/chat");
      setKey(result);
      sessionStorage.setItem("chat:" + slug, JSON.stringify(result));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel space-top">
      {error && <Notice tone="error">{error}</Notice>}
      {!key ? (
        <div className="settings-card">
          <p style={{ fontSize: 12, marginBottom: 16 }}>
            客服根据机构已确认资料回答，无法确认的问题会交给老师。
          </p>
          <button className="button primary" onClick={start}>
            开始咨询
          </button>
        </div>
      ) : (
        <>
          {data.error && <Notice tone="error">{data.error}</Notice>}
          <div className="message-list">
            {data.value?.messages.map((m: any) => (
              <div
                key={m.id}
                className={"message " + (m.role === "user" ? "user" : "")}
              >
                <small>
                  {m.delivery_state === "handled_externally"
                    ? "外部处理登记"
                    : m.role === "user"
                      ? "我"
                      : m.role === "staff"
                        ? "机构同事"
                        : "课程助理"}
                </small>
                {m.body}
                {m.sources.length > 0 && (
                  <div className="source-tags">
                    资料：{m.sources.map((s: any) => s.title).join("、")}
                  </div>
                )}
              </div>
            ))}
          </div>
          <form
            className="chat-compose"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await api("/public/" + slug + "/chat/" + key.id, {
                  method: "POST",
                  headers: { "X-Public-Token": key.token },
                  body: JSON.stringify({ body }),
                });
                setBody("");
                data.refresh();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <textarea
              required
              aria-label="咨询内容"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="问问课程安排，或输入“人工”…"
            />
            <button className="button primary" disabled={busy}>
              发送
            </button>
          </form>
        </>
      )}
    </section>
  );
}
export function InboxPage() {
  const team = useResource<any[]>(
    () => (can("lead.assign") ? api("/members") : Promise.resolve([])),
    [],
  );
  const list = useResource<any[]>(() => api("/conversations"), [], 5000),
    [id, setId] = useState(""),
    [body, setBody] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const data = useResource<any>(
    () => (id ? api("/conversations/" + id) : Promise.resolve(null)),
    [id],
    3000,
  );
  async function action(name: string) {
    try {
      await post("/conversations/" + id + "/" + name);
      data.refresh();
      list.refresh();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="CONVERSATIONS"
        title="每一次咨询，都有回应"
        text="查看课程咨询、资料引用和人工跟进记录。"
      />
      {error && <Notice tone="error">{error}</Notice>}
      {list.error && <Notice tone="error">{list.error}</Notice>}
      <section className="panel chat-layout">
        <aside className="chat-list">
          {list.value?.length ? (
            list.value.map((c) => (
              <button
                key={c.id}
                className={id === c.id ? "selected" : ""}
                onClick={() => setId(c.id)}
              >
                <b>{c.title}</b>
                <small>
                  {(
                    {
                      web: "网页咨询",
                      wecom: "企业微信",
                      xiaohongshu: "小红书",
                      douyin: "抖音",
                      channels: "微信视频号",
                    } as Record<string, string>
                  )[c.channel] || c.channel}{" "}
                  · {date(c.created_at)}
                </small>
                <div style={{ marginTop: 7 }}>
                  <Badge value={c.state} />
                </div>
              </button>
            ))
          ) : (
            <Empty title="暂无咨询" text="分享机构预约链接，让家长开始咨询。" />
          )}
        </aside>
        <div className="chat-pane">
          {!id ? (
            <Empty
              title="选择一条会话"
              text="接管后，智能助理会停止自动回复。"
            />
          ) : (
            <>
              <header>
                <Badge value={data.value?.state || "bot"} />
                {can("lead.assign") && !data.value?.lead_id && (
                  <select
                    aria-label="会话负责人"
                    value={data.value?.owner_id || ""}
                    onChange={async (e) => {
                      try {
                        await patch("/conversations/" + id, {
                          owner_id: e.target.value,
                        });
                        data.refresh();
                        list.refresh();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    <option value="">未分配</option>
                    {team.value
                      ?.filter(
                        (m) =>
                          m.status === "active" &&
                          m.roles.some((r: string) =>
                            ["owner", "admissions"].includes(r),
                          ),
                      )
                      .map((m) => (
                        <option key={m.id} value={m.user_id}>
                          {m.name}
                        </option>
                      ))}
                  </select>
                )}
                <div className="button-row">
                  <button
                    className="button small"
                    onClick={() => action("takeover")}
                  >
                    人工接管
                  </button>
                  <button
                    className="button small"
                    onClick={() => action("resume")}
                  >
                    恢复智能接待
                  </button>
                </div>
              </header>
              {data.error && <Notice tone="error">{data.error}</Notice>}
              <div className="message-list">
                {data.value?.messages.map((m: any) => (
                  <div key={m.id} className={"message " + m.role}>
                    <small>
                      {m.delivery_state === "handled_externally"
                        ? "外部处理登记"
                        : m.role === "user"
                          ? "家长"
                          : m.role === "staff"
                            ? "人工客服"
                            : "智能助理"}{" "}
                      · {date(m.created_at, true)}
                      {m.delivery_state === "unknown"
                        ? " · 发送结果待核实"
                        : ""}
                    </small>
                    {m.body}
                    {m.sources.length > 0 && (
                      <div className="source-tags">
                        依据：{m.sources.map((s: any) => s.title).join("、")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <SocialInboxTools
                conversation={data.value}
                refresh={data.refresh}
              />
              {!data.value?.account_id && (
                <form
                  className="chat-compose"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    setBusy(true);
                    try {
                      await post("/conversations/" + id + "/reply", { body });
                      setBody("");
                      data.refresh();
                      setError("");
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <textarea
                    required
                    aria-label="人工回复"
                    disabled={
                      !["human", "waiting_human"].includes(data.value?.state)
                    }
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder={
                      data.value?.state === "bot"
                        ? "先接管，再回复"
                        : "输入回复内容…"
                    }
                  />
                  <button
                    className="button primary"
                    disabled={
                      busy ||
                      !["human", "waiting_human"].includes(data.value?.state)
                    }
                  >
                    发送回复
                  </button>
                </form>
              )}
            </>
          )}
        </div>
      </section>
    </>
  );
}
