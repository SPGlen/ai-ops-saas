import React, { useState, useEffect, useRef } from "react";
import {
  X,
  LoaderCircle,
  Inbox,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { statuses } from "./api";
export function Badge({ value, label }: { value: string; label?: string }) {
  const tone = [
    "succeeded",
    "connected",
    "won",
    "confirmed",
    "approved",
    "active",
    "completed",
    "sent",
  ].includes(value)
    ? "good"
    : ["failed", "unknown", "suspended", "lost"].includes(value)
      ? "bad"
      : ["draft", "new", "unconfigured", "cancelled"].includes(value)
        ? "neutral"
        : "warn";
  return (
    <span className={"badge " + tone}>
      <i />
      {label || statuses[value] || value}
    </span>
  );
}
export function Empty({
  title = "这里还没有记录",
  text = "添加第一条记录，开始安排今天的工作。",
  action,
}: {
  title?: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Inbox size={25} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={23} />
      <span>正在整理工作台…</span>
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    document.addEventListener("keydown", f);
    return () => document.removeEventListener("keydown", f);
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon-button" aria-label="关闭" onClick={close}>
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className={"notice " + tone}>
      {tone === "success" ? (
        <CheckCircle2 size={17} />
      ) : (
        <AlertCircle size={17} />
      )}
      <div>{children}</div>
    </div>
  );
}
export function useResource<T>(
  load: () => Promise<T>,
  deps: unknown[] = [],
  interval = 0,
) {
  const [value, setValue] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  async function refresh() {
    try {
      setValue(await load());
      setError("");
    } catch (e) {
      setValue(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    load()
      .then((v) => {
        if (active) {
          setValue(v);
          setError("");
        }
      })
      .catch((e) => {
        if (active) {
          setValue(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const id = interval
      ? setInterval(() => {
          if (active) void refresh();
        }, interval)
      : undefined;
    const live = () => {
      if (active) void refresh();
    };
    window.addEventListener("ops-refresh", live);
    return () => {
      window.removeEventListener("ops-refresh", live);
      active = false;
      if (id) clearInterval(id);
    };
  }, deps);
  return { value, error, loading, refresh, setValue };
}
export function PageTitle({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function AsyncButton({
  children,
  action,
  className = "button primary",
}: {
  children: React.ReactNode;
  action: () => Promise<unknown>;
  className?: string;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <>
      <button
        className={className}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await action();
            setError("");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? <LoaderCircle size={16} className="spin" /> : null}
        {children}
      </button>
      {error && <small className="inline-error">{error}</small>}
    </>
  );
}
