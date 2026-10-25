import { test, expect } from "@playwright/test";
test("咨询暂停后，自媒体连接和周期内容仍可维护", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("邮箱", { exact: true })
    .fill("owner.qinghe@zhiying.example");
  await page.getByLabel("密码", { exact: true }).fill("Demo-Staff-2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /今天也从容一点/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "咨询接待", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "内容工作室", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "新建内容", exact: true }),
  ).toBeVisible();
  const cookies = await page.context().cookies(),
    csrf = cookies.find((c) => c.name === "ops_csrf")!.value;
  const account = await (
    await page.request.post("/api/v1/social-accounts", {
      headers: { "X-CSRF-Token": csrf },
      data: { platform: "channels", name: "周期宣发验收" + Date.now() },
    })
  ).json();
  const blocked = await page.request.post(
    `/api/v1/social-accounts/${account.id}/manual-interactions`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: { sender_name: "示例", body: "咨询", kind: "comment" },
    },
  );
  expect(blocked.status()).toBe(403);
  const campaign = await page.request.post("/api/v1/records/campaign", {
    headers: { "X-CSRF-Token": csrf },
    data: { data: { name: "每周宣发验收", interval_days: 7 } },
  });
  expect(campaign.status()).toBe(201);
});
