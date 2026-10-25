import { test, expect, Page } from "@playwright/test";
async function loginStaff(
  page: Page,
  email: string,
  password = "Demo-Staff-2026!",
) {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /今天也从容一点/ }),
  ).toBeVisible();
}
test("教师只见本班学生，隐藏招生财务和内容入口", async ({ page }) => {
  await loginStaff(page, "teacher1.qinghe@zhiying.example");
  await expect(
    page.getByRole("link", { name: "招生线索", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "财务台账", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "内容工作室", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "学员档案", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "演示学员1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "演示学员2", exact: true }),
  ).toHaveCount(0);
  const denied = await page.request.get("/api/v1/records/order");
  expect(denied.status()).toBe(403);
  await page.screenshot({
    path: "../docs/screenshots/staff-teacher.png",
    fullPage: true,
  });
});
test("招生看本人线索和订单，不能登记收退款", async ({ page }) => {
  await loginStaff(page, "admissions1.qinghe@zhiying.example");
  await page.getByRole("link", { name: "招生线索", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "演示线索1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "演示线索2", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "课程订单", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "演示报名1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "演示报名2", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "收款", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "../docs/screenshots/staff-admissions.png",
    fullPage: true,
  });
});
test("财务和兼任岗位保留模块边界", async ({ page }) => {
  await loginStaff(page, "combined.qinghe@zhiying.example");
  await expect(
    page.getByRole("link", { name: "教务管理", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "财务台账", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "内容工作室", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "咨询接待", exact: true }),
  ).toHaveCount(0);
  const records = await (
    await page.request.get("/api/v1/records/student")
  ).json();
  expect(records.items.find((r: any) => r.data.notes)).toBeUndefined();
});
test("机构负责人邀请新员工，接受后不创建新机构", async ({ page, browser }) => {
  await loginStaff(page, "owner.qinghe@zhiying.example");
  await page.getByRole("link", { name: "机构与连接", exact: true }).click();
  const email = "browser-staff-" + Date.now() + "@example.com";
  await page.getByLabel("员工邮箱", { exact: true }).fill(email);
  await page
    .getByRole("button", { name: "发送24小时邀请", exact: true })
    .click();
  const link = page.getByRole("link", {
    name: "打开员工加入页面",
    exact: true,
  });
  await expect(link).toBeVisible();
  const url = await link.getAttribute("href");
  const context = await browser.newContext();
  const employee = await context.newPage();
  await employee.goto(url!);
  await employee
    .getByLabel("姓名（新账号必填）", { exact: true })
    .fill("邀请验收员工");
  await employee
    .getByLabel("密码（已有账号填写当前密码）", { exact: true })
    .fill("Browser-Employee-2026!");
  await employee
    .getByRole("button", { name: "接受邀请并进入机构", exact: true })
    .click();
  await expect(
    employee.getByRole("heading", { name: "邀请验收员工，今天也从容一点" }),
  ).toBeVisible();
  const me = await (await employee.request.get("/api/v1/auth/me")).json();
  expect(me.tenants).toHaveLength(1);
  expect(me.roles).toEqual(["teacher"]);
  await context.close();
});
test("未接通的平台能力保留真实人工处理入口", async ({ page }) => {
  await loginStaff(page, "owner.qinghe@zhiying.example");
  await page.goto("/#publishing");
  await expect(
    page.getByRole("heading", { name: "发布与复盘", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/staff-connectors.png",
    fullPage: true,
  });
});
