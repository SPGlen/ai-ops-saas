import { RubricsPage } from "./ContentPage";
import React, { useEffect, useState } from "react";
import {
  Users,
  Workflow,
  CalendarDays,
  Layers3,
  Play,
  Pause,
  Plus,
  RefreshCw,
  ShieldCheck,
  ArrowUpRight,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api, post, patch, can, uid, money, date, platforms } from "./api";
import {
  PageTitle,
  Notice,
  Modal,
  Field,
  Empty,
  Badge,
  Loading,
  useResource,
} from "./ui";

const modes: Record<string, string> = {
  program: "程序合成",
  aigc: "AIGC视频",
  mixed: "混合制作",
};
const stages: Record<string, string> = {
  sources: "资料采集",
  creation: "选题与分账号创作",
  media: "素材与配音",
  composition: "成品合成",
  prediction: "独立盲评",
  review: "审核",
  publish: "发布核实",
  metrics: "T+3数据回收",
  retro: "复盘",
};
const dayNames = ["一", "二", "三", "四", "五", "六", "日"];
const freshSpec = () => ({
  direction: "",
  account_ids: [] as string[],
  group_ids: [] as string[],
  mode: "matrix",
  source_urls: [] as string[],
  xhs_search: false,
  weekdays: [1, 4],
  times: ["18:00"],
  timezone: "Asia/Shanghai",
  funding: "platform",
  review: "manual",
  allowed_render_modes: ["program", "aigc", "mixed"],
  min_video_seconds: 45,
  max_video_seconds: 90,
  run_budget_fen: 0,
  daily_budget_fen: 0,
});
const toggle = (xs: string[], key: string) =>
  xs.includes(key) ? xs.filter((x) => x !== key) : [...xs, key];

function Picks({
  items,
  selected,
  set,
}: {
  items: { id: string; name: string }[];
  selected: string[];
  set: (ids: string[]) => void;
}) {
  return (
    <div className="matrix-picks">
      {items.map((x) => (
        <label className="check" key={x.id}>
          <input
            type="checkbox"
            aria-label={x.name}
            checked={selected.includes(x.id)}
            onChange={() => set(toggle(selected, x.id))}
          />
          {x.name}
        </label>
      ))}
      {!items.length && <small>暂无可选记录</small>}
    </div>
  );
}
function Amount({
  label,
  value,
  set,
}: {
  label: string;
  value: number;
  set: (v: number) => void;
}) {
  return (
    <Field label={label + "（元）"}>
      <input
        type="number"
        min="0"
        step="0.01"
        required
        value={value / 100}
        onChange={(e) => set(Math.round(Number(e.target.value) * 100))}
      />
    </Field>
  );
}

function MatrixEditor({
  kind,
  item,
  profiles,
  groups,
  accounts,
  close,
  saved,
}: {
  kind: string;
  item: any;
  profiles: any[];
  groups: any[];
  accounts: any[];
  close: () => void;
  saved: () => void;
}) {
  const blank: any =
    kind === "profile"
      ? {
          name: "",
          audience: "小学阶段家长",
          style: "清楚、真实、有用",
          knowledge_ids: [],
          asset_ids: [],
        }
      : kind === "group"
        ? { name: "", profile_id: profiles[0]?.id || "", account_ids: [] }
        : kind === "plan"
          ? { name: "", profile_id: profiles[0]?.id || "", spec: freshSpec() }
          : kind === "settings"
            ? { monthly_budget_fen: 0, paused: false }
            : {
                name: "",
                platform: "xiaohongshu",
                profile_id: profiles[0]?.id || null,
                positioning: "",
                call_to_action: "",
                form: null,
                monthly_budget_fen: 0,
                paused: false,
              };
  const initial =
    kind === "account" && item
      ? { ...item, ...(item.config?.matrix || {}) }
      : item;
  const [v, setV] = useState<any>(initial || blank),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const knowledge = useResource<any>(
    () =>
      kind === "profile"
        ? api("/records/knowledge?limit=200")
        : Promise.resolve({ items: [] }),
    [],
  );
  const assets = useResource<any[]>(
    () => (kind === "profile" ? api("/assets") : Promise.resolve([])),
    [],
  );
  const set = (key: string, value: any) =>
    setV((old: any) => ({ ...old, [key]: value }));
  const setSpec = (key: string, value: any) =>
    setV((old: any) => ({ ...old, spec: { ...old.spec, [key]: value } }));
  const profileSelect = (
    <Field label="品牌档案">
      <select
        required
        value={v.profile_id || ""}
        disabled={Boolean(item?.id) && kind === "plan"}
        onChange={(e) => {
          setV({
            ...v,
            profile_id: e.target.value,
            ...(kind === "group" ? { account_ids: [] } : {}),
            ...(kind === "plan"
              ? { spec: { ...v.spec, account_ids: [], group_ids: [] } }
              : {}),
          });
        }}
      >
        <option value="">请选择品牌</option>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </Field>
  );
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (kind === "profile") {
        const body = {
          name: v.name,
          audience: v.audience,
          style: v.style,
          knowledge_ids: v.knowledge_ids,
          asset_ids: v.asset_ids,
          ...(v.id ? { version: v.version } : {}),
        };
        if (v.id) await patch("/media-profiles/" + v.id, body);
        else await post("/media-profiles", body);
      }
      if (kind === "group") {
        const body = {
          name: v.name,
          profile_id: v.profile_id,
          account_ids: v.account_ids,
          ...(v.id ? { version: v.version } : {}),
        };
        if (v.id) await patch("/account-groups/" + v.id, body);
        else await post("/account-groups", body);
      }
      if (kind === "plan") {
        const body = {
          name: v.name,
          profile_id: v.profile_id,
          spec: v.spec,
          ...(v.id ? { version: v.version } : {}),
        };
        if (v.id) await patch("/automation-plans/" + v.id, body);
        else await post("/automation-plans", body);
      }
      if (kind === "account") {
        let id = v.id;
        if (!id) {
          const a = await post("/social-accounts", {
            name: v.name,
            platform: v.platform,
          });
          id = a.id;
        }
        await patch("/social-accounts/" + id + "/matrix", {
          profile_id: v.profile_id || null,
          positioning: v.positioning || "",
          call_to_action: v.call_to_action || "",
          form: v.form || null,
          monthly_budget_fen: v.monthly_budget_fen || 0,
          paused: v.paused || false,
        });
      }
      if (kind === "settings")
        await api("/matrix/settings", {
          method: "PUT",
          body: JSON.stringify({
            monthly_budget_fen: v.monthly_budget_fen,
            paused: v.paused,
          }),
        });
      saved();
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={
        kind === "profile"
          ? "品牌与内容边界"
          : kind === "group"
            ? "矩阵账号分组"
            : kind === "plan"
              ? "自动运营计划"
              : kind === "settings"
                ? "机构自媒体预算与总开关"
                : "矩阵账号配置"
      }
      close={close}
      wide={kind === "plan" || kind === "profile"}
    >
      <form onSubmit={submit}>
        <div className="form-body">
          {error && <Notice tone="error">{error}</Notice>}
          {kind !== "settings" && (
            <Field label={kind === "account" ? "账号备注" : "名称"}>
              <input
                required
                value={v.name}
                disabled={kind === "account" && Boolean(item)}
                onChange={(e) => set("name", e.target.value)}
                maxLength={80}
              />
            </Field>
          )}
          {kind === "profile" && (
            <>
              <div className="form-grid">
                <Field label="目标受众">
                  <textarea
                    required
                    value={v.audience}
                    onChange={(e) => set("audience", e.target.value)}
                  />
                </Field>
                <Field label="品牌语气与内容规则">
                  <textarea
                    value={v.style}
                    onChange={(e) => set("style", e.target.value)}
                  />
                </Field>
              </div>
              <Field label="已审核的机构事实">
                <Picks
                  items={
                    knowledge.value?.items
                      .filter((k: any) => k.data.approved)
                      .map((k: any) => ({ id: k.id, name: k.data.name })) || []
                  }
                  selected={v.knowledge_ids}
                  set={(ids) => set("knowledge_ids", ids)}
                />
              </Field>
              <Field label="已授权品牌素材">
                <Picks
                  items={(assets.value || [])
                    .filter(
                      (a) => a.consent && a.object_key?.includes("/content/"),
                    )
                    .map((a) => ({ id: a.id, name: a.name }))}
                  selected={v.asset_ids}
                  set={(ids) => set("asset_ids", ids)}
                />
              </Field>
              <Notice>
                仅引用选中的已审核知识库与授权素材。修改品牌后，相关计划需要负责人重新确认。
              </Notice>
            </>
          )}
          {kind === "group" && (
            <>
              {profileSelect}
              <Field label="账号（支持同平台多个账号）">
                <Picks
                  items={accounts
                    .filter((a) => a.profile_id === v.profile_id)
                    .map((a) => ({
                      id: a.id,
                      name: platforms[a.platform] + " · " + a.name,
                    }))}
                  selected={v.account_ids}
                  set={(ids) => set("account_ids", ids)}
                />
              </Field>
            </>
          )}
          {kind === "account" && (
            <>
              <div className="form-grid">
                <Field label="平台">
                  <select
                    disabled={Boolean(item)}
                    value={v.platform}
                    onChange={(e) => set("platform", e.target.value)}
                  >
                    {Object.entries(platforms).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                {profileSelect}
              </div>
              <Field label="账号定位 / 校区 / 栏目">
                <textarea
                  value={v.positioning}
                  onChange={(e) => set("positioning", e.target.value)}
                />
              </Field>
              <Field label="行动引导语">
                <input
                  value={v.call_to_action}
                  onChange={(e) => set("call_to_action", e.target.value)}
                />
              </Field>
              <div className="form-grid">
                <Field label="默认内容形式">
                  <select
                    value={v.form || ""}
                    onChange={(e) => set("form", e.target.value || null)}
                  >
                    <option value="">按平台默认</option>
                    {v.platform !== "channels" && (
                      <option value="image_text">图文卡片</option>
                    )}
                    <option value="video">视频</option>
                  </select>
                </Field>
                <Amount
                  label="账号月预算"
                  value={v.monthly_budget_fen || 0}
                  set={(n) => set("monthly_budget_fen", n)}
                />
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  checked={v.paused}
                  onChange={(e) => set("paused", e.target.checked)}
                />
                暂停该账号的新任务
              </label>
              <Notice>
                登录由每个账号单独扫码。身份核验与能力验证通过后，才能启用无人值守发布。
              </Notice>
            </>
          )}
          {kind === "settings" && (
            <>
              <Amount
                label="机构自媒体月预算"
                value={v.monthly_budget_fen || 0}
                set={(n) => set("monthly_budget_fen", n)}
              />
              <label className="check">
                <input
                  type="checkbox"
                  checked={v.paused}
                  onChange={(e) => set("paused", e.target.checked)}
                />
                暂停整个机构的自媒体自动任务
              </label>
              <Notice>
                预算为零时不调用模型。暂停后，已提交的付费任务仍回收结果并结算。
              </Notice>
            </>
          )}
          {kind === "plan" && (
            <>
              {profileSelect}
              <Field label="内容方向">
                <textarea
                  required
                  value={v.spec.direction}
                  onChange={(e) => setSpec("direction", e.target.value)}
                />
              </Field>
              <div className="form-grid">
                <Field label="运营模式">
                  <select
                    value={v.spec.mode}
                    onChange={(e) => setSpec("mode", e.target.value)}
                  >
                    <option value="matrix">母题矩阵分发 · 分账号改写</option>
                    <option value="independent">账号独立选题与创作</option>
                  </select>
                </Field>
                <Field label="成品发布策略">
                  <select
                    value={v.spec.review}
                    onChange={(e) => setSpec("review", e.target.value)}
                  >
                    <option value="manual">逐条审核后发布</option>
                    <option value="auto">负责人授权后自动发布</option>
                  </select>
                </Field>
              </div>
              <Field label="目标账号">
                <Picks
                  items={accounts
                    .filter((a) => a.profile_id === v.profile_id)
                    .map((a) => ({
                      id: a.id,
                      name: platforms[a.platform] + " · " + a.name,
                    }))}
                  selected={v.spec.account_ids}
                  set={(ids) => setSpec("account_ids", ids)}
                />
              </Field>
              <Field label="目标分组（重叠账号只执行一次）">
                <Picks
                  items={groups.filter((g) => g.profile_id === v.profile_id)}
                  selected={v.spec.group_ids}
                  set={(ids) => setSpec("group_ids", ids)}
                />
              </Field>
              <div className="form-grid">
                <Field label="每周执行日期">
                  <div className="matrix-picks">
                    {dayNames.map((d, index) => (
                      <label className="check" key={d}>
                        <input
                          type="checkbox"
                          checked={v.spec.weekdays.includes(index)}
                          onChange={() =>
                            setSpec(
                              "weekdays",
                              v.spec.weekdays.includes(index)
                                ? v.spec.weekdays.filter(
                                    (n: number) => n !== index,
                                  )
                                : [...v.spec.weekdays, index],
                            )
                          }
                        />
                        周{d}
                      </label>
                    ))}
                  </div>
                </Field>
                <Field label="中国时间（多个时间用逗号分隔）">
                  <input
                    required
                    value={v.spec.times.join(",")}
                    onChange={(e) =>
                      setSpec(
                        "times",
                        e.target.value.split(",").map((t) => t.trim()),
                      )
                    }
                    placeholder="18:00,20:00"
                  />
                </Field>
              </div>
              <Field label="RSS / Atom 来源（每行一个，需平台域名白名单）">
                <textarea
                  value={v.spec.source_urls.join("\n")}
                  onChange={(e) =>
                    setSpec(
                      "source_urls",
                      e.target.value
                        .split("\n")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    )
                  }
                />
              </Field>
              <label className="check">
                <input
                  type="checkbox"
                  checked={v.spec.xhs_search}
                  onChange={(e) => setSpec("xhs_search", e.target.checked)}
                />
                使用已验证的小红书搜索能力；不可用时标明来源缺失
              </label>
              <Field label="允许AI导演选择的制作方式">
                <Picks
                  items={Object.entries(modes).map(([id, name]) => ({
                    id,
                    name,
                  }))}
                  selected={v.spec.allowed_render_modes}
                  set={(ids) => setSpec("allowed_render_modes", ids)}
                />
              </Field>
              <div className="form-grid">
                <Field label="视频最短秒数">
                  <input
                    type="number"
                    min={45}
                    max={90}
                    value={v.spec.min_video_seconds}
                    onChange={(e) =>
                      setSpec("min_video_seconds", Number(e.target.value))
                    }
                  />
                </Field>
                <Field label="视频最长秒数">
                  <input
                    type="number"
                    min={45}
                    max={90}
                    value={v.spec.max_video_seconds}
                    onChange={(e) =>
                      setSpec("max_video_seconds", Number(e.target.value))
                    }
                  />
                </Field>
                <Amount
                  label="单次运行预算"
                  value={v.spec.run_budget_fen}
                  set={(n) => setSpec("run_budget_fen", n)}
                />
                <Amount
                  label="计划每日预算"
                  value={v.spec.daily_budget_fen}
                  set={(n) => setSpec("daily_budget_fen", n)}
                />
                <Field label="调用凭证">
                  <select
                    value={v.spec.funding}
                    onChange={(e) => setSpec("funding", e.target.value)}
                  >
                    <option value="platform">平台赠送额度</option>
                    <option value="byok">机构自带 Key</option>
                  </select>
                </Field>
              </div>
              <Notice>
                保存为新版本并关闭自动执行。负责人确认预算后可试运行；当前版本成品与盲评通过后，才能启用定时计划。
              </Notice>
            </>
          )}
        </div>
        <div className="form-footer">
          <button className="button" type="button" onClick={close}>
            取消
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "保存中…" : "保存配置"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function RunDetail({ id, close }: { id: string; close: () => void }) {
  const data = useResource<any>(
      () => api("/automation-runs/" + id),
      [id],
      5000,
    ),
    [notice, setNotice] = useState(""),
    [preview, setPreview] = useState<any>(null);
  useEffect(() => {
    const source = new EventSource("/api/v1/automation-runs/" + id + "/events");
    source.addEventListener("update", () => data.refresh());
    return () => source.close();
  }, [id]);
  const run = data.value;
  async function action(path: string, body: any = {}) {
    try {
      await post(path, body);
      data.refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function view(task: any) {
    try {
      const content = await api("/contents/" + task.content_id);
      setPreview(content.versions.find((v: any) => v.id === task.version_id));
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  return (
    <Modal title="自动运营任务 · 分账号追踪" close={close} wide>
      {data.loading ? (
        <Loading />
      ) : (
        <div className="form-body">
          {(notice || data.error) && (
            <Notice tone="error">{notice || data.error}</Notice>
          )}
          {run && (
            <>
              <div className="toolbar">
                <div>
                  <strong>{run.snapshot.name}</strong>
                  <small className="matrix-block">
                    实际费用 {money(run.cost?.actual_fen)} · 预占{" "}
                    {money(run.cost?.reserved_fen)} · 共享选题{" "}
                    {money(run.shared_cost?.actual_fen)}（仅计一次）
                  </small>{" "}
                  <Badge value={run.paused ? "suspended" : run.status} />{" "}
                  <small>
                    {run.trial ? "试运行 · 不发布" : "正式运行"} · v
                    {run.plan_version}
                  </small>
                </div>
                {can("campaign.write") && (
                  <button
                    className="button small"
                    onClick={() =>
                      action(
                        "/automation-runs/" +
                          id +
                          "/" +
                          (run.paused ? "resume" : "pause"),
                      )
                    }
                  >
                    {run.paused ? "恢复运行" : "暂停运行"}
                  </button>
                )}
              </div>
              <p className="muted">
                目标账号与配置已固定。实时刷新 · 最后更新{" "}
                {date(run.updated_at, true)}
              </p>
              {run.tasks.map((task: any) => {
                const account = run.snapshot.accounts.find(
                  (a: any) => a.id === task.account_id,
                );
                return (
                  <section className="matrix-task" key={task.id}>
                    <div className="toolbar">
                      <strong>
                        {platforms[account?.platform]} · {account?.name}
                      </strong>
                      <Badge value={task.status} />
                    </div>
                    <div className="matrix-flow">
                      {Object.entries(stages).map(([key, label]) => (
                        <div
                          key={key}
                          className={
                            "matrix-stage " +
                            (task.stage === key ? "current" : "")
                          }
                        >
                          {label}
                        </div>
                      ))}
                    </div>
                    {task.error && (
                      <Notice tone="error">
                        {task.error_code} · {task.error}
                      </Notice>
                    )}
                    <div className="button-row">
                      {task.status === "trial_ready" && (
                        <a
                          className="button small"
                          href="#publishing"
                          onClick={close}
                        >
                          前往首次发布联调
                        </a>
                      )}
                      {task.version_id && (
                        <button
                          className="button small"
                          onClick={() => view(task)}
                        >
                          查看固定成品
                        </button>
                      )}
                      {task.status === "awaiting_review" &&
                        can("publish.write") && (
                          <button
                            className="button primary small"
                            onClick={() =>
                              action(
                                "/automation-tasks/" + task.id + "/approve",
                              )
                            }
                          >
                            审核通过并排期
                          </button>
                        )}
                      {task.publish_job_id && (
                        <button
                          className="button small"
                          onClick={() =>
                            action(
                              "/publish-jobs/" +
                                task.publish_job_id +
                                "/reconcile",
                            )
                          }
                        >
                          核实发布结果
                        </button>
                      )}
                    </div>
                    {task.data.booking_url && (
                      <p>
                        <a
                          href={task.data.booking_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          该任务的招生归因入口 ↗
                        </a>
                      </p>
                    )}
                    <details>
                      <summary>步骤、分镜和模型任务</summary>
                      {task.steps.map((st: any) => (
                        <div className="matrix-step-detail" key={st.id}>
                          <strong>{st.key}</strong> <Badge value={st.status} />
                          <small className="matrix-block">
                            {st.cost?.shared ? "品牌共享 · " : ""}费用{" "}
                            {money(st.cost?.actual_fen)} / 预占{" "}
                            {money(st.cost?.reserved_fen)}
                          </small>
                          {can("content.write") &&
                            st.object_id &&
                            ["failed", "waiting_authorization"].includes(
                              st.status,
                            ) && (
                              <button
                                className="button small"
                                onClick={() =>
                                  action(
                                    "/automation-tasks/" +
                                      task.id +
                                      "/steps/" +
                                      st.key +
                                      "/retry",
                                    { request_id: uid() },
                                  )
                                }
                              >
                                重试明确失败的调用
                              </button>
                            )}
                          {can("content.write") &&
                            st.object_id &&
                            [
                              "failed",
                              "unknown",
                              "waiting_authorization",
                            ].includes(st.status) &&
                            (st.key === "image" ||
                              st.key === "speech" ||
                              st.key.startsWith("clip-")) && (
                              <button
                                className="button small"
                                onClick={() =>
                                  action(
                                    "/media-jobs/" + st.object_id + "/resume",
                                  )
                                }
                              >
                                继续回收已有结果
                              </button>
                            )}
                          {st.detail?.estimated_remaining_cost_fen != null && (
                            <p>
                              后续媒体、盲评与复盘预估上限{" "}
                              {money(st.detail.estimated_remaining_cost_fen)}
                            </p>
                          )}
                          {st.detail?.render_mode && (
                            <p>
                              AI导演：{modes[st.detail.render_mode]} ·{" "}
                              {st.detail.decision_reason}
                            </p>
                          )}
                          <pre>{JSON.stringify(st.detail, null, 2)}</pre>
                        </div>
                      ))}
                    </details>
                  </section>
                );
              })}
            </>
          )}
        </div>
      )}
      {preview && (
        <div className="form-body matrix-preview">
          <h3>{preview.title}</h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{preview.body}</p>
          <div className="matrix-assets">
            {preview.assets.map((asset: string) => (
              <AssetPreview key={asset} id={asset} />
            ))}
          </div>
          <button className="button" onClick={() => setPreview(null)}>
            收起成品
          </button>
        </div>
      )}
    </Modal>
  );
}
function AssetPreview({ id }: { id: string }) {
  const a = useResource<any[]>(() => api("/assets"), []);
  const item = a.value?.find((x) => x.id === id);
  const url = "/api/v1/assets/" + id + "/download";
  return item?.mime === "video/mp4" ? (
    <video controls src={url} />
  ) : item?.mime.startsWith("image/") ? (
    <img alt={item.name} src={url} />
  ) : (
    <a href={url} target="_blank" rel="noreferrer">
      查看素材原件
    </a>
  );
}

export default function MatrixPage() {
  const [tab, setTab] = useState("accounts"),
    [profile, setProfile] = useState(""),
    [group, setGroup] = useState(""),
    [account, setAccount] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [editor, setEditor] = useState<any>(null),
    [runId, setRunId] = useState(""),
    [notice, setNotice] = useState(""),
    [qr, setQr] = useState<any>(null),
    [preview, setPreview] = useState<any>(null);
  const filters = new URLSearchParams({
    profile_id: profile,
    group_id: group,
    account_id: account,
  }).toString();
  const overview = useResource<any>(
    () => api("/matrix/overview?" + filters),
    [profile, group, account],
    10000,
  );
  const profiles = useResource<any[]>(() => api("/media-profiles"), []),
    groups = useResource<any[]>(() => api("/account-groups"), []),
    plans = useResource<any[]>(() => api("/automation-plans"), []),
    runs = useResource<any[]>(() => api("/automation-runs"), [], 10000),
    accounts = useResource<any[]>(() => api("/social-accounts"), []),
    calendar = useResource<any[]>(
      () => api("/matrix/calendar?" + filters),
      [profile, group, account, tab],
    );
  const owner = can("social.manage");
  function refresh() {
    overview.refresh();
    profiles.refresh();
    groups.refresh();
    plans.refresh();
    runs.refresh();
    accounts.refresh();
    calendar.refresh();
  }
  async function action(fn: () => Promise<any>, success = "操作已完成") {
    try {
      await fn();
      setNotice(success);
      refresh();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function login(a: any) {
    await action(async () => {
      await post("/social-accounts/" + a.id + "/login");
      const out = await post("/social-accounts/" + a.id + "/login-image");
      setQr({
        account: a,
        image: out.image || out.qr_image || out.qrcode || "",
      });
    }, "请使用对应账号扫码，随后检查身份");
  }
  const value = overview.value;
  return (
    <>
      <PageTitle
        eyebrow="MEDIA MATRIX"
        title="让每个账号，各有定位、有序运营"
        text="同机构多品牌、多平台、多账号统一编排。成品、预算与发布结果按账号记录。"
        action={
          owner ? (
            <button
              className="button primary"
              onClick={() => setEditor({ kind: "account" })}
            >
              <Plus size={15} />
              添加账号
            </button>
          ) : undefined
        }
      />
      {notice && <Notice>{notice}</Notice>}
      {overview.error && <Notice tone="error">{overview.error}</Notice>}
      <div className="matrix-summary">
        {[
          [
            "机构账号",
            value ? `${value.account_used} / ${value.account_limit}` : "—",
          ],
          ["已核实发布", value?.published ?? 0],
          ["模型费用", money(value?.cost_fen)],
          ["预占费用", money(value?.reserved_fen)],
        ].map(([label, v]) => (
          <div className="panel" key={label}>
            <small>{label}</small>
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      <div className="tabs">
        {[
          ["accounts", "矩阵账号", Users],
          ["profiles", "品牌与分组", Layers3],
          ["plans", "自动运营计划", Workflow],
          ["calendar", "发布日历", CalendarDays],
          ["runs", "任务与复盘", RefreshCw],
          ["rubrics", "评分与校准", ShieldCheck],
        ].map(([key, label, Icon]: any) => (
          <button
            key={key}
            className={"tab " + (tab === key ? "active" : "")}
            onClick={() => setTab(key)}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>
      <div className="toolbar panel matrix-filter">
        <div className="button-row">
          <select
            aria-label="筛选品牌"
            value={profile}
            onChange={(e) => {
              setProfile(e.target.value);
              setGroup("");
              setAccount("");
            }}
          >
            <option value="">全部品牌</option>
            {profiles.value?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            aria-label="筛选矩阵分组"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          >
            <option value="">全部分组</option>
            {groups.value
              ?.filter((g) => !profile || g.profile_id === profile)
              .map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
          </select>
          <select
            aria-label="筛选账号"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          >
            <option value="">全部账号</option>
            {accounts.value
              ?.filter((a) => !profile || a.profile_id === profile)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </select>
        </div>
        {owner && (
          <button
            className="button small"
            onClick={() =>
              setEditor({
                kind: "settings",
                item: {
                  monthly_budget_fen: value?.monthly_budget_fen || 0,
                  paused: value?.paused || false,
                },
              })
            }
          >
            预算与机构总开关
          </button>
        )}
      </div>
      {value?.paused && (
        <Notice>机构自动运营已暂停。已提交的生成与发布任务仍核实结果。</Notice>
      )}
      {tab === "accounts" && (
        <>
          <section className="panel">
            <div className="toolbar">
              <strong>矩阵账号 · {value?.accounts.length || 0}</strong>
              {owner && (
                <div className="button-row">
                  {["check", "pause", "resume"].map((op, index) => (
                    <button
                      className="button small"
                      disabled={!selected.length}
                      key={op}
                      onClick={() =>
                        action(async () => {
                          const result = await post("/matrix/accounts/batch", {
                            account_ids: selected,
                            operation: op,
                          });
                          const failed = result.results.filter(
                            (r: any) => r.status === "failed",
                          );
                          if (failed.length)
                            throw Error(
                              `${failed.length}个账号未完成，请分别检查连接`,
                            );
                        })
                      }
                    >
                      {["批量检查身份", "暂停所选", "恢复所选"][index]}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {value?.accounts.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {owner && <th>选择</th>}
                      <th>平台 / 账号</th>
                      <th>品牌 / 分组</th>
                      <th>登录与身份</th>
                      <th>预算 / 费用</th>
                      <th>最近结果 / 下次时段</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value.accounts.map((a: any) => (
                      <tr key={a.id}>
                        {owner && (
                          <td>
                            <input
                              type="checkbox"
                              aria-label={"选择" + a.name}
                              checked={selected.includes(a.id)}
                              onChange={() =>
                                setSelected(toggle(selected, a.id))
                              }
                            />
                          </td>
                        )}
                        <td>
                          <strong>{a.name}</strong>
                          <small className="matrix-block">
                            {platforms[a.platform]}
                          </small>
                        </td>
                        <td>
                          {profiles.value?.find((p) => p.id === a.profile_id)
                            ?.name || "待配置品牌"}
                          <small className="matrix-block">
                            {a.group_ids
                              .map(
                                (gid: string) =>
                                  groups.value?.find((g) => g.id === gid)?.name,
                              )
                              .filter(Boolean)
                              .join(" / ") || "未分组"}
                          </small>
                        </td>
                        <td>
                          <Badge value={a.paused ? "suspended" : a.status} />
                          <small className="matrix-block">
                            {a.identity_verified ? "身份已核实" : "身份待核验"}
                          </small>
                          <small className="matrix-block">
                            {a.identity_key ||
                              a.config?.identity_error ||
                              "等待连接器返回可靠账号ID"}
                          </small>
                          <details>
                            <summary>逐项能力</summary>
                            {[
                              "publish_image",
                              "publish_video",
                              "search",
                              "metrics",
                            ].map((k) => (
                              <div key={k}>
                                {
                                  (
                                    {
                                      publish_image: "图文发布",
                                      publish_video: "视频发布",
                                      search: "选题搜索",
                                      metrics: "数据回收",
                                    } as any
                                  )[k]
                                }
                                ：
                                {a.config?.verified_capabilities?.[k]
                                  ? "已验证"
                                  : "待验证 / 未接通"}
                              </div>
                            ))}
                          </details>
                        </td>
                        <td>
                          {money(a.cost_fen)}
                          <small className="matrix-block">
                            账号月预算{" "}
                            {money(a.config?.matrix?.monthly_budget_fen)}
                          </small>
                        </td>
                        <td>
                          {a.last_result ? (
                            <Badge value={a.last_result.status} />
                          ) : (
                            "暂无发布"
                          )}
                          <small className="matrix-block">
                            {date(a.next_publish_at, true)}
                          </small>
                          <small className="matrix-block">
                            归因线索 {a.attributed_leads} · 正式报名{" "}
                            {a.attributed_enrollments}
                          </small>
                        </td>
                        <td>
                          <div className="button-row">
                            {owner && (
                              <>
                                <button
                                  className="button link"
                                  onClick={() => login(a)}
                                >
                                  扫码登录
                                </button>
                                <button
                                  className="button link"
                                  onClick={() =>
                                    setEditor({ kind: "account", item: a })
                                  }
                                >
                                  配置
                                </button>
                                <button
                                  className="button link"
                                  onClick={() =>
                                    action(async () => {
                                      const out = await post(
                                        "/social-accounts/" +
                                          a.id +
                                          "/matrix-probe",
                                      );
                                      setPreview({ probe: out });
                                    }, "连接器核验已完成")
                                  }
                                >
                                  核验能力
                                </button>
                              </>
                            )}
                            {a.last_result?.external_url && (
                              <a
                                href={a.last_result.external_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                查看作品 ↗
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="先为机构建立矩阵账号"
                text="创建品牌档案，再添加并配置小红书、抖音和视频号账号。"
              />
            )}
          </section>
          {Boolean(value?.accounts.length) && (
            <div className="matrix-charts">
              <section className="panel settings-card">
                <h3>各账号已核实发布</h3>
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={value.accounts}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar
                      dataKey="published"
                      name="发布数量"
                      fill="#598458"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </section>
              <section className="panel settings-card">
                <h3>各账号模型费用（元）</h3>
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart
                    data={value.accounts.map((a: any) => ({
                      ...a,
                      cost_yuan: a.cost_fen / 100,
                    }))}
                  >
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar
                      dataKey="cost_yuan"
                      name="模型费用（元）"
                      fill="#b0b66c"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
                <p className="muted">
                  品牌共享选题费用 {money(value.shared_cost_fen)}，单独记账。
                </p>
              </section>
            </div>
          )}
        </>
      )}
      {tab === "profiles" && (
        <>
          <div className="toolbar">
            <h2>品牌内容边界</h2>
            {can("content.write") && (
              <button
                className="button primary"
                onClick={() => setEditor({ kind: "profile" })}
              >
                创建品牌档案
              </button>
            )}
          </div>
          <div className="matrix-profile-grid">
            {profiles.value?.map((p) => (
              <section className="panel settings-card" key={p.id}>
                <h3>{p.name}</h3>
                <p>{p.audience}</p>
                <p className="muted">{p.style}</p>
                <p>
                  {p.knowledge_ids.length}份已确认资料 · {p.asset_ids.length}
                  份授权素材 · v{p.version}
                </p>
                {can("content.write") && (
                  <button
                    className="button small"
                    onClick={() => setEditor({ kind: "profile", item: p })}
                  >
                    编辑品牌
                  </button>
                )}
              </section>
            ))}
          </div>
          <div className="toolbar space-top">
            <h2>矩阵分组</h2>
            {owner && (
              <button
                className="button"
                disabled={!profiles.value?.length}
                onClick={() => setEditor({ kind: "group" })}
              >
                创建分组
              </button>
            )}
          </div>
          <div className="matrix-profile-grid">
            {groups.value?.map((g) => (
              <section key={g.id} className="panel settings-card">
                <h3>{g.name}</h3>
                <p>
                  {profiles.value?.find((p) => p.id === g.profile_id)?.name} ·{" "}
                  {g.account_ids.length}个账号
                </p>
                {owner && (
                  <button
                    className="button small"
                    onClick={() => setEditor({ kind: "group", item: g })}
                  >
                    编辑分组
                  </button>
                )}
              </section>
            ))}
          </div>
        </>
      )}
      {tab === "plans" && (
        <section className="panel">
          <div className="toolbar">
            <strong>固定流程 · 参数可配置</strong>
            {can("campaign.write") && (
              <button
                className="button primary"
                disabled={!profiles.value?.length}
                onClick={() => setEditor({ kind: "plan" })}
              >
                创建运营计划
              </button>
            )}
          </div>
          {plans.value?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>计划 / 品牌</th>
                    <th>模式与频次</th>
                    <th>预算</th>
                    <th>授权状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.value
                    .filter((p) => !profile || p.profile_id === profile)
                    .map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                          <small className="matrix-block">
                            {
                              profiles.value?.find((x) => x.id === p.profile_id)
                                ?.name
                            }{" "}
                            · v{p.version}
                          </small>
                          {p.last_error && <small>{p.last_error}</small>}
                        </td>
                        <td>
                          {p.spec.mode === "matrix" ? "母题矩阵" : "独立运营"}
                          <small className="matrix-block">
                            周
                            {p.spec.weekdays
                              .map((d: number) => dayNames[d])
                              .join("、")}{" "}
                            {p.spec.times.join(" / ")}
                          </small>
                        </td>
                        <td>
                          单次 {money(p.spec.run_budget_fen)}
                          <small className="matrix-block">
                            每日 {money(p.spec.daily_budget_fen)}
                          </small>
                        </td>
                        <td>
                          <Badge
                            value={p.enabled ? "active" : "draft"}
                            label={
                              p.enabled
                                ? "已启用"
                                : p.authorized_by
                                  ? "已授权试运行"
                                  : "等待负责人授权"
                            }
                          />
                          <small className="matrix-block">
                            {p.spec.review === "auto" ? "自动发布" : "逐条审核"}
                          </small>
                        </td>
                        <td>
                          <div className="button-row">
                            {can("campaign.write") && (
                              <>
                                <button
                                  className="button link"
                                  onClick={() =>
                                    setEditor({ kind: "plan", item: p })
                                  }
                                >
                                  编辑
                                </button>
                                <button
                                  className="button link"
                                  onClick={() =>
                                    action(
                                      async () =>
                                        setPreview(
                                          await api(
                                            "/automation-plans/" +
                                              p.id +
                                              "/preview",
                                          ),
                                        ),
                                      "目标账号与预算预览已生成",
                                    )
                                  }
                                >
                                  预览
                                </button>
                                <button
                                  className="button small"
                                  onClick={() =>
                                    action(async () => {
                                      const run = await post(
                                        "/automation-runs",
                                        {
                                          plan_id: p.id,
                                          request_id: uid(),
                                          trial: true,
                                        },
                                      );
                                      setRunId(run.id);
                                    }, "已创建试运行，不会发布")
                                  }
                                >
                                  试运行
                                </button>
                              </>
                            )}
                            {owner && (
                              <>
                                {!p.authorized_by && (
                                  <button
                                    className="button small"
                                    onClick={() =>
                                      action(() =>
                                        post(
                                          "/automation-plans/" +
                                            p.id +
                                            "/authorize",
                                          { enabled: true, version: p.version },
                                        ),
                                      )
                                    }
                                  >
                                    授权试运行
                                  </button>
                                )}
                                <button
                                  className="button small"
                                  onClick={() =>
                                    action(() =>
                                      post(
                                        "/automation-plans/" +
                                          p.id +
                                          "/enabled",
                                        {
                                          enabled: !p.enabled,
                                          version: p.version,
                                        },
                                      ),
                                    )
                                  }
                                >
                                  {p.enabled ? "暂停计划" : "启用计划"}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty text="先配置品牌、账号及预算，再创建第一个计划。" />
          )}
        </section>
      )}
      {tab === "runs" && (
        <section className="panel">
          <div className="toolbar">
            <strong>运行记录 · 每个账号独立完成</strong>
            <button className="button small" onClick={runs.refresh}>
              刷新
            </button>
          </div>
          {runs.value?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>计划</th>
                    <th>时间</th>
                    <th>状态</th>
                    <th>账号进度</th>
                    <th>查看</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.value
                    .filter(
                      (r) =>
                        (!profile || r.snapshot.profile.id === profile) &&
                        (!account ||
                          r.tasks.some((t: any) => t.account_id === account)) &&
                        (!group ||
                          r.tasks.some((t: any) =>
                            groups.value
                              ?.find((g) => g.id === group)
                              ?.account_ids.includes(t.account_id),
                          )),
                    )
                    .map((r) => (
                      <tr key={r.id}>
                        <td>
                          {r.snapshot.name}
                          <small className="matrix-block">
                            {r.trial ? "试运行" : "正式运行"} · v
                            {r.plan_version}
                          </small>
                        </td>
                        <td>{date(r.created_at, true)}</td>
                        <td>
                          <Badge value={r.paused ? "suspended" : r.status} />
                        </td>
                        <td>
                          {
                            r.tasks.filter((t: any) =>
                              [
                                "trial_ready",
                                "succeeded",
                                "waiting_metrics",
                              ].includes(t.status),
                            ).length
                          }{" "}
                          / {r.tasks.length}
                        </td>
                        <td>
                          <button
                            className="button link"
                            onClick={() => setRunId(r.id)}
                          >
                            任务详情 ↗
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty text="试运行或定时执行后，会在这里显示真实任务状态。" />
          )}
        </section>
      )}
      {tab === "rubrics" && (
        <RubricsPage
          key={profile}
          profileId={profile}
          role={owner ? "owner" : "content_ops"}
        />
      )}
      {tab === "calendar" && (
        <section className="panel">
          <div className="toolbar">
            <strong>未来14天 · 中国时间</strong>
            <small>计划时段为预排，实际发布取决于生成、审核及账号状态。</small>
          </div>
          {calendar.value?.length ? (
            <div className="matrix-calendar">
              {calendar.value.map((event: any, index) => (
                <div className="matrix-calendar-event" key={index}>
                  <CalendarDays size={18} />
                  <strong>{date(event.at, true)}</strong>
                  <span>
                    {
                      accounts.value?.find((a) => a.id === event.account_id)
                        ?.name
                    }
                  </span>
                  <span>{event.name || "已创建发布任务"}</span>
                  <Badge
                    value={event.status}
                    label={event.type === "plan_slot" ? "计划时段" : undefined}
                  />
                  {event.external_url && (
                    <a
                      href={event.external_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      作品 ↗
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="暂无发布时段"
              text="负责人启用计划后显示预排；已创建的发布任务会显示实际状态。"
            />
          )}
        </section>
      )}
      {editor && (
        <MatrixEditor
          key={editor.kind + (editor.item?.id || "")}
          kind={editor.kind}
          item={editor.item}
          profiles={profiles.value || []}
          groups={groups.value || []}
          accounts={accounts.value || []}
          close={() => setEditor(null)}
          saved={refresh}
        />
      )}
      {runId && (
        <RunDetail
          id={runId}
          close={() => {
            setRunId("");
            refresh();
          }}
        />
      )}
      {qr && (
        <Modal
          title={qr.account.name + " · 独立账号登录"}
          close={() => setQr(null)}
        >
          <div className="form-body">
            {qr.image ? (
              <img
                alt="该账号的登录二维码"
                src={qr.image}
                style={{ maxWidth: "100%" }}
              />
            ) : (
              <Notice>连接器暂未提供二维码，请检查发布节点。</Notice>
            )}
            <button
              className="button primary"
              onClick={() =>
                action(async () => {
                  const result = await post("/matrix/accounts/batch", {
                    account_ids: [qr.account.id],
                    operation: "check",
                  });
                  if (result.results[0]?.identity_verified) setQr(null);
                  else
                    throw Error("登录身份仍待核验，请确认对应账号及连接器能力");
                })
              }
            >
              扫码后检查身份
            </button>
          </div>
        </Modal>
      )}
      {preview && (
        <Modal title="矩阵执行预览" close={() => setPreview(null)}>
          <div className="form-body">
            {preview.probe ? (
              <Notice>
                {preview.probe.reason} · 身份
                {preview.probe.identity_verified ? "已验证" : "待验证"}
              </Notice>
            ) : (
              <p>
                目标账号 {preview.account_count} 个 · 本次预算上限{" "}
                {money(preview.budget_ceiling_fen)}
              </p>
            )}
            {preview.accounts?.map((a: any) => (
              <p key={a.id}>
                {platforms[a.platform]} · {a.name} ·{" "}
                {a.form === "video" ? "视频" : "图文"}
              </p>
            ))}
            <Notice>{preview.note}</Notice>
          </div>
        </Modal>
      )}
    </>
  );
}
