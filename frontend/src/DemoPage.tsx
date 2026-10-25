import React, { useState } from "react";
import { ArrowUpRight, CheckCircle2, ShieldCheck, PlayCircle, Users, Wallet, CalendarDays, BarChart3, Layers, ChevronRight, FileCheck2, AlertTriangle } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, BarChart, Bar } from "recharts";
import { api, post, can, money, date, SessionInfo, roles } from "./api";
import { useResource, Loading, Notice, PageTitle } from "./ui";

const roleOrder = ["owner", "admissions1", "teacher1", "academic", "finance", "content", "combined", "scheduler", "revenue"];
function primaryAccounts(accounts: any[]) {
  return accounts.filter(a => !a.platform_admin && roleOrder.some(r => a.email.startsWith(r + ".qinghe@"))).sort((a,b) => roleOrder.indexOf(a.email.split(".")[0]) - roleOrder.indexOf(b.email.split(".")[0]));
}
export function DemoLoginChoices({ accounts, ready }: { accounts: any[]; ready: () => void }) {
  const [busy,setBusy]=useState(""),[error,setError]=useState("");
  async function enter(a:any) {
    setBusy(a.email);setError("");
    try { await post("/auth/login",{email:a.email,password:a.password}); location.hash="demo"; ready(); }
    catch(e) { setError((e as Error).message); } finally {setBusy("");}
  }
  return <section className="demo-login-panel" aria-label="企业演示入口">
    <div className="demo-kicker"><span className="demo-dot"/>企业体验 · 独立演示环境</div>
    <h3>选一个岗位，直接体验</h3>
    <p>虚构机构资料，正常登录与权限校验。可录入、核对、查看报表。</p>
    <div className="demo-login-roles">{primaryAccounts(accounts).slice(0,7).map(a => <button type="button" key={a.email} className={"button "+(a.roles.includes("owner")?"primary":"")} disabled={!!busy} onClick={()=>enter(a)}>{busy===a.email?"正在进入…":a.roles.map((r:string)=>roles[r]).join(" + ")}<ArrowUpRight size={15}/></button>)}</div>
    {error&&<Notice tone="error">{error}</Notice>}
    <small>请勿填写真实儿童资料、账号密钥或付款信息。真实 AI 调用与外部发送已关闭。</small>
  </section>;
}
export function DemoModeBar({ me, ready }: {me:SessionInfo;ready:()=>void}) {
  const accounts=useResource<any[]>(()=>api("/auth/demo-accounts"),[]);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const choices=primaryAccounts(accounts.value||[]);
  return <><div className="demo-mode-bar">
    <div><span className="demo-dot"/><strong>企业演示</strong><span>虚构业务资料 · 真实权限与计算 · 外部发送关闭</span></div>
    <div><a className="button small" href="#demo">演示总览</a><select aria-label="切换演示岗位" value={choices.some(a=>a.email===me.user.email)?me.user.email:""} disabled={busy} onChange={async e=>{
      const a=choices.find(a=>a.email===e.target.value);if(!a)return;setBusy(true);setError("");
      try {await post("/auth/logout");await post("/auth/login",{email:a.email,password:a.password});location.hash="demo";ready();}
      catch(e){setError((e as Error).message);ready();}finally{setBusy(false);}
    }}><option value="" disabled>选择岗位</option>{choices.map(a=><option key={a.email} value={a.email}>{a.roles.map((r:string)=>roles[r]).join(" + ")}</option>)}</select></div>
  </div>{error&&<Notice tone="error">{error}</Notice>}</>;
}
const routeSteps=[
  {permission:"lead.read",hash:"leads",title:"招生与转化",copy:"从一张招生表，到试听、跟进和报名。",icon:Users},
  {permission:"student.read",hash:"students",title:"班级与学员",copy:"按班查看学员、家长及课时记录。",icon:CalendarDays},
  {permission:"finance.read",hash:"finance",title:"财务与票据",copy:"从经营图表，进入流水与票据原件。",icon:Wallet},
  {permission:"reports.read",hash:"reports",title:"周报与月报",copy:"转化、流失、出勤和家长反馈集中汇总。",icon:BarChart3},
  {permission:"social.read",hash:"matrix",title:"自媒体矩阵",copy:"多品牌、多账号、预算与周期计划。",icon:Layers},
  {permission:"members.manage",hash:"authorization",title:"岗位与授权",copy:"一人多岗，由负责人配置功能权限。",icon:ShieldCheck},
];
const pct=(v:any)=>v==null?"暂无数据":Number(v).toFixed(1)+"%";
export default function DemoPage({me}:{me:SessionInfo}) {
  const resource=useResource<any>(()=>api("/demo/showcase"),[me.tenant_id,me.authz_version],15000);
  const [asset,setAsset]=useState<string>("");
  if(resource.loading)return <Loading/>;
  if(resource.error)return <Notice tone="error">{resource.error}</Notice>;
  const data=resource.value, monthly=data.monthly||{},weekly=data.weekly||{},m=monthly.metrics||{},w=weekly.metrics||{},finance=monthly.finance||monthly.revenue, totals=finance?.totals;
  const cards:any[]=[];
  if(data.counts.lead!=null)cards.push([Users,"可见招生线索",data.counts.lead,"leads"]);
  if(data.counts.student!=null)cards.push([CalendarDays,"可见学员档案",data.counts.student,"students"]);
  if(totals)cards.push([Wallet,"本月净收款",money(totals.net_fen),can("finance.read")?"finance":"revenue"]);
  if(m.attendance_rate!=null)cards.push([CheckCircle2,"本月出勤率",pct(m.attendance_rate),"reports"]);
  if(data.matrix)cards.push([Layers,"矩阵账号",data.matrix.accounts,"matrix"]);
  const assets=data.assets||[],selected=assets.find((a:any)=>a.id===asset)||assets[0];
  const steps=routeSteps.filter(s=>can(s.permission));
  return <div className="demo-showcase">
    <PageTitle eyebrow="ZHIYING · ENTERPRISE DEMO" title="一个工作台，看清一家机构的经营" text="从招生到交付，从每笔收支到每周经营回顾。选择入口，即可查看与操作对应业务。"/>
    <section className="demo-hero">
      <div><div className="demo-kicker"><span className="demo-dot"/>为教育机构创业者设计</div><h2>把日常事务串起来，<br/>把精力留给课程与增长。</h2><p>负责人统筹全局，员工按授权协作。一人可以兼任多个岗位，每一笔记录都能向下查看。</p><div className="button-row"><a href={"#"+(steps[0]?.hash||"dashboard")} className="button primary">开始体验 <ArrowUpRight size={17}/></a><a href="#dashboard" className="button">查看我的工作台</a></div></div>
      <div className="demo-hero-facts"><div><ShieldCheck size={23}/><strong>机构独立，岗位协作</strong><span>{me.roles.map(r=>roles[r]).join(" / ")}视角</span></div><div><FileCheck2 size={23}/><strong>经营数字可追溯</strong><span>图表关联订单、收退款与原件</span></div><div><CalendarDays size={23}/><strong>周报月报自动汇总</strong><span>本例由虚构业务记录实际计算</span></div></div>
    </section>
    <div className="stats-grid">{cards.map(([Icon,label,value,hash])=><a href={"#"+hash} className="stat" key={label}><div className="stat-label"><span>{label}</span><Icon size={18}/></div><div className="stat-value">{value}</div><small>查看关联记录 <ArrowUpRight size={12}/></small></a>)}</div>
    <section className="panel"><div className="demo-section-title"><div><h2>沿着一条业务线，体验完整工作</h2><p>可见入口由当前岗位决定，切换岗位后菜单与数据范围一起变化。</p></div><span className="badge neutral">{steps.length} 个可见入口</span></div><div className="demo-journey">{steps.map((s,j)=><a key={s.hash} href={"#"+s.hash} className="demo-journey-card"><span className="demo-step-index">0{j+1}</span><s.icon size={23}/><h3>{s.title}</h3><p>{s.copy}</p><span>进入体验 <ChevronRight size={14}/></span></a>)}</div></section>
    <div className="demo-two-columns">
      {totals&&<section className="panel"><div className="demo-section-title"><div><h2>每笔收支，汇成经营趋势</h2><p>本月实收、退款与净收；点击查看财务明细。</p></div><a href={can("finance.read")?"#finance":"#revenue"} className="button small">查看明细 ↗</a></div><div className="demo-chart"><ResponsiveContainer width="100%" height={240}><AreaChart data={(finance.chart||[]).map((r:any)=>({...r,net_yuan:r.net_fen/100,received_yuan:r.received_fen/100}))}><defs><linearGradient id="demoRevenue" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4e815a" stopOpacity={.3}/><stop offset="100%" stopColor="#4e815a" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 5" vertical={false}/><XAxis dataKey="date" tickFormatter={v=>v.slice(5)} tick={{fontSize:11}}/><YAxis tick={{fontSize:11}}/><Tooltip formatter={(v:any)=>["¥"+Number(v).toLocaleString(),"净收款"]}/><Area isAnimationActive={false} dataKey="net_yuan" type="monotone" stroke="#3c7655" fill="url(#demoRevenue)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div><div className="demo-inline-stats"><div><span>实收</span><strong>{money(totals.received_fen)}</strong></div><div><span>退款</span><strong>{money(totals.refund_fen)}</strong></div>{totals.expense_fen!=null&&<div><span>已确认费用</span><strong>{money(totals.expense_fen)}</strong></div>}</div></section>}
      {weekly.metrics&&<section className="panel"><div className="demo-section-title"><div><h2>这一周，招生进行到哪里</h2><p>{weekly.period} 起的同批线索累计转化</p></div><a href="#reports" className="button small">查看周报 ↗</a></div><div className="demo-inline-stats demo-conversion"><div><span>新增线索</span><strong>{w.new_leads??"—"}</strong></div><div><span>线索转化率</span><strong>{pct(w.lead_conversion_rate)}</strong></div><div><span>试听转化率</span><strong>{pct(w.trial_conversion_rate)}</strong></div></div><div className="demo-summary">{(weekly.summary||[]).slice(0,4).map((line:string,j:number)=><p key={j}><CheckCircle2 size={15}/>{line}</p>)}</div><small className="demo-muted">转化口径、分母及历史快照可在经营报表中查看；AI 润色需另接模型。</small></section>}
    </div>
    {m.attrition_rate!=null&&can("tenant.manage")&&<section className={"demo-alert "+(m.attrition_rate>=30?"attention":"")}><AlertTriangle size={23}/><div><strong>{m.attrition_rate>=30?"经营异常示例：本月流失率已达到预警线":"本月流失情况"}</strong><p>退读 {m.withdrawn_students} 人 / 在读基数 {m.population} 人 = {pct(m.attrition_rate)}。原因与课时快照可向下核对。本演示不发送企业微信消息。</p></div><a href="#operations" className="button small">查看预警 ↗</a></section>}
    {assets.length>0&&<section className="panel"><div className="demo-section-title"><div><h2>从计划配置，到看得见的内容成品</h2><p>预置图文案例与真实程序合成视频；没有模拟发布成功或平台数据。</p></div><a href="#matrix" className="button small">查看矩阵计划 ↗</a></div><div className="demo-media-grid"><div className="demo-media-preview">{selected?.mime.startsWith("video/")?<video controls preload="metadata" src={"/api/v1/assets/"+selected.id+"/download"} aria-label="程序合成演示视频"/>:selected&&<img src={"/api/v1/assets/"+selected.id+"/download"} alt={selected.name}/>}</div><div className="demo-media-copy"><span className="demo-kicker">内容运营 · 授权后执行</span><h3>同一母题，按账号分别创作</h3><p>选题、文案、图片与视频、审核、发布和复盘分别留痕。负责人控制账号绑定、预算和自动发布策略。</p><div className="demo-inline-stats"><div><span>品牌档案</span><strong>{data.matrix.brands}</strong></div><div><span>矩阵账号</span><strong>{data.matrix.accounts}</strong></div><div><span>周期计划</span><strong>{data.matrix.plans}</strong></div></div><div className="demo-asset-options">{assets.map((a:any,j:number)=><button className={"button small "+(selected?.id===a.id?"primary":"")} key={a.id} onClick={()=>setAsset(a.id)}>{a.mime.startsWith("video/")?<><PlayCircle size={16}/>播放视频案例</>:"图文案例 "+(j+1)}</button>)}</div><Notice>这里展示预置内容与排版结果。真实 AI 生成、扫码登录、发布回执和平台指标，需要接入供应商及机构账号后验收。</Notice></div></div></section>}
    <section className="demo-footer-note"><ShieldCheck size={17}/><p>独立演示数据库 · 资料均为虚构 · 外部调用关闭。准备时间：{date(data.seeded_at,true)}；统计刷新：{date(data.as_of,true)}。现场可操作，重置脚本可恢复基线。</p></section>
  </div>;
}
