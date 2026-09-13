import { expect, test } from "@playwright/test";

// A valid one-pixel PNG, sent through the actual multipart upload and SQLite API.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC", "base64");

test("upload, display extraction, reload and reopen from SQLite history", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/documentos");
  await expect(page.getByText("Nenhum documento enviado ainda.")).toBeVisible();
  await page.getByRole("link", { name: "Enviar primeiro documento" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "documento.png", mimeType: "image/png", buffer: png });
  await expect(page).toHaveURL(/\/documentos\/\d+$/);
  await expect(page.getByRole("button", { name: "000123", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "1°S 48°W", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Observações: Vegetação nativa", exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Documento enviado", exact: true })).toBeVisible();
  await expect.poll(() => page.getByRole("img", { name: "Documento enviado", exact: true }).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1);
  await page.getByText("Evidências e observações", { exact: true }).nth(1).click();
  await expect(page.locator("details[open]").getByText("Região: r1")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "000123", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Voltar aos documentos" }).click();
  await expect(page.getByRole("cell", { name: "Belém", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "documento.png", exact: true }).click();
  await expect(page.getByText("AUTO DE INFRAÇÃO Nº 000123/2026", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "000123", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("history exposes connection errors and can retry", async ({ page, request }) => {
  const uploaded = await request.post("/api/extract", { multipart: { image: { name: "retry.png", mimeType: "image/png", buffer: png } } });
  expect(uploaded.ok()).toBeTruthy();
  await page.route("**/api/documents?**", (route) => route.fulfill({ status: 503, json: { error: { code: "unavailable", message: "Unavailable" } } }));
  await page.goto("/documentos");
  await expect(page.getByRole("alert")).toBeVisible();
  await page.unroute("**/api/documents?**");
  await page.getByRole("button", { name: "Atualizar lista" }).click();
  await expect(page.getByRole("link", { name: "retry.png", exact: true })).toBeVisible();
});

test("upload rejects unsupported files and displays service failures", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({ name: "documento.webp", mimeType: "image/webp", buffer: png });
  await expect(page.getByRole("alert")).toContainText("Formato não suportado");
  await page.route("**/api/extract", (route) => route.fulfill({ status: 429, json: { error: { code: "processing_capacity_reached", message: "Busy" } } }));
  await page.locator('input[type="file"]').setInputFiles({ name: "documento.png", mimeType: "image/png", buffer: png });
  await expect(page.getByRole("alert")).toContainText("processando outro documento");
  await expect(page.locator('input[type="file"]')).toBeEnabled();
});
