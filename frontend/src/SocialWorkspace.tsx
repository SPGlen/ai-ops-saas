import React, { useState, useEffect } from "react";
import { api, post, patch, can, platforms, date, uid } from "./api";
import { Field, Notice, Badge, useResource, Empty } from "./ui";
export function SocialWorkspace() {
  const accounts = useResource<any[]>(() => api("/social-accounts"), []),
    [selected, setSelected] = useState(""),
    [message, setMessage] = useState(""),
    [auto, setAuto] = useState(false),
    [assignee, setAssignee] = useState(""),
    [incoming, setIncoming] = useState(""),
    [sender, setSender] = useState(""),
    [kind, setKind] = useState("private_message");
  const info = useResource<any>(
    () =>
      selected
        ? api("/social-accounts/" + selected + "/capabilities")
        : Promise.resolve(null),
    [selected],
  );
  const members = useResource<any[]>(
    () => (can("members.manage") ? api("/members") : Promise.resolve([])),
    [],
  );
  useEffect(() => {
    if (info.value) {
      setAuto(info.value.policy.auto_reply);
      setAssignee(info.value.policy.assignee_id || "");
    }
  }, [selected, info.value]);
  async function action(op: string) {
    try {
      const out = await post("/social-accounts/" + selected + "/" + op);
      setMessage(out.message || "连接器请求已完成");
      info.refresh();
      accounts.refresh();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <section className="panel settings-card social-workspace">
      <h2>平台能力与自动回复</h2>
      <p>
        每项能力单独显示接通状态。未接通时请在官方后台处理，不会显示虚假发送成功。
      </p>
      {message && <Notice>{message}</Notice>}
      <Field label="选择平台账号">
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setMessage("");
          }}
        >
          <option value="">请选择账号</option>
          {accounts.value?.map((a) => (
            <option key={a.id} value={a.id}>
              {platforms[a.platform]} · {a.name}
            </option>
          ))}
        </select>
      </Field>
      {!accounts.value?.length && (
        <Empty
          title="尚未添加平台账号"
          text="负责人在机构与连接中添加账号并扫码授权。"
        />
      )}
      {info.error && <Notice tone="error">{info.error}</Notice>}
      {info.value && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>能力</th>
                  <th>状态</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.value.capabilities).map(
                  ([key, cap]: any) => (
                    <tr key={key}>
                      <td>{cap.label}</td>
                      <td>
                        <Badge
                          value={cap.state}
                          label={
                            {
                              available: "可用",
                              requires_authorization: "待授权",
                              unverified: "待验证",
                              unsupported: "不支持",
                            }[
                              cap.state as
                                | "available"
                                | "requires_authorization"
                                | "unverified"
                                | "unsupported"
                            ]
                          }
                        />
                      </td>
                      <td>{cap.reason}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <div className="button-row">
            <a
              className="button"
              href={info.value.official_url}
              target="_blank"
              rel="noreferrer"
            >
              打开官方运营后台
            </a>
            {can("social.manage") && (
              <button className="button" onClick={() => action("probe")}>
                检查连接与读取能力
              </button>
            )}
            {can("social.reply") && (
              <button className="button" onClick={() => action("poll")}>
                采集收到的评论
              </button>
            )}
          </div>
          {can("social.manage") && info.value.platform === "douyin" && (
            <OfficialDouyin accountId={selected} saved={info.refresh} />
          )}
          {can("social.manage") && (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await patch("/social-accounts/" + selected + "/policy", {
                    auto_reply: auto,
                    assignee_id: assignee,
                  });
                  info.refresh();
                  setMessage("自动回复策略已保存");
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              <h3>自动回复授权</h3>
              <p>
                当前策略：
                {info.value.policy.auto_reply ? "自动回复已授权" : "尚未授权"}
                ；环境实际发送：
                {info.value.live_replies ? "已启用" : "关闭（开发预览）"}
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={auto}
                  onChange={(e) => setAuto(e.target.checked)}
                />
                为已验证能力启用评论和私信自动回复
              </label>
              <Field label="咨询线索默认分配给">
                <select
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                >
                  <option value="">未分配，由负责人处理</option>
                  {members.value
                    ?.filter(
                      (m) =>
                        m.status === "active" &&
                        m.roles.some((r: string) =>
                          ["owner", "admissions"].includes(r),
                        ),
                    )
                    .map((m) => (
                      <option value={m.user_id} key={m.id}>
                        {m.name}
                      </option>
                    ))}
                </select>
              </Field>
              <button className="button primary">保存策略</button>
            </form>
          )}
          {can("social.reply") && (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await post(
                    "/social-accounts/" + selected + "/manual-interactions",
                    { sender_name: sender, body: incoming, kind },
                  );
                  setIncoming("");
                  setMessage(
                    "已标记为人工录入，可在咨询接待中生成草稿和登记处理结果",
                  );
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              <h3>人工录入收到的互动</h3>
              <Field label="对方称呼">
                <input
                  required
                  value={sender}
                  onChange={(e) => setSender(e.target.value)}
                />
              </Field>
              <Field label="类型">
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="private_message">私信</option>
                  <option value="comment">评论</option>
                </select>
              </Field>
              <Field label="实际收到的内容">
                <textarea
                  required
                  value={incoming}
                  onChange={(e) => setIncoming(e.target.value)}
                />
              </Field>
              <button className="button">保存人工记录</button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
export function SocialInboxTools({
  conversation,
  refresh,
}: {
  conversation: any;
  refresh: () => void;
}) {
  const [text, setText] = useState(""),
    [notice, setNotice] = useState("");
  const replies = useResource<any[]>(
    () => api("/social-replies"),
    [conversation?.id],
    5000,
  );
  if (!conversation?.account_id) return null;
  const own = (replies.value || []).filter(
    (r) => r.conversation_id === conversation.id,
  );
  return (
    <section className="panel social-inbox-tools">
      <h3>自媒体互动处理</h3>
      <p>
        {platforms[conversation.channel]} ·{" "}
        {conversation.interaction_kind === "comment" ? "作品评论" : "私信"}
      </p>
      <a
        href={
          {
            xiaohongshu: "https://creator.xiaohongshu.com/",
            douyin: "https://creator.douyin.com/",
            channels: "https://channels.weixin.qq.com/",
          }[conversation.channel as "xiaohongshu" | "douyin" | "channels"]
        }
        target="_blank"
        rel="noreferrer"
      >
        打开官方后台处理 ↗
      </a>
      <p className="capability-note">
        {conversation.reply_capability?.reason || "渠道能力待验证"}
        {!conversation.live_replies ? " · 当前环境实际发送关闭" : ""}
      </p>
      <button
        className="button small"
        onClick={async () => {
          try {
            await post(
              "/conversations/" + conversation.id + "/handled-externally",
              { note: "员工已在官方后台完成本次处理" },
            );
            setNotice("已登记外部处理记录，未通过本系统发送消息");
            refresh();
          } catch (e) {
            setNotice((e as Error).message);
          }
        }}
      >
        登记已在官方后台处理
      </button>
      {notice && <Notice>{notice}</Notice>}
      <div className="button-row">
        <button
          className="button small"
          onClick={async () => {
            try {
              await post("/conversations/" + conversation.id + "/convert-lead");
              setNotice("已建立招生线索，按账号负责人规则分配");
            } catch (e) {
              setNotice((e as Error).message);
            }
          }}
        >
          转为招生线索
        </button>
        <button
          className="button small"
          onClick={async () => {
            try {
              await post("/conversations/" + conversation.id + "/reply-draft", {
                request_id: uid(),
              });
              setNotice("草稿任务已建立");
              replies.refresh();
            } catch (e) {
              setNotice((e as Error).message);
            }
          }}
        >
          AI生成回复草稿
        </button>
      </div>
      {own.map((r) => (
        <div key={r.id}>
          <p>
            <Badge value={r.status} /> · {date(r.created_at, true)}
          </p>
          <p>{r.body || r.error || "等待生成"}</p>
          {r.error && <small>{r.error}</small>}
          {r.status === "draft" && (
            <button
              className="button small"
              onClick={async () => {
                await post("/social-replies/" + r.id + "/mark-handled", {
                  note: "员工已在官方后台处理",
                });
                replies.refresh();
                refresh();
              }}
            >
              登记已在官方后台处理
            </button>
          )}
        </div>
      ))}
      {conversation.live_replies &&
        (conversation.reply_capability?.state === "available" ||
          (conversation.reply_capability?.state === "unverified" &&
            can("social.manage"))) &&
        ["human", "waiting_human"].includes(conversation.state) && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await post(
                  "/conversations/" + conversation.id + "/social-reply",
                  { body: text, request_id: uid() },
                );
                setText("");
                replies.refresh();
                setNotice("已建立回复任务，请查看实际发送状态");
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          >
            <Field label="发送到已接通的自媒体渠道">
              <textarea
                required
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
            <button className="button primary">提交渠道回复</button>
          </form>
        )}
    </section>
  );
}

function OfficialDouyin({
  accountId,
  saved,
}: {
  accountId: string;
  saved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({}),
    [message, setMessage] = useState("");
  return (
    <details>
      <summary>配置已获授权的抖音官方接口</summary>
      <p>
        填写该账号已取得的官方凭证。身份核对不代表评论和私信权限已开通，需分别验证。
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/social-accounts/" + accountId + "/douyin-credentials", {
              method: "PUT",
              body: JSON.stringify(values),
            });
            setValues({});
            setMessage("凭证已加密保存，页面不回显");
            saved();
          } catch (e) {
            setMessage((e as Error).message);
          }
        }}
      >
        {[
          ["client_key", "应用Client Key"],
          ["client_secret", "应用Client Secret"],
          ["open_id", "授权账号Open ID"],
          ["access_token", "账号Access Token"],
        ].map(([key, label]) => (
          <Field key={key} label={label}>
            <input
              type={
                key.includes("secret") || key.includes("token")
                  ? "password"
                  : "text"
              }
              required
              autoComplete="off"
              value={values[key] || ""}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            />
          </Field>
        ))}
        <button className="button">核对身份并保存凭证</button>
        {message && <Notice>{message}</Notice>}
      </form>
    </details>
  );
}
