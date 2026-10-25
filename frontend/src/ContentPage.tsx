import { can } from "./api";
import React, { useState } from "react";
import {
  Plus,
  Sparkles,
  FileText,
  Video,
  CalendarDays,
  Upload,
  ArrowUpRight,
  Download,
  RefreshCw,
} from "lucide-react";
import {
  api,
  post,
  patch,
  ContentItem,
  Job,
  date,
  uid,
  localInput,
  platforms,
} from "./api";
import {
  PageTitle,
  Modal,
  Field,
  Notice,
  Empty,
  Badge,
  Loading,
  useResource,
} from "./ui";
import { RecordPage } from "./BusinessPage";

function ContentForm({
  item,
  close,
  saved,
}: {
  item?: ContentItem;
  close: () => void;
  saved: () => void;
}) {
  const latest = item?.versions[0],
    [title, setTitle] = useState(latest?.title || ""),
    [body, setBody] = useState(latest?.body || ""),
    [form, setForm] = useState(item?.form || "image_text"),
    [assets, setAssets] = useState<string[]>(latest?.assets || []),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const material = useResource<any[]>(() => api("/assets"), []);
  return (
    <Modal
      title={item ? "编辑内容 · 保存为新版本" : "新建内容"}
      close={close}
      wide
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const data = {
              title,
              body,
              form,
              assets,
              version: item?.current_version,
            };
            if (item) await patch("/contents/" + item.id, data);
            else await post("/contents", data);
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
          <div className="form-grid">
            <Field label="内容标题">
              <input
                required
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            <Field label="内容形式">
              <select
                disabled={Boolean(item)}
                value={form}
                onChange={(e) => setForm(e.target.value)}
              >
                <option value="image_text">图文卡片</option>
                <option value="video">AI 短视频</option>
              </select>
            </Field>
          </div>
          <Field label="正文或最终脚本">
            <textarea
              required
              rows={9}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          <Field label="关联已授权素材">
            <div className="button-row">
              {material.value
                ?.filter((a) => a.consent)
                .map((a) => (
                  <label className="check" key={a.id}>
                    <input
                      type="checkbox"
                      checked={assets.includes(a.id)}
                      onChange={(e) =>
                        setAssets(
                          e.target.checked
                            ? [...assets, a.id]
                            : assets.filter((x) => x !== a.id),
                        )
                      }
                    />
                    {a.name}
                  </label>
                ))}
            </div>
          </Field>
          {item && (
            <Notice>
              保存后将生成新版本，当前版本的评分和预测会保留。发布前需为新成品重新评分。
            </Notice>
          )}
        </div>
        <div className="form-footer">
          <button className="button" type="button" onClick={close}>
            取消
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "保存中…" : "保存内容"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function Generate({
  close,
  saved,
  initialTopic = "",
}: {
  close: () => void;
  saved: () => void;
  initialTopic?: string;
}) {
  const [topic, setTopic] = useState(initialTopic),
    [form, setForm] = useState("image_text"),
    [funding, setFunding] = useState("platform"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="让 AI 起草一条内容" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/runs", {
              kind: "content",
              request_id: uid(),
              funding,
              input: { topic, form },
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
          <Notice>
            AI依据已发布的机构知识库创作，完成后会出现在内容库。图片和视频可继续生成。
          </Notice>
          {error && <Notice tone="error">{error}</Notice>}
          <Field label="这次想和家长聊什么？">
            <textarea
              required
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：孩子用AI写作业，家长可以怎样引导？"
            />
          </Field>
          <div className="form-grid">
            <Field label="内容形式">
              <select value={form} onChange={(e) => setForm(e.target.value)}>
                <option value="image_text">图文卡片</option>
                <option value="video">AI 短视频</option>
              </select>
            </Field>
            <Field label="调用费用">
              <select
                value={funding}
                onChange={(e) => setFunding(e.target.value)}
              >
                <option value="platform">平台额度</option>
                <option value="byok">机构自带 Key</option>
              </select>
            </Field>
          </div>
        </div>
        <div className="form-footer">
          <button className="button primary" disabled={busy}>
            <Sparkles size={15} />
            {busy ? "提交中…" : "生成内容草稿"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function MediaGenerate({
  item,
  close,
  saved,
}: {
  item?: ContentItem;
  close: () => void;
  saved: () => void;
}) {
  const [kind, setKind] = useState(item?.form === "video" ? "video" : "image"),
    [prompt, setPrompt] = useState(
      item ? item.title + "。" + item.versions[0].body : "",
    ),
    [funding, setFunding] = useState("platform"),
    [duration, setDuration] = useState(10),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="生成 AI 配图或视频" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/media-jobs", {
              kind,
              prompt,
              funding,
              duration,
              ratio: kind === "image" ? "3:4" : "9:16",
              content_id: item?.id || "",
              narration:
                kind === "video"
                  ? (item?.versions[0].body || prompt).slice(0, duration * 4)
                  : "",
              request_id: uid(),
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
          <Notice>
            生成前检查可用额度；视频异步生成，结果会转存到机构素材库。
          </Notice>
          <div className="form-grid">
            <Field label="媒体类型">
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="image">AI 配图</option>
                <option value="video">AI 视频</option>
              </select>
            </Field>
            <Field label="调用费用">
              <select
                value={funding}
                onChange={(e) => setFunding(e.target.value)}
              >
                <option value="platform">平台额度</option>
                <option value="byok">机构自带 Key</option>
              </select>
            </Field>
          </div>
          <Field label="画面描述或视频分镜">
            <textarea
              required
              rows={6}
              maxLength={4000}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </Field>
          {kind === "video" && (
            <Field label="视频时长（秒）">
              <input
                required
                type="number"
                min={2}
                max={15}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </Field>
          )}
        </div>
        <div className="form-footer">
          <button className="button primary" disabled={busy}>
            {busy ? "提交中…" : "提交生成任务"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function PublishModal({
  item,
  close,
  saved,
}: {
  item: ContentItem;
  close: () => void;
  saved: () => void;
}) {
  const accounts = useResource<any[]>(() => api("/social-accounts"), []),
    [account, setAccount] = useState(""),
    [at, setAt] = useState(
      localInput(new Date(Date.now() + 15 * 60000).toISOString()),
    ),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [requestId] = useState(uid);
  return (
    <Modal title="安排发布" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/contents/" + item.id + "/publish", {
              account_id: account,
              scheduled_at: new Date(at).toISOString(),
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
          <Notice>
            发布绑定当前成品 v{item.current_version}
            。素材授权、内容检查和盲预测均通过后执行。
          </Notice>
          <Field label="发布账号">
            <select
              required
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            >
              <option value="">请选择</option>
              {accounts.value?.map((a) => (
                <option key={a.id} value={a.id}>
                  {platforms[a.platform]} · {a.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="发布时间">
            <input
              required
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
            />
          </Field>
        </div>
        <div className="form-footer">
          <button className="button primary" disabled={busy}>
            <CalendarDays size={15} />
            加入发布日历
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function ContentPage({ role }: { role: string }) {
  const [tab, setTab] = useState("library"),
    [selected, setSelected] = useState(""),
    [edit, setEdit] = useState<ContentItem | null | undefined>(undefined),
    [generate, setGenerate] = useState(
      Boolean(location.hash.includes("?topic=")),
    ),
    [media, setMedia] = useState<ContentItem | null | undefined>(undefined),
    [publish, setPublish] = useState<ContentItem | null>(null),
    [notice, setNotice] = useState("");
  const items = useResource<ContentItem[]>(() => api("/contents"), [], 7000);
  const chosen = items.value?.find((x) => x.id === selected),
    initialTopic = location.hash.split("?topic=")[1] || "";
  return (
    <>
      <PageTitle
        eyebrow="CONTENT STUDIO"
        title="内容工作室"
        text="把家长关心的问题，变成持续带来咨询的好内容。"
        action={
          <div className="button-row">
            <button className="button" onClick={() => setEdit(null)}>
              <Plus size={15} />
              新建内容
            </button>
            <button
              className="button primary"
              onClick={() => setGenerate(true)}
            >
              <Sparkles size={15} />
              AI 创作
            </button>
          </div>
        }
      />
      <div className="tabs">
        {[
          ["library", "内容库"],
          ["topic", "选题池"],
          ["campaign", "自动计划"],
          ["assets", "素材库"],
          ["jobs", "生成任务"],
          ["rubrics", "评分规则"],
        ].map(([k, l]) => (
          <button
            key={k}
            className={"tab " + (tab === k ? "active" : "")}
            onClick={() => setTab(k)}
          >
            {l}
          </button>
        ))}
      </div>
      {notice && <Notice>{notice}</Notice>}
      {tab === "campaign" ? (
        <Notice>
          自动运营计划已迁移至 <a href="#matrix">自媒体矩阵</a>
          。旧计划保留为历史记录，需要补齐品牌、明确账号和预算后启用。
        </Notice>
      ) : tab === "topic" ? (
        <RecordPage key={tab} kind={tab} role={role} />
      ) : tab === "assets" ? (
        <AssetsPage />
      ) : tab === "rubrics" ? (
        <RubricsPage role={role} />
      ) : tab === "jobs" ? (
        <JobsPage />
      ) : items.loading ? (
        <Loading />
      ) : items.error ? (
        <Notice tone="error">{items.error}</Notice>
      ) : !items.value?.length ? (
        <div className="panel">
          <Empty
            title="从一个真实问题开始"
            text="整理课程资料后，AI可以为你起草图文和视频脚本。"
            action={
              <button
                className="button primary"
                onClick={() => setGenerate(true)}
              >
                <Sparkles size={15} />
                创作第一条内容
              </button>
            }
          />
        </div>
      ) : (
        <div className="card-grid">
          {items.value.map((item) => (
            <article className="panel content-card" key={item.id}>
              <div className="content-cover">
                {item.versions[0]?.assets[0] ? (
                  item.form === "video" ? (
                    <Video size={35} />
                  ) : (
                    <img
                      alt=""
                      src={
                        "/api/v1/assets/" +
                        item.versions[0].assets[0] +
                        "/download"
                      }
                    />
                  )
                ) : item.form === "video" ? (
                  <Video size={32} />
                ) : (
                  <FileText size={32} />
                )}
                <Badge
                  value={
                    item.predictions.some(
                      (p) => p.version_id === item.versions[0]?.id,
                    )
                      ? "approved"
                      : "draft"
                  }
                  label={
                    item.predictions.some(
                      (p) => p.version_id === item.versions[0]?.id,
                    )
                      ? "已评分"
                      : "待完善"
                  }
                />
              </div>
              <div className="card-body">
                <h3>{item.title}</h3>
                <p>{item.versions[0]?.body}</p>
                <div className="content-meta">
                  <span>
                    {item.form === "video" ? "AI 短视频" : "图文卡片"} · v
                    {item.current_version}
                  </span>
                  <span>{date((item as any).created_at)}</span>
                </div>
              </div>
              <div className="card-actions">
                <button
                  className="button small"
                  onClick={() => setSelected(item.id)}
                >
                  查看与评分
                  <ArrowUpRight size={12} />
                </button>
                <button
                  className="button small"
                  onClick={() => setPublish(item)}
                >
                  安排发布
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {generate && (
        <Generate
          close={() => setGenerate(false)}
          saved={() => {
            items.refresh();
            setTab("jobs");
          }}
          initialTopic={decodeURIComponent(initialTopic)}
        />
      )}
      {edit !== undefined && (
        <ContentForm
          item={edit || undefined}
          close={() => setEdit(undefined)}
          saved={items.refresh}
        />
      )}
      {media !== undefined && (
        <MediaGenerate
          item={media || undefined}
          close={() => setMedia(undefined)}
          saved={() => {
            setNotice("媒体任务已提交，可在生成任务中查看进度。");
            items.refresh();
          }}
        />
      )}
      {publish && (
        <PublishModal
          item={publish}
          close={() => setPublish(null)}
          saved={() => setNotice("已加入发布日历。")}
        />
      )}
      {chosen && (
        <Modal
          title={"成品详情 · v" + chosen.current_version}
          close={() => setSelected("")}
          wide
        >
          <div className="form-body">
            <h3 style={{ marginBottom: 15 }}>{chosen.title}</h3>
            <div className="content-detail">{chosen.versions[0]?.body}</div>
            {chosen.versions[0]?.policy_notes.map((n) => (
              <Notice key={n} tone="error">
                {n}
              </Notice>
            ))}
            <div className="button-row space-top">
              <button
                className="button"
                onClick={() => {
                  setEdit(chosen);
                  setSelected("");
                }}
              >
                编辑新版本
              </button>
              <button
                className="button"
                onClick={() => {
                  setMedia(chosen);
                  setSelected("");
                }}
              >
                <Sparkles size={14} />
                生成配图 / 视频
              </button>
              <button
                className="button primary"
                onClick={async () => {
                  try {
                    await post("/runs", {
                      kind: "predict",
                      request_id: uid(),
                      input: { version_id: chosen.versions[0].id },
                    });
                    setNotice("盲评任务已提交，完成后会显示评分。");
                    setSelected("");
                    setTab("jobs");
                  } catch (e) {
                    setNotice((e as Error).message);
                  }
                }}
              >
                独立盲评
              </button>
            </div>
            {chosen.predictions
              .filter((p) => p.version_id === chosen.versions[0]?.id)
              .map((p) => (
                <div key={p.id}>
                  <div className="score-grid">
                    {[
                      ["composite", "综合分"],
                      ["clarity", "清晰度"],
                      ["relevance", "家长相关"],
                      ["usefulness", "实用性"],
                      ["credibility", "可信度"],
                      ["narrative", "叙事"],
                      ["actionability", "可行动"],
                      ["accessibility", "易理解"],
                    ].map(([k, l]) => (
                      <div className="score-cell" key={k}>
                        <b>{p.payload[k]}</b>
                        {l}
                      </div>
                    ))}
                  </div>
                  <Notice>
                    {p.rubric_version} ·{" "}
                    {p.payload.calibrated ? "已校准" : "初始规则，尚未校准"}
                  </Notice>
                  <p className="content-detail">
                    {p.payload.reasoning}
                    <br />
                    预测：{p.payload.bet}
                  </p>
                </div>
              ))}
          </div>
        </Modal>
      )}
    </>
  );
}
export function AssetsPage() {
  const data = useResource<any[]>(() => api("/assets"), [], 8000),
    [notice, setNotice] = useState("");
  return (
    <>
      <div className="button-row" style={{ marginBottom: 17 }}>
        <label className="button">
          <Upload size={15} />
          上传已授权素材
          <input
            hidden
            type="file"
            accept="image/png,image/jpeg,image/webp,video/mp4,application/pdf,.txt,.md"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const form = new FormData();
              form.append("file", file);
              form.append("consent", "true");
              form.append("purpose", "content");
              try {
                await api("/assets", { method: "POST", body: form });
                data.refresh();
              } catch (e) {
                setNotice((e as Error).message);
              }
            }}
          />
        </label>
        <small className="text-muted">上传即确认机构拥有素材使用授权。</small>
      </div>
      {notice && <Notice>{notice}</Notice>}
      {!data.value?.length ? (
        <div className="panel">
          <Empty
            title="为内容准备真实素材"
            text="上传机构已授权的图片、视频和课程资料。"
          />
        </div>
      ) : (
        <div className="asset-grid">
          {data.value.map((a) => (
            <div className="asset-card" key={a.id}>
              {a.mime.startsWith("image/") ? (
                <img
                  src={"/api/v1/assets/" + a.id + "/download"}
                  alt={a.name}
                />
              ) : a.mime === "video/mp4" ? (
                <video controls src={"/api/v1/assets/" + a.id + "/download"} />
              ) : (
                <FileText size={30} />
              )}
              <p style={{ margin: "12px 0" }}>{a.name}</p>
              <div className="button-row">
                <a
                  className="button small"
                  href={"/api/v1/assets/" + a.id + "/download"}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看
                </a>
                <Badge
                  value={a.consent ? "approved" : "draft"}
                  label={a.consent ? "已授权" : "待确认"}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
export function JobsPage() {
  const agent = useResource<Job[]>(() => api("/runs"), [], 5000),
    media = useResource<Job[]>(() => api("/media-jobs"), [], 5000);
  const rows = [
    ...(agent.value || []).map((x) => ({ ...x, category: "agent" })),
    ...(media.value || []).map((x) => ({ ...x, category: "media" })),
  ].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <div className="panel">
      <div className="toolbar">
        <strong style={{ fontSize: 12 }}>生成与评分任务</strong>
        <button
          className="button small"
          onClick={() => {
            agent.refresh();
            media.refresh();
          }}
        >
          <RefreshCw size={13} />
          刷新
        </button>
      </div>
      {!rows.length ? (
        <Empty text="提交AI创作、配图、视频或评分后，可以在这里查看进度。" />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>时间</th>
                <th>结果与说明</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.id}>
                  <td>
                    {{
                      content: "内容起草",
                      predict: "内容盲评",
                      image: "AI配图",
                      video: "AI视频",
                      feedback: "课堂反馈",
                      ocr: "票据识别",
                      chat: "客服回答",
                    }[x.kind || ""] || x.kind}
                    <span className="sub">{x.id.slice(0, 10)}</span>
                  </td>
                  <td>
                    <Badge value={x.status} />
                  </td>
                  <td>{date(x.created_at, true)}</td>
                  <td>
                    {x.error ||
                      x.output?.title ||
                      x.output?.body ||
                      (x.status === "succeeded"
                        ? "已保存到对应业务记录"
                        : "等待处理")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
export function PublishingPage() {
  const jobs = useResource<Job[]>(() => api("/publish-jobs"), [], 7000),
    metrics = useResource<any[]>(() => api("/metrics"), [], 7000),
    [notice, setNotice] = useState(""),
    [editing, setEditing] = useState<Job | null>(null);
  return (
    <>
      <PageTitle
        eyebrow="PUBLISH & LEARN"
        title="发布与复盘"
        text="每一次发布都有记录，每一条实绩都能追溯。"
      />
      {notice && <Notice>{notice}</Notice>}
      <div className="panel">
        <div className="toolbar">
          <strong style={{ fontSize: 12 }}>发布日历</strong>
          <button className="button small" onClick={jobs.refresh}>
            <RefreshCw size={13} />
            刷新
          </button>
        </div>
        {!jobs.value?.length ? (
          <Empty
            title="排好下一条内容"
            text="在内容库完成成品评分后，选择账号与时间安排发布。"
            action={
              <a className="button" href="#content">
                前往内容工作室
                <ArrowUpRight size={13} />
              </a>
            }
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>发布时间</th>
                  <th>状态</th>
                  <th>结果</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {jobs.value.map((j) => (
                  <tr key={j.id}>
                    <td>{date(j.scheduled_at, true)}</td>
                    <td>
                      <Badge value={j.status} />
                    </td>
                    <td>
                      {j.external_url ? (
                        <a
                          href={j.external_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          查看作品 ↗
                        </a>
                      ) : (
                        j.error || "等待发布"
                      )}
                    </td>
                    <td>
                      <div className="button-row">
                        {j.status === "unknown" && (
                          <button
                            className="button link"
                            onClick={async () => {
                              try {
                                await post(
                                  "/publish-jobs/" + j.id + "/reconcile",
                                );
                                jobs.refresh();
                              } catch (e) {
                                setNotice((e as Error).message);
                              }
                            }}
                          >
                            核实结果
                          </button>
                        )}
                        {j.status === "succeeded" && (
                          <button
                            className="button link"
                            onClick={() => setEditing(j)}
                          >
                            登记实绩
                          </button>
                        )}
                        {j.status === "scheduled" && (
                          <button
                            className="button link"
                            onClick={async () => {
                              await post("/jobs/publish/" + j.id + "/cancel");
                              jobs.refresh();
                            }}
                          >
                            取消排期
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="panel space-top">
        <div className="panel-head">
          <h2>内容实绩</h2>
          <small>缺失指标保留为空，默认 T+3 天回收</small>
        </div>
        {!metrics.value?.length ? (
          <Empty
            title="发布后再看真实表现"
            text="系统回收平台指标，也支持运营人员补录。"
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>记录时间</th>
                  <th>来源</th>
                  <th>播放 / 阅读</th>
                  <th>收藏</th>
                  <th>预约</th>
                  <th>复盘</th>
                </tr>
              </thead>
              <tbody>
                {metrics.value.map((m) => (
                  <tr key={m.id}>
                    <td>{date(m.created_at, true)}</td>
                    <td>{m.source === "manual" ? "人工登记" : "平台回收"}</td>
                    <td>{m.metrics.plays ?? "—"}</td>
                    <td>{m.metrics.saves ?? "—"}</td>
                    <td>{m.metrics.bookings ?? "—"}</td>
                    <td>
                      {m.summary ? (
                        <span>{m.summary.slice(0, 60)}</span>
                      ) : (
                        <button
                          className="button link"
                          onClick={async () => {
                            try {
                              await post("/runs", {
                                kind: "retro",
                                request_id: uid(),
                                input: { metric_id: m.id },
                              });
                              setNotice("复盘任务已提交。");
                            } catch (e) {
                              setNotice((e as Error).message);
                            }
                          }}
                        >
                          AI复盘
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && (
        <MetricForm
          job={editing}
          close={() => setEditing(null)}
          saved={metrics.refresh}
        />
      )}
    </>
  );
}
function MetricForm({
  job,
  close,
  saved,
}: {
  job: Job;
  close: () => void;
  saved: () => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="登记作品实绩" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget),
            body: Record<string, number | null> = {};
          for (const [k, v] of f.entries())
            body[k] = v === "" ? null : Number(v);
          setBusy(true);
          try {
            await post("/publish-jobs/" + job.id + "/metrics", body);
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
          <Notice>平台没有提供的指标请留空。</Notice>
          <div className="form-grid">
            {[
              ["plays", "播放 / 阅读"],
              ["likes", "点赞"],
              ["saves", "收藏"],
              ["shares", "分享"],
              ["comments", "评论"],
              ["inquiries", "有效咨询"],
              ["bookings", "实际预约"],
              ["enrollments", "报名"],
            ].map(([k, l]) => (
              <Field key={k} label={l}>
                <input type="number" min={0} name={k} />
              </Field>
            ))}
          </div>
        </div>
        <div className="form-footer">
          <button disabled={busy} className="button primary">
            保存实绩
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function RubricsPage({
  role,
  profileId = "",
}: {
  role: string;
  profileId?: string;
}) {
  const [profile, setProfile] = useState(profileId);
  const profiles = useResource<any[]>(() => api("/media-profiles"), []);
  const data = useResource<any>(
      () =>
        api(
          "/rubrics" +
            (profile ? "?profile_id=" + encodeURIComponent(profile) : ""),
        ),
      [profile],
      5000,
    ),
    [form, setForm] = useState("image_text"),
    [notes, setNotes] = useState(""),
    [funding, setFunding] = useState("platform"),
    [weights, setWeights] = useState<Record<string, number>>({
      clarity: 1,
      relevance: 1,
      usefulness: 1,
      credibility: 1,
      narrative: 1,
      actionability: 1,
      accessibility: 1,
    }),
    [notice, setNotice] = useState("");
  const names: Record<string, string> = {
    clarity: "清晰度",
    relevance: "受众相关",
    usefulness: "实用性",
    credibility: "可信度",
    narrative: "叙事节奏",
    actionability: "可执行",
    accessibility: "可访问性",
  };
  return (
    <div className="settings-grid">
      <section className="panel settings-card">
        <h2>当前教育内容规则</h2>
        <Field label="评分规则所属品牌">
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="">机构手动内容（独立样本池）</option>
            {profiles.value?.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <p>
          图文与视频使用独立规则。初始版本未经实绩校准，评分用于改进内容，不能保证传播结果。
        </p>
        {Object.entries(data.value?.active || {}).map(([f, r]: any) => (
          <div key={f}>
            <div className="kv">
              <strong>{f === "video" ? "教学视频" : "教育图文"}</strong>
              <span>{r.version}</span>
            </div>
            {Object.entries(r.dimensions).map(([k, v]: any) => (
              <div className="kv" key={k}>
                <span>{names[k]}</span>
                <span style={{ maxWidth: "70%" }}>{v}</span>
              </div>
            ))}
          </div>
        ))}
      </section>
      <section className="panel settings-card">
        <h2>提交候选规则</h2>
        <p>
          至少5个成品版本与5条T+3实绩样本。全量重新评分、独立模型复核以及排序一致性达到80%后，由负责人启用。
        </p>
        {notice && <Notice>{notice}</Notice>}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await post("/rubrics", {
                profile_id: profile || null,
                form,
                weights,
                notes,
                funding,
                request_id: uid(),
              });
              setNotice("候选规则已提交重算");
              data.refresh();
            } catch (e) {
              setNotice((e as Error).message);
            }
          }}
        >
          <Field label="内容形式">
            <select value={form} onChange={(e) => setForm(e.target.value)}>
              <option value="image_text">教育图文</option>
              <option value="video">教学视频</option>
            </select>
          </Field>
          <div className="form-grid">
            {Object.entries(weights).map(([k, v]) => (
              <Field label={names[k] + " 权重"} key={k}>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={v}
                  onChange={(e) =>
                    setWeights({ ...weights, [k]: Number(e.target.value) })
                  }
                />
              </Field>
            ))}
          </div>
          <Field label="变更理由与样本依据">
            <textarea
              required
              minLength={20}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>
          <Field label="重算费用来源">
            <select
              value={funding}
              onChange={(e) => setFunding(e.target.value)}
            >
              <option value="platform">平台额度</option>
              <option value="byok">机构自带 Key</option>
            </select>
          </Field>
          <button className="button primary" disabled={!can("rubric.manage")}>
            提交完整样本集重算
          </button>
        </form>
      </section>
      <section className="panel settings-card full">
        <h2>规则升级记录</h2>
        {data.value?.candidates?.length ? (
          data.value.candidates.map((c: any) => (
            <div className="kv" key={c.id}>
              <div>
                <b>{c.id.slice(0, 10)}</b> · <Badge value={c.status} />
                <p style={{ marginTop: 7 }}>
                  排序一致性：
                  {Math.round((c.report.ranking_agreement || 0) * 100)}% ·
                  独立复核：{c.report.review_model || "等待执行"}
                </p>
                <p>{c.report.independent_review?.reasons.join("；")}</p>
              </div>
              {can("rubric.manage") && c.status === "reviewed" && (
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      await post("/rubrics/" + c.id + "/activate");
                      data.refresh();
                      setNotice("评分规则已启用，原有预测继续保留");
                    } catch (e) {
                      setNotice((e as Error).message);
                    }
                  }}
                >
                  启用此规则
                </button>
              )}
            </div>
          ))
        ) : (
          <Empty
            title="尚无规则升级"
            text="先积累真实发布和T+3数据，再按证据调整规则。"
          />
        )}
      </section>
    </div>
  );
}
