import { test, expect, Page } from "@playwright/test";
test.use({ extraHTTPHeaders: { "X-Forwarded-For": "127.0.5.7" } });
async function login(page: Page, account = "owner") {
  await page.goto("/");
  await page
    .getByLabel("邮箱", { exact: true })
    .fill(account + ".qinghe@zhiying.example");
  await page.getByLabel("密码", { exact: true }).fill("Demo-Staff-2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /今天也从容一点/ }),
  ).toBeVisible();
}

test("DeepSeek：负责人配置独立凭证、模型、费用来源并持久化", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "机构与连接", exact: true }).click();
  const row = page.locator(".kv").filter({ hasText: "DeepSeek 官方 API" });
  await row.getByRole("button", { name: /连接|替换凭证/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "连接 DeepSeek 官方 API" }),
  ).toBeVisible();
  await dialog
    .getByLabel("API Key", { exact: true })
    .fill("sk-e2e-fake-not-a-real-credential");
  await dialog.getByRole("button", { name: "保存连接", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const panel = page.getByRole("region", { name: "AI 模型配置", exact: true });
  await panel.getByLabel("文字智能体供应商").selectOption("deepseek");
  await panel.getByLabel("文字任务默认费用来源").selectOption("byok");
  await panel.getByLabel("输出 Token 上限").fill("2000");
  await expect(
    panel.getByRole("button", { name: "测试连接", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "保存 AI 配置", exact: true })
    .click();
  await expect(panel.getByText(/AI 配置已保存/)).toBeVisible();
  await page.reload();
  await expect(panel.getByLabel("文字智能体供应商")).toHaveValue("deepseek");
  await expect(panel.getByLabel("DeepSeek 模型")).toHaveValue("deepseek-flash");
  await expect(panel.getByLabel("输出 Token 上限")).toHaveValue("2000");
  await expect(
    panel.getByRole("button", { name: "测试连接", exact: true }),
  ).toBeEnabled();
  await expect(page.getByText("sk-e2e-fake-not-a-real-credential")).toHaveCount(
    0,
  );
  await page.screenshot({
    path: "../docs/screenshots/deepseek-settings.png",
    fullPage: true,
  });
  // Browser acceptance never sends the fake key to a real provider.
  await panel.getByLabel("文字智能体供应商").selectOption("aliyun");
  await panel.getByLabel("文字任务默认费用来源").selectOption("platform");
  await panel
    .getByRole("button", { name: "保存 AI 配置", exact: true })
    .click();
  await expect(panel.getByText(/AI 配置已保存/)).toBeVisible();
});

test("DeepSeek：授课员工无法看到模型配置或机构凭证", async ({ page }) => {
  await login(page, "teacher1");
  await page.getByRole("link", { name: "机构与连接", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "机构与连接", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "AI 模型配置", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "服务连接", exact: true }),
  ).toHaveCount(0);
});

test('DeepSeek：报表版本提供独立的汇总解读入口', async ({ page }) => {
  await login(page);
  const csrf = (await page.context().cookies()).find(x => x.name === 'ops_csrf')?.value || '';
  const response = await page.request.post('/api/v1/report-snapshots/weekly?period=2026-10-19', { headers: { 'X-CSRF-Token': csrf } });
  expect(response.ok()).toBeTruthy();
  const snapshot = await response.json();
  await page.getByRole('link', { name: '经营规则与提醒', exact: true }).click();
  await page.getByRole('button', { name: `周报 ${snapshot.period} · 第${snapshot.version}版`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'AI 经营解读', exact: true })).toBeVisible();
  await expect(dialog.getByRole('button', { name: '生成 AI 解读', exact: true })).toBeEnabled();
  await expect(dialog.getByText(/仅发送当前版本的汇总数字/)).toBeVisible();
  await page.screenshot({ path: '../docs/screenshots/deepseek-report-summary.png', fullPage: true });
});
