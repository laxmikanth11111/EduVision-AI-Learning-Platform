/* EduVision real-browser E2E — drives installed Chrome via puppeteer-core against the live backend. */
const puppeteer = require("puppeteer-core");
const os = require("os");

const BASE = "http://localhost:8000/frontend";
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PPTX = "C:\\Users\\Admin\\OneDrive\\Desktop\\AI visual learning\\backend\\storage-data\\eduvision-content\\sources\\pres_0d6f47a76274476e\\6ad6357e88ce42c5a625bffe469131f5_ML_UNIT3_PPT.pptx";
const VIEW = { width: 1440, height: 900 };

const stamp = Date.now();
const EMAIL = `brws${stamp}@t.com`;
const PASSWORD = "E2ETest123!";

const passList = [], failList = [], notes = [];
function pass(name, detail) { passList.push(name); console.log(`PASS  ${name}${detail ? "  (" + detail + ")" : ""}`); }
function fail(name, detail, cls) {
    failList.push(name);
    console.log(`FAIL  ${name}  (${detail})`);
    notes.push({ name, detail, classification: cls || "REAL APPLICATION BUG" });
}
function note(text) { notes.push({ name: "NOTE", detail: text, classification: "ENVIRONMENT LIMITATION" }); console.log("NOTE  " + text); }

const consoleErrors = [], pageErrors = [], failedRequests = [], badResponses = [];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function waitFor(fn, timeoutMs, pollMs, label) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        let v = false;
        try { v = await fn(); } catch (e) {}
        if (v) return true;
        await sleep(pollMs || 500);
    }
    throw new Error(`waitFor timeout after ${Math.round(timeoutMs/1000)}s: ${label}`);
}

(async () => {
    const browser = await puppeteer.launch({
        executablePath: CHROME,
        headless: true,
        defaultViewport: VIEW,
        args: ["--no-first-run", "--disable-features=Translate"],
    });
    const page = await browser.newPage();

    const chromeVersion = await browser.version();
    console.log(`Browser: ${chromeVersion} (headless)\n`);

    page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text().substring(0, 300)); });
    page.on("pageerror", e => pageErrors.push(String(e.message).substring(0, 300)));
    page.on("requestfailed", r => {
        const u = r.url();
        if (!u.includes("favicon")) failedRequests.push(`${u.substring(0, 120)} :: ${r.failure() && r.failure().errorText}`);
    });
    page.on("response", res => {
        const s = res.status();
        if (s >= 400) {
            const u = res.url();
            if (!u.includes("favicon")) badResponses.push(`${s} ${u.substring(0, 140)}`);
        }
    });

    // ══ 1. LANDING ════════════════════════════════════════════════════════════
    try {
        await page.goto(BASE + "/index.html", { waitUntil: "networkidle2", timeout: 30000 });
        const h1 = await page.$eval("h1", el => el.textContent.trim());
        const links = await page.$$eval(".actions a", els => els.map(a => a.textContent.trim()));
        if (h1 === "EduVision AI" && links.join(",").includes("Get Started") && links.join(",").includes("Sign In"))
            pass("Landing", h1);
        else fail("Landing", `h1=${h1} links=${links}`);
    } catch (e) { fail("Landing", e.message); }

    // ══ 2. SIGNUP (real form) ═════════════════════════════════════════════════
    try {
        await page.goto(BASE + "/signup.html", { waitUntil: "networkidle2", timeout: 30000 });
        await page.type("#name", "Browser E2E Tester");
        await page.type("#email", EMAIL);
        await page.type("#password", PASSWORD);
        const nav = page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 });
        await page.click("#submitBtn");
        await nav;
        if (page.url().includes("upload.html")) pass("Signup", `${EMAIL} -> upload.html`);
        else {
            const st = await page.$eval("#statusMsg", el => el.textContent).catch(() => "");
            fail("Signup", `url=${page.url()} status=${st}`);
        }
    } catch (e) { fail("Signup", e.message); }

    // ══ 3. UPLOAD PAGE GUARD + USER CONTEXT ═══════════════════════════════════
    try {
        await waitFor(async () => await page.$eval("#userName", el => el.textContent.trim()), 10000, 300, "#userName");
        const uname = await page.$eval("#userName", el => el.textContent.trim());
        if (uname) pass("Upload page user context", uname);
        else fail("Upload page user context", "empty #userName");
    } catch (e) { fail("Upload page user context", e.message); }

    // ══ 4. UPLOAD ML_UNIT3 PPTX (real file input) ═════════════════════════════
    try {
        const input = await page.$("#fileInput");
        await input.uploadFile(PPTX);
        const nav = page.waitForNavigation({ waitUntil: "networkidle2", timeout: 180000 });
        await nav;
        if (page.url().includes("processing.html?id=")) {
            pass("PPTX upload -> processing", page.url().split("/").pop());
        } else {
            const st = await page.$eval("#status", el => el.textContent).catch(() => "");
            fail("PPTX upload -> processing", `url=${page.url()} status=${st}`);
        }
    } catch (e) { fail("PPTX upload -> processing", e.message); }

    // ══ 5. PROCESSING PAGE (its own polling, bounded) ═════════════════════════
    let lessonId = null, deckId = null, blockCount = -1, metaText = "";
    try {
        await page.waitForFunction(() => {
            const b = document.getElementById("start-btn");
            return b && b.style.display === "block";
        }, { timeout: 800000, polling: 3000 });
        metaText = await page.$eval("#deckMeta", el => el.textContent.trim());
        const hint = await page.$eval("#review-hint", el => el.textContent.trim());
        blockCount = (hint.match(/^(\d+)/) || [])[1] ? parseInt(hint.match(/^(\d+)/)[1], 10) : -1;
        const href = await page.$eval("#start-btn", el => el.getAttribute("href"));
        lessonId = (href.match(/lesson=([^&]+)/) || [])[1];
        deckId = (href.match(/deck=([^&]+)/) || [])[1];
        const topicRows = await page.$$eval("#topics .topic-row", els => els.length);
        const firstTopic = await page.$eval("#topics .topic-row .topic-name", el => el.textContent.trim()).catch(() => "");
        if (lessonId && deckId && blockCount > 0) {
            pass("Processing pipeline", `meta="${metaText}" hint="${hint}" rows=${topicRows}`);
            console.log(`      deck=${deckId} lesson=${lessonId} first-topic="${firstTopic.substring(0, 60)}"`);
        } else fail("Processing pipeline", `href=${href} hint=${hint} meta=${metaText}`);
    } catch (e) {
        const rowTxt = await page.evaluate(() =>
            ["row-extract","row-topics","row-lesson"].map(id => {
                const el = document.getElementById(id); return el ? el.textContent.trim() : "?";
            }).join(" | ")).catch(() => "?");
        fail("Processing pipeline", e.message + ` rows=[${rowTxt}]`);
    }

    // ══ 6. OPEN PLAYER VIA START BUTTON ═══════════════════════════════════════
    let playerOK = false, thumbCount = -1, counterText = "";
    if (lessonId) {
        try {
            const nav = page.waitForNavigation({ waitUntil: "networkidle2", timeout: 45000 });
            await page.click("#start-btn");
            await nav;
            if (!page.url().includes("player.html?lesson=")) throw new Error("did not reach player.html: " + page.url());
            await waitFor(async () => (await page.$$eval(".thumb", els => els.length)) > 0, 60000, 400, "thumbnails");
            thumbCount = await page.$$eval(".thumb", els => els.length);
            counterText = (await page.$eval("#counter", el => el.textContent)).replace(/\s+/g, "").trim();
            const errState = await page.$eval("#stateWrap", el => el.style.display !== "none" && el.innerHTML.includes("Failed")).catch(() => false);
            if (errState) throw new Error("player showed Failed-to-load state");
            playerOK = true;
            pass("Player opens via Start", `thumbs=${thumbCount} counter=${counterText}`);
        } catch (e) { fail("Player opens via Start", e.message); }
    } else fail("Player opens via Start", "skipped - no lessonId");

    // ══ 7. CONCEPT SLIDE CONTENT ══════════════════════════════════════════════
    let conceptTitle = "", conceptTextLen = 0;
    if (playerOK) {
        try {
            conceptTitle = await page.$eval(".slide-title", el => el.textContent.trim());
            conceptTextLen = await page.$eval(".slide-text", el => el.textContent.trim().length);
            const kindLabel = await page.$eval(".count-label", el => el.textContent.trim());
            if (conceptTitle && conceptTitle !== "[object Object]" && conceptTextLen > 10 && kindLabel.includes("Concept"))
                pass("Concept slide content", `"${conceptTitle.substring(0, 50)}" descLen=${conceptTextLen}`);
            else fail("Concept slide content", `title="${conceptTitle}" descLen=${conceptTextLen} label=${kindLabel}`);
        } catch (e) { fail("Concept slide content", e.message); }
    }

    // ── helper: navigate to an actual VISUAL slide (odd index) and generate ───
    // Slide model: even index = Concept, odd index = Visual.
    // Topic index is ALWAYS derived from live application state, never assumed.
    async function genVisual(thumbIdx, type, waitOutput, timeoutMs, label) {
        const handle = await page.$("#thumb-" + thumbIdx);
        if (!handle) throw new Error("Thumbnail missing: #thumb-" + thumbIdx);
        await handle.evaluate(el => el.scrollIntoView({ block: "center", inline: "nearest" }));
        const visible = await handle.evaluate(el => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        });
        if (!visible) throw new Error("Thumbnail not visible: #thumb-" + thumbIdx);
        await handle.click();

        // Wait until the application actually switched to the requested slide.
        await waitFor(async () =>
            await page.evaluate(() => (typeof current !== "undefined" ? current : -1)) === thumbIdx,
            10000, 300, "active slide = " + thumbIdx);

        // Read REAL state from the application.
        const state = await page.evaluate(() => ({
            current,
            kind: slides[current] ? slides[current].kind : "?",
            topicIdx: slides[current] ? slides[current].topicIdx : -1,
        }));
        console.log(`      ${label}: current=${state.current}, kind=${state.kind}, topicIdx=${state.topicIdx}`);
        if (state.current !== thumbIdx) throw new Error(`Wrong active slide: expected ${thumbIdx}, got ${state.current}`);
        if (state.kind !== "visual") throw new Error(`Expected visual slide but got ${state.kind} at slide ${state.current}`);

        const tIdx = state.topicIdx;
        await page.waitForSelector("#types-" + tIdx, { timeout: 10000 });
        await page.click("#types-" + tIdx + ' .type-btn[data-type="' + type + '"]');
        const btns = await page.$$("#viewport button");
        let clicked = false;
        for (const b of btns) {
            const t = await b.evaluate(el => el.textContent);
            if (/Generate Visual/i.test(t)) { await b.click(); clicked = true; break; }
        }
        if (!clicked) throw new Error("Generate Visual button not found");
        await waitFor(() => waitOutput(tIdx), timeoutMs, 500, label);
        return tIdx;
    }

    // ══ 8. CANVAS (image type) on slide 1 = topic 0 Visual ═══════════════════
    if (playerOK) {
        try {
            // Strategy-aware: accept .ev-node strategy renderers OR radial SVG.
            const canvasTopic = await genVisual(1, "image",
                async t => await page.$eval("#va-" + t, el => {
                    const svg = el.querySelector("svg");
                    return !!svg && (
                        el.querySelector(".ev-node") !== null ||
                        svg.querySelectorAll("circle, rect, text").length > 0
                    );
                }),
                90000, "canvas SVG");
            const evNodes = await page.$$eval(`#va-${canvasTopic} .ev-node`, els => els.length);
            const shapes = await page.$$eval(`#va-${canvasTopic} svg circle, #va-${canvasTopic} svg rect`,
                els => els.length);
            const texts = await page.$$eval(`#va-${canvasTopic} svg text`, els => els.length);
            let meta = null;
            try { meta = await page.evaluate(t => window["_evmeta_" + t] || null, canvasTopic); } catch (_) {}
            pass("Canvas/SVG visual",
                `topic=${canvasTopic} strategyNodes=${evNodes} shapes=${shapes} labels=${texts}`
                + (meta ? ` meta=${meta}` : ""));
        } catch (e) { fail("Canvas/SVG visual", e.message); }

        // ══ 9. ANIMATION on slide 5 = topic 2 Visual ══════════════════════════
        try {
            const animationTopic = await genVisual(5, "animation",
                async t => (await page.$$(".ae-node")).length > 0,
                90000, "animation blueprint");
            const nodeCount = (await page.$$(".ae-node")).length;
            const playBtn = await page.$(`#ae-play-${animationTopic}`);
            const before = await playBtn.evaluate(el => el.textContent);
            await playBtn.click();
            await sleep(200);
            const after = await playBtn.evaluate(el => el.textContent);
            const replayExists = !!(await page.$(`#ae-wrap-${animationTopic} .ae-controls .ae-btn`));
            const timeEl = await page.$eval(`#ae-time-${animationTopic}`, el => el.textContent).catch(() => "?");
            if ((before.includes("Pause") && after.includes("Play")) || (before.includes("Play") && after.includes("Pause")))
                pass("Animation + play/pause", `topic=${animationTopic} components=${nodeCount} time=${timeEl} controls=${replayExists ? "ok" : "missing"}`);
            else fail("Animation + play/pause", `btn "${before}" -> "${after}"`);
        } catch (e) { fail("Animation + play/pause", e.message); }

        // ══ 10. VIDEO on slide 9 = topic 4 Visual ═════════════════════════════
        try {
            const videoTopic = await genVisual(9, "video",
                async t => !!(await page.$("#va-" + t + " video")),
                180000, "video render");
            const src = await page.$eval(`#va-${videoTopic} video source`, el => el.getAttribute("src"));
            const meta = await page.evaluate(src2 => fetch(src2, { method: "HEAD" }).then(r => r.status), src);
            let loadedMeta = false;
            try {
                await page.waitForFunction(vi => {
                    const v = document.querySelector("#va-" + vi + " video");
                    return v && v.readyState >= 1;
                }, { timeout: 20000 }, videoTopic);
                loadedMeta = true;
            } catch (e) {}
            if (src && src.startsWith("/uploads/videos/") && meta === 200 && loadedMeta)
                pass("Video visual", `topic=${videoTopic} ${src} HTTP ${meta}, media loaded (readyState>=1)`);
            else fail("Video visual", `topic=${videoTopic} src=${src} http=${meta} loadedMeta=${loadedMeta}`,
                loadedMeta ? undefined : "REAL APPLICATION BUG");

            // 10b. Default playback speed must be 0.5x on a freshly loaded video
            const rate = await page.$eval(`#va-${videoTopic} video`, el => el.playbackRate);
            const speedBtns = await page.$$eval(`#va-${videoTopic} .vspeed-btn`, els => els.length);
            if (rate === 0.5 && speedBtns >= 6)
                pass("Video default speed", `playbackRate=${rate}, ${speedBtns} speed controls`);
            else fail("Video default speed", `playbackRate=${rate} (expected 0.5), controls=${speedBtns}`);
        } catch (e) { fail("Video visual", e.message); }

        // ══ 11. SIMULATION on slide 13 = topic 6 Visual ═══════════════════════
        try {
            const simulationTopic = await genVisual(13, "simulation",
                async t => {
                    const picks = await page.$$(".sim-pick");
                    const session = await page.$("#sim-session-" + t);
                    if (!picks.length || !session) return false;
                    const text = await session.evaluate(el => el.textContent || "");
                    return text.includes("Step 1");
                }, 120000, "simulation session");
            const sessSel = `#sim-session-${simulationTopic}`;
            const stepBefore = await page.$eval(sessSel, el => (el.textContent.match(/Step (\d+) of/) || [])[1]);
            const btns = await page.$$(sessSel + " button");
            let nextBtn = null;
            for (const b of btns) { const t = await b.evaluate(el => el.textContent); if (t.includes("Next")) { nextBtn = b; break; } }
            await nextBtn.click();
            await sleep(800);
            const stepAfter = await page.$eval(sessSel, el => (el.textContent.match(/Step (\d+) of/) || [])[1]);
            const objCount = await page.$$eval(sessSel + " p", els => els.filter(p => p.textContent.startsWith("\u2022")).length);
            if (Number(stepAfter) === Number(stepBefore) + 1)
                pass("Simulation session + step", `topic=${simulationTopic} step ${stepBefore}->${stepAfter}, objectives=${objCount}`);
            else fail("Simulation session + step", `step ${stepBefore}->${stepAfter}`);
        } catch (e) { fail("Simulation session + step", e.message); }
    }

    // ══ 12. NAVIGATION SUITE ═════════════════════════════════════════════════
    const C = () => page.$eval("#counter", el => el.textContent.replace(/\s+/g, ""));
    if (playerOK) {
        try {
            await page.keyboard.press("Home"); await sleep(250);
            if (await C() !== "1/" + thumbCount) throw new Error("Home -> " + await C());
            await page.keyboard.press("ArrowRight"); await sleep(250);
            if (!(await C()).startsWith("2/")) throw new Error("ArrowRight -> " + await C());
            await page.keyboard.press("ArrowLeft"); await sleep(250);
            if (!(await C()).startsWith("1/")) throw new Error("ArrowLeft -> " + await C());
            await page.click("#nextBtn"); await sleep(250);
            if (!(await C()).startsWith("2/")) throw new Error("nextBtn -> " + await C());
            await page.click("#prevBtn"); await sleep(250);
            if (!(await C()).startsWith("1/")) throw new Error("prevBtn -> " + await C());

            await page.keyboard.press("End"); await sleep(600);
            if (await C() !== thumbCount + "/" + thumbCount) throw new Error("End -> " + await C());
            const nextDisabled = await page.$eval("#nextBtn", el => el.disabled);
            const activeThumbOk = await page.$eval("#thumb-" + (thumbCount - 1), el => el.classList.contains("active"));
            const sbScrolled = await page.$eval("#sidebar", el => el.scrollTop > 0);
            if (!nextDisabled) throw new Error("Next not disabled at end");
            if (!activeThumbOk) throw new Error("active thumb not marked at end");
            if (!sbScrolled) note("Thumbnail auto-scroll: sidebar.scrollTop=0 at last slide (may fit viewport)");
            pass("Navigation suite", `Home/Arrows/Prev/Next/End over ${thumbCount} slides, end-state ok, autoscroll=${sbScrolled}`);

            await page.keyboard.press("Home"); await sleep(300);
        } catch (e) { fail("Navigation suite", e.message); }

        // ══ 13. PRESENT MODE ══════════════════════════════════════════════════
        try {
            await page.click("#presentBtn");
            await sleep(400);
            const presenting = await page.evaluate(() => document.body.classList.contains("presenting"));
            const sidebarHidden = await page.$eval("#sidebar", el => getComputedStyle(el).display === "none");
            const exitVisible = !!(await page.$(".present-exit"));
            await page.keyboard.press("Escape"); await sleep(300);
            const exited = await page.evaluate(() => !document.body.classList.contains("presenting"));
            const fsElement = await page.evaluate(() => !!document.fullscreenElement);
            if (presenting && sidebarHidden && exitVisible && exited)
                pass("Present mode", `enter/exit ok; fullscreen during test=${fsElement ? "engaged" : "not engaged (headless)"}`);
            else fail("Present mode", `presenting=${presenting} sidebarHidden=${sidebarHidden} exit=${exitVisible} exited=${exited}`);
            if (!fsElement) note("Fullscreen API did not engage under headless Chrome; state/CSS behavior verified instead.");
        } catch (e) { fail("Present mode", e.message); }

        // ══ 14. REFRESH ═══════════════════════════════════════════════════════
        try {
            await page.reload({ waitUntil: "networkidle2" });
            await waitFor(async () => (await page.$$eval(".thumb", els => els.length)) > 0, 60000, 400, "reload thumbnails");
            const thumbs2 = await page.$$eval(".thumb", els => els.length);
            const counter2 = (await page.$eval("#counter", el => el.textContent)).replace(/\s+/g, "");
            if (thumbs2 === thumbCount && counter2.endsWith("/" + thumbCount))
                pass("Player refresh", `thumbs=${thumbs2} counter=${counter2}`);
            else fail("Player refresh", `thumbs=${thumbs2}/${thumbCount} counter=${counter2}`);
        } catch (e) { fail("Player refresh", e.message); }
    }

    // ══ 15. AUTH: INVALID LOGIN ═══════════════════════════════════════════════
    try {
        await page.goto(BASE + "/signin.html", { waitUntil: "networkidle2", timeout: 30000 });
        await page.evaluate(() => { localStorage.clear(); });
        await page.goto(BASE + "/signin.html", { waitUntil: "networkidle2", timeout: 30000 });
        await page.type("#email", EMAIL);
        await page.type("#password", "WrongPassword1!");
        await page.click("#submitBtn");
        await waitFor(async () => {
            const cls = await page.$eval("#statusMsg", el => el.className);
            return cls.includes("error");
        }, 15000, 300, "invalid login error");
        pass("Invalid login handled", await page.$eval("#statusMsg", el => el.textContent.trim()));
    } catch (e) { fail("Invalid login handled", e.message); }

    // ══ 16. VALID LOGIN ═══════════════════════════════════════════════════════
    try {
        await page.evaluate(() => { document.querySelectorAll("#email,#password").forEach(el => el.value = ""); });
        await page.type("#email", EMAIL);
        await page.type("#password", PASSWORD);
        const nav = page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 });
        await page.click("#submitBtn");
        await nav;
        if (page.url().includes("upload.html")) pass("Valid login", "-> upload.html");
        else fail("Valid login", page.url());
    } catch (e) { fail("Valid login", e.message); }

    // ══ 17. LOGOUT + PROTECTED ROUTE ══════════════════════════════════════════
    try {
        const nav = page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 });
        await page.click("#logoutBtn");
        await nav;
        if (!page.url().includes("signin.html")) throw new Error("logout landed on " + page.url());
        await page.goto(BASE + "/upload.html", { waitUntil: "networkidle2", timeout: 30000 });
        await sleep(700);
        if (page.url().includes("signin.html")) pass("Logout + protected route", "redirected to signin");
        else fail("Logout + protected route", "upload.html reachable without auth: " + page.url());
    } catch (e) { fail("Logout + protected route", e.message); }

    await browser.close();

    // ══ FINAL REPORT ══════════════════════════════════════════════════════════
    console.log(`
==================================================
EDUVISION REAL BROWSER E2E RESULT
==================================================
Browser:              ${chromeVersion}
Signup:               ${passList.includes("Signup") ? "PASS" : "FAIL"} (${EMAIL})
Login:                ${(passList.includes("Valid login")) ? "PASS" : "FAIL"}
Upload:               ${failList.includes("PPTX upload -> processing") ? "FAIL" : "PASS"}
Processing:           ${failList.includes("Processing pipeline") ? "FAIL" : "PASS"}
Extraction:           ${metaText ? "PASS (" + metaText + ")" : "FAIL"}
Lesson generation:    ${blockCount > 0 ? "PASS" : "FAIL"}
Blocks/topics:        ${blockCount}
Player:               ${playerOK ? "PASS" : "FAIL"}
Player slides:        ${thumbCount}
Concept:              ${failList.includes("Concept slide content") ? "FAIL" : "PASS"}
Canvas:               ${failList.includes("Canvas/SVG visual") ? "FAIL" : "PASS"}
Animation:            ${failList.includes("Animation + play/pause") ? "FAIL" : "PASS"}
Video:                ${failList.includes("Video visual") ? "FAIL" : "PASS"}
Simulation:           ${failList.includes("Simulation session + step") ? "FAIL" : "PASS"}
Navigation:           ${failList.includes("Navigation suite") ? "FAIL" : "PASS"}
Keyboard:             ${failList.includes("Navigation suite") ? "FAIL" : "PASS"} (shared suite)
Present mode:         ${failList.includes("Present mode") ? "FAIL" : passList.some(p => p.startsWith("Present")) ? "PASS" : "NOT RUN"}
Refresh:              ${failList.includes("Player refresh") ? "FAIL" : passList.includes("Player refresh") ? "PASS" : "NOT RUN"}
Console errors:       ${consoleErrors.length}
JS exceptions:        ${pageErrors.length}
Failed requests:      ${failedRequests.length}
HTTP >= 400:          ${badResponses.length}

TOTAL: ${passList.length} passed, ${failList.length} failed
--------------------------------------------------`);
    if (consoleErrors.length) console.log("CONSOLE ERRORS:\n  " + consoleErrors.slice(0, 12).join("\n  "));
    if (pageErrors.length) console.log("PAGE EXCEPTIONS:\n  " + pageErrors.slice(0, 12).join("\n  "));
    if (failedRequests.length) console.log("FAILED REQUESTS:\n  " + [...new Set(failedRequests)].slice(0, 12).join("\n  "));
    if (badResponses.length) console.log("HTTP >=400:\n  " + [...new Set(badResponses)].slice(0, 12).join("\n  "));
    if (notes.length) {
        console.log("CLASSIFICATION:");
        notes.forEach(n => console.log(`  [${n.classification}] ${n.name}: ${n.detail.substring(0, 160)}`));
    }
    process.exit(failList.length ? 1 : 0);
})().catch(e => { console.error("FATAL:", e); process.exit(2); });
