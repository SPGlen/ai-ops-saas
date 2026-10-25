import { chromium, expect } from "@playwright/test";
import {mkdir,writeFile} from "node:fs/promises";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"../..");
const output=path.join(root,".local/delivery/showcase");await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:output,size:{width:1440,height:900}},locale:"zh-CN"});
const page=await context.newPage();const video=page.video();const steps=[];const errors=[];page.on("pageerror",e=>errors.push(e.message));
async function scene(label,ms=2600){
 await page.evaluate(label=>{
  let el=document.getElementById("showcase-recording-caption");if(!el){el=document.createElement("div");el.id="showcase-recording-caption";el.style.cssText="position:fixed;right:22px;bottom:16px;z-index:9999;max-width:65vw;background:#173e32ee;color:#f3f7e9;padding:12px 20px;border-radius:10px;font:14px Microsoft YaHei,system-ui;box-shadow:0 5px 20px #183f3322;pointer-events:none";document.body.append(el)}el.textContent=label;
 },label);
 steps.push(label);await page.waitForTimeout(ms);
}
async function nav(name){await page.getByRole("link",{name,exact:true}).first().click();await page.waitForTimeout(550);}
try{
 await page.goto("http://127.0.0.1:8188/");await expect(page.getByRole("button",{name:"机构负责人",exact:true})).toBeVisible();
 await scene("01 / 选择岗位进入 · 虚构演示资料，权限由真实后端校验");
 await page.getByRole("button",{name:"机构负责人",exact:true}).click();await expect(page.getByRole("heading",{name:"一个工作台，看清一家机构的经营"})).toBeVisible();
 await scene("02 / 负责人总览 · 招生、学员、财务与内容运营在同一工作台",3200);
 await page.getByText("每笔收支，汇成经营趋势",{exact:true}).scrollIntoViewIfNeeded();
 await scene("03 / 经营结果 · 转化、收支与30%流失预警均由示例记录计算",3200);
 await nav("招生线索");await scene("04 / 招生跟进 · 表格导入、试听预约、负责人分配和状态跟进",3200);
 await nav("学员档案");await page.getByRole("button").filter({hasText:"启蒙创想 · 周六上午班"}).first().click();
 await scene("05 / 班级档案 · 家长联系信息、课时与出勤相互关联",3000);
 await page.locator(".class-roster tbody button").first().click();await expect(page.getByRole("dialog")).toBeVisible();await scene("06 / 学员详情 · 多家长、报名、课时流水与出勤历史",3000);
 await page.getByRole("dialog").getByRole("button",{name:"关闭",exact:true}).click();
 await nav("财务台账");await scene("07 / 财务可视化 · 实收、退款、净收和已确认费用",3200);
 await page.locator("#financial-transactions tbody tr").filter({hasText:"教室场地费"}).getByRole("button",{name:"查看票据与详情",exact:true}).click();
 await expect(page.getByRole("dialog").getByText("票据原件",{exact:true})).toBeVisible();await scene("08 / 点击票据 · 从图表向下查看费用原件与核对记录",3200);
 await page.getByRole("dialog").getByRole("button",{name:"关闭",exact:true}).click();
 await page.locator("#financial-transactions tbody tr").filter({hasText:"退款"}).first().getByRole("button",{name:"查看票据与详情",exact:true}).click();
 await expect(page.getByRole("dialog").getByText("退款时的课时快照",{exact:true})).toBeVisible();await scene("09 / 退读退费 · 保留原因、已上与未上课时的当时快照",3200);
 await page.getByRole("dialog").getByRole("button",{name:"关闭",exact:true}).click();
 await nav("经营周报 / 月报");await page.getByRole("button",{name:"月报",exact:true}).click();await scene("10 / 经营月报 · 招生、退读、出勤、课返与财务自动汇总",3500);
 await nav("自媒体矩阵");await scene("11 / 矩阵账号 · 同平台多账号、品牌分组与预算独立管理",3200);
 await page.getByRole("button",{name:"品牌与分组",exact:true}).click();await scene("12 / 品牌档案 · 课程事实与素材分品牌维护，账号当前未连接",2800);
 await page.getByRole("link",{name:"演示总览",exact:true}).click();await page.getByRole("button",{name:"播放视频案例",exact:false}).click();
 const media=page.locator("video");await media.scrollIntoViewIfNeeded();await media.evaluate(el=>el.play());await scene("13 / 成品预览 · 预置文案与15秒无声程序合成，未调用模型或发布",4500);
 await nav("成员与授权");await scene("14 / 负责人授权 · 一人可以兼任多个岗位",3200);
 await page.getByLabel("切换演示岗位").selectOption("teacher1.qinghe@zhiying.example");await expect(page.getByRole("link",{name:"财务台账",exact:true})).toHaveCount(0);
 await nav("学员档案");await scene("15 / 切换授课岗位 · 仅显示任教班级与学员，财务和内容入口隐藏",3500);
 await page.getByLabel("切换演示岗位").selectOption("owner.qinghe@zhiying.example");await expect(page.getByRole("heading",{name:"一个工作台，看清一家机构的经营"})).toBeVisible();await scene("知营 · 企业演示完成 / 真实模型和平台账号联调属于后续接入",3200);
 if(errors.length)throw new Error(errors.join(";"));
}finally{
 await context.close();
 const source=await video.path();await video.saveAs(path.join(output,"企业演示录像.webm"));
 await browser.close();
 await writeFile(path.join(output,"recording.json"),JSON.stringify({steps,source,errors,completed:steps.length===16,synthetic_data:true,model_calls:false,real_publish:false},null,2));
}
console.log("Enterprise walkthrough recorded with "+steps.length+" scenes.");
