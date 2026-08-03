import { expect, test } from "@playwright/test";

test("登录页可以打开并展示表单", async ({ page }) => {
  await page.goto("/login");

  await expect(
    page.getByRole("heading", { name: "AiRestro" }),
  ).toBeVisible();
  await expect(page.getByPlaceholder("your@email.com")).toBeVisible();
  await expect(page.getByPlaceholder("密码")).toBeVisible();
  const submitButton = page.locator("button[type='submit']");
  await expect(submitButton).toBeVisible();
  await expect(submitButton).toContainText(/登\s*录/);
});
