// Playwright golden-path acceptance for the Presale QA demo UI.
// Launches, drives the full flow, asserts, screenshots, exits 1 on any failure.
//
// Prerequisites (once):
//   demo service running (make demo, or PRESALE_* env + presale-qa-api)
//   cd scripts/ui-golden && npm install && npx playwright install chromium-headless-shell
//     (Windows slow download: $env:PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright")
//
// Run:
//   node scripts/ui-golden/golden.mjs          # against http://127.0.0.1:8000
//   DEMO_BASE=http://host:8000 node ...        # custom target
//
// Screenshots land in <repo>/output/playwright/.
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.DEMO_BASE || "http://127.0.0.1:8000";
const OUT =
  process.env.UI_GOLDEN_OUT ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "output", "playwright");
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
}

const browser = await chromium.launch();
const page = await browser.newPage();
try {
  // 1. Load page & static structure
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
  check("页面标题", (await page.title()).includes("售前问答"));
  check("模式徽标区", await page.locator("#mode-badges .badge").first().isVisible());
  const badgeText = await page.locator("#mode-badges").innerText();
  check("真实 LLM 徽标", badgeText.includes("真实 LLM"), badgeText.replace(/\s+/g, " "));
  check("Hybrid 检索徽标", badgeText.includes("Hybrid"));
  check("商品下拉", (await page.locator("#product option").count()) >= 11);
  check("示例问题 chips", (await page.locator("#chips .chip").count()) >= 2);
  check("历史侧栏", await page.locator(".history").isVisible());

  // 2. Ask via example chip
  const firstQ = await page.locator("#chips .chip").first().innerText();
  await page.locator("#chips .chip").first().click();
  check("chip 填充输入框", (await page.locator("#question").inputValue()) === firstQ);

  await page.locator("#ask").click();
  // streaming: wait until feedback buttons appear (renderResult done)
  await page.waitForSelector("#result:not([hidden]) .fb-btn", { timeout: 120000 });
  const badges1 = await page.locator("#badges").innerText();
  check("结果徽标：已生成答案", badges1.includes("已生成答案"), badges1.replace(/\s+/g, " "));
  check("结果徽标：检索命中", badges1.includes("检索命中"));
  check("演示精选徽标", badges1.includes("演示精选"), badges1.replace(/\s+/g, " "));
  const answer1 = await page.locator("#answer").innerText();
  check("答案非空", answer1.trim().length > 10, answer1.slice(0, 40) + "…");
  check("证据列表可见", await page.locator("#evidence-block").isVisible());
  await page.screenshot({ path: path.join(OUT, "01-qa-result.png"), fullPage: true });

  // 3. Evidence expand
  const eviCount = await page.locator(".evi-item").count();
  check("证据条目 ≥1", eviCount >= 1, `count=${eviCount}`);
  await page.locator(".evi-loc").first().click();
  const bodyVisible = await page.locator(".evi-item").first().locator(".evi-body").isVisible();
  check("证据原文展开", bodyVisible);
  const bodyText = await page.locator(".evi-item").first().locator(".evi-body").innerText();
  check("证据原文非空", bodyText.trim().length > 0, bodyText.slice(0, 40));

  // 3b. Run timeline (platform visibility)
  check("运行时间线可见", await page.locator("#timeline-block").isVisible());
  const tlCount = await page.locator(".tl-item").count();
  check("时间线 4 阶段", tlCount === 4, `count=${tlCount}`);
  const tlText = await page.locator("#timeline").innerText();
  check("阶段含检索/生成", tlText.includes("知识检索") && tlText.includes("答案生成"), tlText.replace(/\s+/g, " ").slice(0, 80));
  const platformText = await page.locator("#platform-row").innerText();
  check("平台徽标 B0 契约", platformText.includes("B0 契约"), platformText.replace(/\s+/g, " "));
  await page.screenshot({ path: path.join(OUT, "01b-timeline.png"), fullPage: true });

  // 4b. Multi-agent relay (AgentCoordinator)
  await page.locator("#relay-btn").click();
  await page.waitForSelector("#relay:not([hidden]) .relay-agent:nth-child(1)", { timeout: 60000 });
  await page.waitForFunction(
    () => document.querySelectorAll("#relay-agents .relay-agent").length >= 2,
    null,
    { timeout: 60000 }
  );
  const relayBadges = await page.locator("#relay-badges").innerText();
  check("接力整体终态 need_human", relayBadges.includes("need_human"), relayBadges.replace(/\s+/g, " "));
  const relayCards = await page.locator(".relay-agent .ra-name").allInnerTexts();
  check("接力两段 Agent", relayCards.length === 2, relayCards.join(" → "));
  check("接力含售前 Agent", relayCards[0].includes("售前问答"), relayCards[0]);
  check("接力含评论 Agent", relayCards[1].includes("评论分析"), relayCards[1]);
  await page.screenshot({ path: path.join(OUT, "01c-relay.png"), fullPage: true });

  // 5. Feedback
  await page.locator(".fb-btn").first().click(); // 👍
  await page.waitForTimeout(400);
  const fbActive = await page.locator(".fb-btn").first().evaluate((el) => el.classList.contains("active"));
  check("👍 反馈激活", fbActive);

  // 5. History recorded + replay (incremental — old runs may pre-seed history)
  await page.waitForFunction(
    () => document.querySelectorAll("#history-list li").length >= 1,
    { timeout: 15000 },
  ).catch(() => {});
  const histBefore = await page.locator("#history-list li").count();
  check("历史侧栏出现记录", histBefore >= 1, `count=${histBefore}`);
  // 6. Follow-up turn (same product → session continues)
  await page.locator("#question").fill("那要是阴天呢，还建议穿吗？");
  await page.locator("#ask").click();
  await page.waitForFunction(
    (n) => document.querySelectorAll("#history-list li").length > n,
    histBefore,
    { timeout: 120000 }
  );
  check("追问第二轮进入历史", true, `before=${histBefore}`);
  await page.waitForFunction(
    () => document.getElementById("answer").innerText.trim().length > 10,
    null,
    { timeout: 15000 }
  );
  const answer2 = await page.locator("#answer").innerText();
  check("追问答案非空", answer2.trim().length > 10, answer2.slice(0, 40) + "…");
  await page.screenshot({ path: path.join(OUT, "02-followup.png"), fullPage: true });

  // 7. History replay click (newest entry = the follow-up we just asked)
  await page.locator("#history-list li").first().click();
  await page.waitForTimeout(300);
  const replayAnswer = await page.locator("#answer").innerText();
  check("历史回看加载旧答案", replayAnswer.trim().length > 10, replayAnswer.slice(0, 30));
  check(
    "回看是追问记录",
    (await page.locator("#history-list li .q").first().innerText()).includes("阴天"),
  );

  // 8. Review tab
  await page.locator('.tab[data-panel="panel-review"]').click();
  check("评论面板显示", await page.locator("#panel-review").isVisible());
  check("问答面板隐藏", !(await page.locator("#panel-qa").isVisible()));
  check("评论示例 chips", (await page.locator("#review-chips .chip").count()) >= 3);
  await page.locator("#review-chips .chip").nth(1).click(); // negative sample
  await page.locator("#review-ask").click();
  await page.waitForSelector("#review-result:not([hidden])", { timeout: 15000 });
  const reviewBadges = await page.locator("#review-badges").innerText();
  check("情感徽标：负面", reviewBadges.includes("负面情感"), reviewBadges.replace(/\s+/g, " "));
  const keywords = await page.locator("#review-keywords .kw-chip").allInnerTexts();
  check("关键词命中", keywords.length >= 2 && !keywords.includes("无命中"), keywords.join(","));
  await page.screenshot({ path: path.join(OUT, "03-review-tab.png"), fullPage: true });

  // 9. Back to QA tab
  await page.locator('.tab[data-panel="panel-qa"]').click();
  check("切回问答面板", await page.locator("#panel-qa").isVisible());
} catch (err) {
  check("流程未抛异常", false, String(err).slice(0, 300));
  await page.screenshot({ path: path.join(OUT, "99-error.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n==== ${results.length - failed.length}/${results.length} PASS ====`);
if (failed.length) {
  console.log("FAILED:");
  failed.forEach((f) => console.log("  - " + f.name + (f.detail ? "  " + f.detail : "")));
  process.exit(1);
}
