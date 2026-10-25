import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const folder=path.join(root,'docs/screenshots/manual');await fs.mkdir(folder,{recursive:true});
const browser=await chromium.launch();const context=await browser.newContext({viewport:{width:1500,height:1050},locale:'zh-CN'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 const health=await (await page.request.get('http://127.0.0.1:8188/api/v1/health')).json();
 await page.goto('http://127.0.0.1:8188/');await page.getByRole('button',{name:'机构负责人',exact:true}).click();
 await page.getByRole('link',{name:'自媒体矩阵',exact:true}).first().click();
 await expect(page.getByRole('button',{name:'扫码登录',exact:true}).first()).toBeVisible();
 await page.screenshot({path:path.join(folder,'01-matrix-accounts.png'),fullPage:false});
 const accounts=await page.evaluate(async()=>await(await fetch('/api/v1/social-accounts')).json());
 const me=await page.evaluate(async()=>await(await fetch('/api/v1/auth/me')).json());
 const login=await page.evaluate(async(id)=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('ops_csrf='))?.split('=').slice(1).join('=')||'');const r=await fetch('/api/v1/social-accounts/'+id+'/login',{method:'POST',headers:{'X-CSRF-Token':csrf,'Content-Type':'application/json'},body:'{}'});return {status:r.status,body:await r.json()}},accounts[0].id);
 await page.getByRole('button',{name:'添加账号',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByRole('dialog').screenshot({path:path.join(folder,'02-add-account.png')});
 const fields=await page.getByRole('dialog').locator('label').allTextContents();
 await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'品牌与分组',exact:true}).click();await page.screenshot({path:path.join(folder,'03-brand-groups.png'),fullPage:false});
 await page.getByRole('button',{name:'自动运营计划',exact:true}).click();await page.screenshot({path:path.join(folder,'04-automation-plans.png'),fullPage:false});
 await page.getByRole('link',{name:'机构与连接',exact:true}).first().click();await expect(page.getByRole('heading',{name:'机构与连接',exact:true})).toBeVisible();await page.screenshot({path:path.join(folder,'05-connections.png'),fullPage:false});
 const report={checked_at:new Date().toISOString(),environment:'local enterprise demo',health,features:me.features,account_count:accounts.length,connected_accounts:accounts.filter(a=>a.status==='connected').length,identity_verified_accounts:accounts.filter(a=>Boolean(a.identity_key)).length,login_attempt:login,account_form_fields:fields,external_publish_attempted:false,external_reply_attempted:false,errors};
 await fs.writeFile(path.join(root,'docs/account-connection-inspection.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report,null,2));
}finally{await context.close();await browser.close();}
