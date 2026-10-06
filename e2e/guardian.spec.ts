import { expect, test, type Page } from "@playwright/test";

// 보호자가 화면에서 겪는 흐름을 실제 브라우저로 확인한다. 가짜 모델 서버는 제목의 plan:대로 응답한다.
async function upload(page: Page, wanted: string, plan: string): Promise<void> {
  await page.goto("/");
  await page.getByLabel("작품 제목").fill(`e2e-${Date.now()} ${plan}`);
  await page.getByLabel("원하는 결과").selectOption(wanted);
  await page.getByRole("button", { name: "올리기" }).click();
}

const wall = (page: Page) => page.getByTestId("on-wall");
const status = (page: Page) => page.getByTestId("status");

test("올리는 즉시 원본 액자가 걸리고, 결과는 확인한 뒤에만 바꿔 건다", async ({ page }) => {
  await upload(page, "animated", "plan:timeout,ok");
  await expect(wall(page)).toHaveText("원본 액자");
  await expect(status(page)).toHaveText("결과가 나왔어요: 움직이는 그림");
  await expect(wall(page)).toHaveText("원본 액자");
  await expect(page.getByTestId("causes")).toContainText("서버 장애로 다시 시도함");
  await page.getByTestId("hang-result").click();
  await expect(wall(page)).toHaveText("움직이는 그림");
});

test("결과를 만들지 못하면 안내하고 원본 액자만 고를 수 있다", async ({ page }) => {
  await upload(page, "animated", "plan:timeout,timeout,timeout");
  await expect(status(page)).toHaveText("결과를 만들지 못했어요");
  await expect(page.getByTestId("notice")).toBeVisible();
  await expect(page.getByTestId("hang-result")).toBeDisabled();
  await expect(page.getByTestId("keep-frame")).toBeEnabled();
  await page.getByTestId("keep-frame").click();
  await expect(wall(page)).toHaveText("원본 액자");
});

test("품질이 모자라면 낮춘 결과와 그 이유가 보인다", async ({ page }) => {
  await upload(page, "animated", "plan:quality_below");
  await expect(status(page)).toHaveText("결과가 나왔어요: 입체");
  await expect(page.getByTestId("causes")).toHaveText("품질이 모자라 한 단계 낮춤");
});

test("원본 액자를 고르면 모델을 기다리지 않는다", async ({ page }) => {
  await upload(page, "frame", "plan:down");
  await expect(status(page)).toHaveText("결과가 나왔어요: 원본 액자");
  await expect(page.getByTestId("causes")).toHaveText("보호자가 처음부터 고름");
});
