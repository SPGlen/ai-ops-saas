import { test, expect, Page } from "@playwright/test";
async function login(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("邮箱", { exact: true })
    .fill("owner.qinghe@zhiying.example");
  await page.getByLabel("密码", { exact: true }).fill("Demo-Staff-2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /今天也从容一点/ }),
  ).toBeVisible();
}
test("周报月报、财务图表和票据详情真实读取", async ({ page }) => {
  await login(page);
  await page
    .getByRole("link", { name: "经营周报 / 月报", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "用同一组数据，看清经营变化", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("线索转化率", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/operations-reports.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "财务台账", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "收支概览", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "查看已确认费用明细", exact: true })
    .click();
  await expect(page.locator("#financial-transactions tbody tr")).toHaveCount(0);
  await page.getByRole("button", { name: "显示全部明细", exact: true }).click();
  const detail = page
    .locator("table")
    .getByRole("button")
    .filter({ hasText: "创想课报名" })
    .first();
  await detail.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("dialog").getByText("票据原件", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/operations-receipt.png",
    fullPage: true,
  });
});
test("可视化表单设计、发布和填写持久化", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "表单与流程", exact: true }).click();
  await page.getByRole("button", { name: "新建设计", exact: true }).click();
  let dlg = page.getByRole("dialog");
  const name = "家长需求表" + Date.now();
  await dlg.getByLabel("名称", { exact: true }).fill(name);
  await dlg.getByRole("button", { name: "创建设计", exact: true }).click();
  dlg = page.getByRole("dialog");
  await expect(
    dlg.getByRole("heading", { name: "表单设计器", exact: true }),
  ).toBeVisible();
  await dlg.getByRole("button", { name: "单行文本", exact: true }).click();
  await dlg.getByLabel("字段名称", { exact: true }).fill("意向说明");
  await dlg.getByRole("button", { name: "校验并发布", exact: true }).click();
  await expect(dlg.getByText(/已发布V1/).first()).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/operations-form-designer.png",
    fullPage: true,
  });
  await dlg.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "填写表单", exact: true }).click();
  await page
    .getByRole("button")
    .filter({ has: page.getByRole("heading", { name, exact: true }) })
    .click();
  dlg = page.getByRole("dialog");
  await dlg.getByLabel("意向说明", { exact: true }).fill("周末AI体验");
  await dlg.getByRole("button", { name: "提交表单", exact: true }).click();
  await expect(dlg).toHaveCount(0);
  await page.getByRole("button", { name: "提交记录", exact: true }).click();
  await expect(page.getByText("周末AI体验", { exact: true })).toBeVisible();
});
test("多人招生页面五秒内刷新新记录", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "招生线索", exact: true }).click();
  const second = await page.context().newPage();
  await second.goto("/");
  await expect(
    second.getByRole("heading", { name: /今天也从容一点/ }),
  ).toBeVisible();
  const csrf = (await page.context().cookies()).find(
      (c) => c.name === "ops_csrf",
    )!.value,
    name = "同步家长" + Date.now();
  const response = await second.request.post("/api/v1/records/lead", {
    headers: { "X-CSRF-Token": csrf },
    data: { data: { name, student_name: "同步学员", contact: "13800000001" } },
  });
  expect(response.status()).toBe(201);
  await expect(page.getByRole("cell", { name, exact: true })).toBeVisible({
    timeout: 5000,
  });
  await second.close();
});
test("数字人付费申请和移动端报表不宣称已开播", async ({ page }) => {
  await login(page);
  await page
    .getByRole("link", { name: "数字人直播（增值）", exact: true })
    .click();
  await expect(page.getByText("待接入", { exact: true })).toBeVisible();
  await page.getByLabel("机构需求", { exact: true }).fill("视频号课程介绍直播");
  await page
    .getByRole("button", { name: "申请开通 / 获取报价", exact: true })
    .click();
  await expect(
    page.getByText("申请已登记，等待平台报价与接入安排", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#reports");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../docs/screenshots/operations-mobile.png",
    fullPage: true,
  });
});
test("可视化流程画布、发布及审批待办完成", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "表单与流程", exact: true }).click();
  await page
    .getByRole("button", { name: "加载招生 / 教务 / 财务模板", exact: true })
    .click();
  const card = page.getByRole("button").filter({
    has: page.getByRole("heading", { name: "自定义表单审批", exact: true }),
  });
  await expect(card).toBeVisible();
  await card.click();
  let dlg = page.getByRole("dialog");
  await expect(dlg.locator(".react-flow__node")).toHaveCount(3);
  await dlg.locator(".react-flow__node").filter({ hasText: "审核" }).click();
  await dlg
    .getByRole("combobox", { name: "完成规则", exact: true })
    .selectOption("any");
  await dlg.getByRole("button", { name: "校验并发布", exact: true }).click();
  await expect(dlg.getByText(/已发布V1/).first()).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/operations-workflow-designer.png",
    fullPage: true,
  });
  await dlg.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "我的流程", exact: true }).click();
  await page
    .getByRole("button", { name: "发起：自定义表单审批", exact: true })
    .click();
  dlg = page.getByRole("dialog");
  await dlg.getByLabel("申请说明", { exact: true }).fill("测试申请");
  await dlg.getByRole("button", { name: "提交审批", exact: true }).click();
  await expect(dlg).toHaveCount(0);
  await page.getByRole("button", { name: /^审批待办/ }).click();
  await page
    .getByRole("button", { name: "查看并处理", exact: true })
    .first()
    .click();
  dlg = page.getByRole("dialog");
  await expect(dlg.getByText("测试申请", { exact: true })).toBeVisible();
  await dlg.getByRole("button", { name: "审批通过", exact: true }).click();
  await expect(dlg).toHaveCount(0);
  await page.getByRole("button", { name: "我的流程", exact: true }).click();
  await expect(
    page
      .getByText("已审核", { exact: true })
      .or(page.getByText("已审批", { exact: true }))
      .or(page.getByText("已通过", { exact: true })),
  ).toBeVisible();
});
test("招生Excel上传、全列核对和确认导入不自动记账", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "招生线索", exact: true }).click();
  await page
    .locator('input[type=file][accept*=".xlsx"]')
    .setInputFiles("../docs/samples/admissions-filled-fixture.xlsx");
  const dlg = page.getByRole("dialog");
  await expect(
    dlg.getByRole("heading", { name: "核对招生表识别结果", exact: true }),
  ).toBeVisible();
  await expect(
    dlg.getByLabel("第1行student_name", { exact: true }),
  ).toHaveValue("扫描示例学员", { timeout: 15000 });
  await dlg.getByLabel("第1行grade", { exact: true }).fill("三年级");
  await expect(
    dlg.getByRole("columnheader", { name: "预约时间", exact: true }),
  ).toBeVisible();
  await dlg
    .getByRole("button", { name: "确认导入选中行", exact: true })
    .click();
  await expect(dlg.getByText("已导入", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/operations-import-review.png",
    fullPage: true,
  });
  await dlg.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "扫描示例家长", exact: true }),
  ).toBeVisible();
  const orders = await (
    await page.request.get("/api/v1/records/order?q=扫描示例")
  ).json();
  expect(orders.total).toBe(0);
});
