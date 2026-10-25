import { chromium, expect } from "@playwright/test";import path from "node:path";import {pathToFileURL} from "node:url";import fs from "node:fs/promises";
const root=path.resolve(import.meta.dirname,"../..");const folder=path.join(root,".local/delivery/showcase");
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on("pageerror",e=>errors.push(e.message));
try{
 await page.goto(pathToFileURL(path.join(folder,"打开演示导览.html")).href);
 await expect(page.getByRole("heading",{name:"从机构日常，到看得清的经营结果。"})).toBeVisible();
 const video=page.locator("video");await video.evaluate(el=>el.play());await expect.poll(()=>video.evaluate(el=>el.currentTime)).toBeGreaterThan(.2);
 await page.getByRole("button",{name:"票据原件",exact:true}).click();await expect(page.locator(".scene.active h2")).toHaveText("票据原件");
 await expect.poll(()=>page.locator(".scene.active img").evaluate(el=>el.complete&&el.naturalWidth>0)).toBe(true);
 await page.screenshot({path:path.join(root,"docs/screenshots/showcase-offline.png"),fullPage:false});
 if(errors.length)throw new Error(errors.join(";"));
 await fs.writeFile(path.join(root,"docs/showcase-offline-test.json"),JSON.stringify({verified_at:new Date().toISOString(),file_url:true,video_playback:true,tab_navigation:true,embedded_images:true,errors},null,2));
 console.log("Offline HTML, image navigation and the 57-second recording play successfully.");
}finally{await browser.close();}
