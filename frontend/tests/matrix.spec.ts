import { test, expect, Page } from "@playwright/test";
test.use({ extraHTTPHeaders: { "X-Forwarded-For": "127.0.4.1" } });
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
test("矩阵：负责人配置品牌、同平台双账号、分组和版本化计划", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "自媒体矩阵", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "让每个账号，各有定位、有序运营" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "品牌与分组", exact: true }).click();
  await page.getByRole("button", { name: "创建品牌档案", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称", { exact: true }).fill("矩阵验收品牌");
  await dialog.getByLabel("目标受众").fill("小学阶段家长");
  await dialog.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  for (const n of [1, 2]) {
    await page.getByRole("button", { name: "添加账号", exact: true }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel("账号备注").fill("矩阵测试校区" + n);
    await dialog.getByLabel("品牌档案").selectOption({ label: "矩阵验收品牌" });
    await dialog.getByLabel("账号月预算（元）").fill("100");
    await dialog.getByRole("button", { name: "保存配置", exact: true }).click();
    await expect(dialog).toHaveCount(0);
  }
  await page.getByRole("button", { name: "创建分组", exact: true }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称", { exact: true }).fill("校区矩阵组");
  await dialog.getByLabel("品牌档案").selectOption({ label: "矩阵验收品牌" });
  await dialog.getByRole("checkbox", { name: /矩阵测试校区1/ }).check();
  await dialog.getByRole("checkbox", { name: /矩阵测试校区2/ }).check();
  await dialog.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "自动运营计划", exact: true }).click();
  await page.getByRole("button", { name: "创建运营计划", exact: true }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("名称", { exact: true }).fill("每周家长科普");
  await dialog.getByLabel("品牌档案").selectOption({ label: "矩阵验收品牌" });
  await dialog
    .getByLabel("内容方向", { exact: true })
    .fill("AI亲子练习与课堂体验");
  await dialog
    .getByRole("checkbox", { name: "校区矩阵组", exact: true })
    .check();
  await dialog.getByLabel("单次运行预算（元）").fill("10");
  await dialog.getByLabel("计划每日预算（元）").fill("20");
  await dialog.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const row = page.getByRole("row").filter({ hasText: "每周家长科普" });
  await row.getByRole("button", { name: "预览", exact: true }).click();
  dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("目标账号 2 个", { exact: false }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "矩阵账号", exact: true }).click();
  await page.getByLabel("筛选品牌").selectOption({ label: "矩阵验收品牌" });
  await expect(
    page.getByRole("table").getByText("矩阵测试校区1", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table").getByText("矩阵测试校区2", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/matrix-accounts.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "任务与复盘", exact: true }).click();
  await expect(
    page.getByText("试运行或定时执行后，会在这里显示真实任务状态。", {
      exact: true,
    }),
  ).toBeVisible();
});
test("矩阵：教师无菜单且直接访问被拒绝", async ({ page }) => {
  await login(page, "teacher1");
  await expect(
    page.getByRole("link", { name: "自媒体矩阵", exact: true }),
  ).toHaveCount(0);
  expect((await page.request.get("/api/v1/matrix/overview")).status()).toBe(
    403,
  );
});
