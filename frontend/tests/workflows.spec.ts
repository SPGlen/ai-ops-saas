import { test, expect, Page } from "@playwright/test";
async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@zhiying.example");
  await page.getByLabel("密码", { exact: true }).fill("Demo-Zhiying-2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "林老师，今天也从容一点" }),
  ).toBeVisible();
}
test("真实表单保存：家长预约进入招生线索", async ({ page }) => {
  const id = Date.now().toString();
  await page.goto("/book/qinghe-demo?source=e2e-booking");
  await page.getByLabel("家长称呼").fill("预约测试" + id);
  await page.getByLabel("联系电话").fill("13900000001");
  await page.getByLabel("方便联系的时间").fill("周三晚上");
  await page.getByLabel("想了解什么").fill("二年级AI体验课");
  await page.getByLabel("我同意机构").check();
  await page.getByRole("button", { name: "提交预约", exact: true }).click();
  await expect(
    page.getByText("已收到预约，机构老师将按您方便的时间联系"),
  ).toBeVisible();
  await login(page);
  await page.getByRole("link", { name: "招生线索", exact: true }).click();
  await page
    .getByRole("textbox", { name: "搜索招生线索" })
    .fill("预约测试" + id);
  await expect(
    page.getByRole("cell", { name: "预约测试" + id, exact: true }),
  ).toBeVisible();
});
test("机构隔离、内容保存和桌面工作台", async ({ page }) => {
  await login(page);
  await page.screenshot({
    path: "../docs/screenshots/dashboard-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "内容工作室", exact: true }).click();
  await page.getByRole("button", { name: "新建内容", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const title = "课程创作" + Date.now();
  await dialog.getByLabel("内容标题").fill(title);
  await dialog
    .getByLabel("正文或最终脚本")
    .fill(
      "先观察真实世界，再提出一个清楚的问题。这是一次真实保存和回读的浏览器验收。",
    );
  await dialog.getByRole("button", { name: "保存内容", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "当前机构" })
    .selectOption({ label: "星光课堂 · 演示机构" });
  await page.getByRole("link", { name: "内容工作室", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "当前机构" })
    .selectOption({ label: "青禾 AI 教育 · 演示机构" });
  await page.getByRole("link", { name: "内容工作室", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "评分规则", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "当前教育内容规则" }),
  ).toBeVisible();
});
test("咨询暂停：公开入口与员工入口隐藏，接口禁止产生新会话", async ({
  page,
}) => {
  await page.goto("/book/qinghe-demo");
  await expect(
    page.getByRole("button", { name: "咨询课程", exact: true }),
  ).toHaveCount(0);
  const denied = await page.request.post("/api/v1/public/qinghe-demo/chat");
  expect(denied.status()).toBe(403);
  await login(page);
  await expect(
    page.getByRole("link", { name: "咨询接待", exact: true }),
  ).toHaveCount(0);
});
test("报名收款、开通课时、重复签到和部分退款", async ({ page }) => {
  await login(page);
  const name = "验收学员" + Date.now();
  await page.getByRole("link", { name: "学员档案", exact: true }).click();
  await page.getByRole("button", { name: "新增学员档案", exact: true }).click();
  await page.getByRole("dialog").getByLabel("学员称呼").fill(name);
  await page
    .getByRole("dialog")
    .getByLabel("年级", { exact: true })
    .fill("二年级");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "保存记录" })
    .click();
  await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  await page.getByRole("link", { name: "财务台账", exact: true }).click();
  await page.getByRole("button", { name: "新增报名订单", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称 *", { exact: true }).fill(name + "报名");
  await dialog
    .getByLabel("学员", { exact: false })
    .selectOption({ label: name });
  await dialog.getByLabel(/^报名项目名称/).fill("AI创意探索");
  await dialog.getByLabel(/^学费金额/).fill("1980");
  await dialog.getByRole("button", { name: "保存记录" }).click();
  let row = page
    .getByRole("row")
    .filter({
      has: page.getByRole("cell", { name: name + "报名", exact: true }),
    });
  await row.getByRole("button", { name: "收款", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByLabel("交易说明或流水编号")
    .fill("浏览器验收模拟流水");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认登记", exact: true })
    .click();
  await expect(
    row.getByRole("cell", { name: "¥1,980.00", exact: true }),
  ).toHaveCount(2);
  await page.getByRole("link", { name: "教务管理", exact: true }).click();
  await page.getByRole("button", { name: "报名与课时", exact: true }).click();
  await page
    .getByRole("button", { name: "新增报名与课时", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("已收款订单").selectOption({ label: name + "报名" });
  await dialog
    .getByLabel("班级", { exact: false })
    .selectOption({ label: "周六创想班" });
  await dialog.getByRole("button", { name: "保存记录" }).click();
  row = page
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name, exact: true }) });
  await row.getByRole("button", { name: "签到", exact: true }).click();
  await page.getByLabel("选择本班课程").selectOption({ index: 1 });
  await page.getByRole("button", { name: "确认到课", exact: true }).click();
  await expect(row.getByRole("cell", { name: "7", exact: true })).toBeVisible();
  await row.getByRole("button", { name: "签到", exact: true }).click();
  await page.getByLabel("选择本班课程").selectOption({ index: 1 });
  await page.getByRole("button", { name: "确认到课", exact: true }).click();
  await expect(row.getByRole("cell", { name: "7", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "财务台账", exact: true }).click();
  row = page
    .getByRole("row")
    .filter({
      has: page.getByRole("cell", { name: name + "报名", exact: true }),
    });
  await row.getByRole("button", { name: "退款", exact: true }).click();
  await page.getByLabel("金额（元）", { exact: true }).fill("300");
  await page.getByLabel("退款原因（必填）").fill("部分退款验收");
  await page.getByRole("button", { name: "确认登记", exact: true }).click();
  await expect(
    row.getByRole("cell", { name: "¥1,680.00", exact: true }),
  ).toBeVisible();
});
test("移动端导航、公开入口与空数据状态", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(
    page.getByRole("heading", { name: "林老师，今天也从容一点" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "机构与连接", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "机构与连接", exact: true }),
  ).toBeVisible();
  await page.goto("/book/qinghe-demo");
  await page.screenshot({
    path: "../docs/screenshots/booking-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
});
test("关键页面与离线接口文档正常加载", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  for (const label of [
    "教务管理",
    "财务台账",
    "课程知识库",
    "社群运营",
    "经营周报 / 月报",
    "经营规则与提醒",
    "表单与流程",
    "数字人直播（增值）",
    "机构与连接",
    "平台管理",
  ]) {
    await page.getByRole("link", { name: label, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await expect(
      page.getByText("请检查必填字段和格式", { exact: true }),
    ).toHaveCount(0);
  }
  await page.screenshot({
    path: "../docs/screenshots/platform-desktop.png",
    fullPage: true,
  });
  await page.goto("/api/docs");
  await expect(page.locator(".swagger-ui")).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: /知营 · 教育机构运营 API/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
