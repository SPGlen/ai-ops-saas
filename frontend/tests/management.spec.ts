import { test, expect, Page } from "@playwright/test";
// Separate the new suite client from other suites to preserve the normal per-IP login limit.
test.use({ extraHTTPHeaders: { "X-Forwarded-For": "127.0.3.1" } });
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
test("负责人可视化授权，教师兼任营收仍只见本人学员", async ({
  page,
  browser,
}) => {
  await login(page);
  await page.getByRole("link", { name: "成员与授权", exact: true }).click();
  const row = page
    .getByRole("row")
    .filter({ hasText: "teacher1.qinghe@zhiying.example" });
  await row.getByRole("button", { name: "调整授权", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByRole("checkbox", { name: /整体营收查看/ }).check();
  await expect(
    dialog.getByText("仅汇总数据；不含订单、支出、票据及家长资料", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/management-authorization.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "保存授权", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const context = await browser.newContext();
  const employee = await context.newPage();
  try {
    await login(employee, "teacher1");
    await expect(
      employee.getByRole("link", { name: "营收总览", exact: true }),
    ).toBeVisible();
    await expect(
      employee.getByRole("link", { name: "财务台账", exact: true }),
    ).toHaveCount(0);
    await expect(
      employee.getByRole("link", { name: "成员与授权", exact: true }),
    ).toHaveCount(0);
    await employee.getByRole("link", { name: "学员档案", exact: true }).click();
    await expect(
      employee.getByRole("cell", { name: "演示学员1", exact: true }),
    ).toBeVisible();
    await expect(
      employee.getByRole("cell", { name: "演示学员2", exact: true }),
    ).toHaveCount(0);
  } finally {
    await row.getByRole("button", { name: "调整授权", exact: true }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByRole("checkbox", { name: /整体营收查看/ }).uncheck();
    await dialog.getByRole("button", { name: "保存授权", exact: true }).click();
  }
  await expect(
    employee.getByRole("link", { name: "营收总览", exact: true }),
  ).toHaveCount(0, { timeout: 10000 });
  expect(
    (await employee.request.get("/api/v1/revenue/overview")).status(),
  ).toBe(403);
  await context.close();
});
test("营收查看与排班账号分别显示获授权功能", async ({ page }) => {
  await login(page, "revenue");
  await page.getByRole("link", { name: "营收总览", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "整体营收总览", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "财务台账", exact: true }),
  ).toHaveCount(0);
  expect((await page.request.get("/api/v1/finance/overview")).status()).toBe(
    403,
  );
  await page.screenshot({
    path: "../docs/screenshots/management-revenue.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /退出/ }).click();
  await login(page, "scheduler");
  await page.getByRole("link", { name: "教务管理", exact: true }).click();
  await page.getByRole("button", { name: "排课", exact: true }).click();
  await expect(page.getByRole("button", { name: /新增/ })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "学员档案", exact: true }),
  ).toHaveCount(0);
  expect((await page.request.get("/api/v1/records/student")).status()).toBe(
    403,
  );
});
test("登记家长反馈并汇入周报与不可覆盖快照", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "教务管理", exact: true }).click();
  await page.getByRole("button", { name: "学员家长反馈", exact: true }).click();
  await page.getByRole("button", { name: "登记反馈", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("关联学员", { exact: true })
    .selectOption({ label: "演示学员1" });
  await dialog
    .getByLabel("关联班级", { exact: true })
    .selectOption({ label: "权限演示班1" });
  const title = "家长实际反馈" + Date.now();
  await dialog.getByLabel("反馈主题", { exact: true }).fill(title);
  await dialog
    .getByLabel("实际反馈内容", { exact: true })
    .fill("课程节奏希望慢一点，安排一次沟通。");
  await dialog.getByLabel("评分（可不填）", { exact: true }).selectOption("2");
  await dialog.getByRole("button", { name: "保存反馈", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/management-family-feedback.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "经营周报 / 月报", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "学员与家长反馈", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/低评分反馈1条/)).toBeVisible();
  await page.getByRole("button", { name: "保存报表版本", exact: true }).click();
  await expect(page.getByText(/已保存第/)).toBeVisible();
  const snapshots = await (
    await page.request.get("/api/v1/report-snapshots")
  ).json();
  const current = snapshots.find(
    (s: any) => s.kind === "weekly" && s.payload.family_feedback?.count > 0,
  );
  await page
    .getByRole("button", {
      name: `周报 ${current.period} · V${current.version}`,
      exact: true,
    })
    .click();
  dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("本页显示已保存版本", { exact: false }),
  ).toBeVisible();
  await expect(dialog.getByText(/低评分反馈1条/)).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/management-report.png",
    fullPage: true,
  });
});
test("财务流水可关联票据并查看原件与订单图表", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "财务台账", exact: true }).click();
  await page.getByRole("button", { name: "演示报名1", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "关联订单收款情况", exact: true }),
  ).toBeVisible();
  await dialog
    .locator("input[type=file]")
    .setInputFiles("../docs/samples/admissions-ocr-fixture.png");
  await expect(dialog.getByText("票据已关联", { exact: true })).toBeVisible();
  const preview = dialog.getByRole("img", {
    name: "admissions-ocr-fixture.png",
    exact: true,
  });
  await expect(preview).toBeVisible();
  expect(
    await preview.evaluate(
      (image: HTMLImageElement) => image.complete && image.naturalWidth > 0,
    ),
  ).toBeTruthy();
  const link = dialog.getByRole("link", { name: /admissions-ocr-fixture.png/ });
  expect(
    (await page.request.get((await link.getAttribute("href"))!)).status(),
  ).toBe(200);
  await page.screenshot({
    path: "../docs/screenshots/management-receipt.png",
    fullPage: true,
  });
});
