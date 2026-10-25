import React, { useEffect, useState } from "react";
import { api, post, uid } from "./api";
import { Field, Notice, Badge, useResource } from "./ui";

export function AIRunResult({ id }: { id: string }) {
  const [watch, setWatch] = useState(true);
  const data = useResource<any>(
    () => api("/runs/" + id),
    [id, watch],
    watch ? 2000 : 0,
  );
  useEffect(() => {
    if (
      data.value &&
      !["queued", "processing", "retrying"].includes(data.value.status)
    )
      setWatch(false);
  }, [data.value]);
  if (data.error) return <Notice tone="error">{data.error}</Notice>;
  if (!data.value) return <p>正在读取模型任务…</p>;
  const r = data.value;
  return (
    <div aria-live="polite" className="space-top">
      <Badge value={r.status} />
      {r.error && <Notice tone="error">{r.error}</Notice>}
      {r.output?.message && <p>{r.output.message}</p>}
      {r.output?.summary && (
        <>
          <p style={{ whiteSpace: "pre-wrap" }}>{r.output.summary}</p>
          {r.output.actions?.length > 0 && (
            <>
              <strong>建议行动</strong>
              <ul>
                {r.output.actions.map((x: string, j: number) => (
                  <li key={j}>{x}</li>
                ))}
              </ul>
            </>
          )}
          {r.output.limitations?.length > 0 && (
            <Notice>{r.output.limitations.join("；")}</Notice>
          )}
        </>
      )}
      <small>模型输出与费用可在任务和用量记录中核对。</small>
    </div>
  );
}

export function AISettingsPanel() {
  const data = useResource<any>(() => api("/ai-settings"), []);
  const [draft, setDraft] = useState<any>(null),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [probe, setProbe] = useState("");
  const v = draft || data.value?.settings;
  const set = (key: string, value: any) => setDraft({ ...v, [key]: value });
  if (data.error)
    return (
      <section className="panel settings-card">
        <Notice tone="error">{data.error}</Notice>
      </section>
    );
  if (!v) return null;
  return (
    <section className="panel settings-card" aria-label="AI 模型配置">
      <h2>AI 模型配置</h2>
      <p>
        负责人选择文字智能体的供应商、费用来源及预算。图片、视频、配音、向量检索、视觉评分与独立复核继续使用百炼。矩阵任务的费用来源以计划配置为准。
      </p>
      {message && <Notice>{message}</Notice>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMessage("");
          try {
            const result = await api("/ai-settings", {
              method: "PUT",
              body: JSON.stringify(v),
            });
            data.setValue(result);
            setDraft(null);
            setProbe("");
            setMessage("AI 配置已保存，仅影响新任务；排队任务保留原模型。");
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="文字智能体供应商">
          <select
            value={v.provider}
            onChange={(e) =>
              setDraft({
                ...v,
                provider: e.target.value,
                model:
                  e.target.value === "deepseek"
                    ? "deepseek-flash"
                    : "qwen-plus",
              })
            }
          >
            <option value="aliyun">阿里云百炼</option>
            <option value="deepseek">DeepSeek 官方 API</option>
          </select>
        </Field>
        {v.provider === "deepseek" && (
          <>
            <Field label="DeepSeek 模型">
              <select
                value={v.model}
                onChange={(e) => {
                  const pro = e.target.value === "deepseek-v4-pro";
                  setDraft({
                    ...v,
                    model: e.target.value,
                    input_million_fen: pro ? 900 : 200,
                    output_million_fen: pro ? 2700 : 800,
                    cached_million_fen: pro ? 30 : 4,
                  });
                }}
              >
                <option value="deepseek-flash">DeepSeek Flash</option>
                <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
              </select>
            </Field>
            <Field label="输出 Token 上限">
              <input
                type="number"
                min={256}
                max={8000}
                step={1}
                value={v.max_tokens}
                onChange={(e) => set("max_tokens", Number(e.target.value))}
                required
              />
            </Field>
            <label className="check">
              <input
                type="checkbox"
                checked={v.thinking}
                onChange={(e) => set("thinking", e.target.checked)}
              />
              启用思考模式（会增加用量与等待时间）
            </label>
          </>
        )}
        <Field label="文字任务默认费用来源">
          <select
            value={v.funding}
            onChange={(e) => set("funding", e.target.value)}
          >
            <option value="platform">平台额度</option>
            <option value="byok">机构自带 Key</option>
          </select>
        </Field>
        {v.provider === "deepseek" && v.funding === "byok" && (
          <>
            <p>
              下列单价用于预算与费用估算，初值按忙时配置，可按供应商账单更新。
            </p>
            <div className="form-grid">
              {[
                ["input", "输入"],
                ["output", "输出"],
                ["cached", "缓存命中输入"],
              ].map(([k, label]) => (
                <Field key={k} label={label + "估算价（元／百万Token）"}>
                  <input
                    type="number"
                    min={k === "cached" ? 0 : 0.01}
                    step="0.01"
                    max={10000}
                    value={v[k + "_million_fen"] / 100}
                    onChange={(e) =>
                      set(
                        k + "_million_fen",
                        Math.round(Number(e.target.value) * 100),
                      )
                    }
                    required
                  />
                </Field>
              ))}
            </div>
          </>
        )}
        {v.provider === "deepseek" && v.funding === "platform" && (
          <Notice>
            平台管理员需配置平台 DeepSeek
            Key、对应模型计价和机构额度。不会自动使用机构 Key。
          </Notice>
        )}
        <div className="button-row space-top">
          <button className="button primary" disabled={busy}>
            保存 AI 配置
          </button>
          <button
            type="button"
            className="button"
            disabled={busy || !!draft}
            onClick={async () => {
              setBusy(true);
              setMessage("");
              try {
                const r = await post("/ai-settings/test", {
                  request_id: uid(),
                });
                setProbe(r.id);
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            测试连接
          </button>
        </div>
      </form>
      <p>
        {draft
          ? "请先保存配置，再测试连接。"
          : data.value?.credential_configured
            ? "所选费用来源已配置凭证，实际连通性以测试结果为准。"
            : "所选费用来源尚未配置凭证。机构 Key 请在服务连接中添加。"}{" "}
        测试连接会产生少量真实用量。
      </p>
      {probe && <AIRunResult key={probe} id={probe} />}
    </section>
  );
}

export function AIReportSummary({ reportId }: { reportId: string }) {
  const [run, setRun] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <section className="space-top">
      <h3>AI 经营解读</h3>
      <p>
        仅发送当前版本的汇总数字；不发送学员、家长、原始反馈或票据明细。解读单独保存，报表数字保持原版本。
      </p>
      <button
        className="button"
        disabled={busy || !!run}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            const r = await post("/runs", {
              kind: "report_summary",
              request_id: uid(),
              input: { report_id: reportId },
            });
            setRun(r.id);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        生成 AI 解读
      </button>
      {error && <Notice tone="error">{error}</Notice>}
      {run && <AIRunResult key={run} id={run} />}
    </section>
  );
}
