/* Focused diagnostic: why does clicking #thumb-N fail after canvas generation? */
const puppeteer = require("puppeteer-core");
const fs = require("fs");

const BASE = "http://localhost:8000/frontend";
const API = "http://localhost:8000/api/v1";
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PPTX = "C:\\Users\\Admin\\OneDrive\\Desktop\\AI visual learning\\backend\\storage-data\\eduvision-content\\sources\\pres_0d6f47a76274476e\\6ad6357e88ce42c5a625bffe469131f5_ML_UNIT3_PPT.pptx";

const stamp = Date.now();
const EMAIL = `diag${stamp}@t.com`;
const PASSWORD = "DiagTest123!";
const pageErrors = [];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function waitFor(fn, timeoutMs, label) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        let v = false;
        try { v = await fn(); } catch (e) {}
        if (v) return true;
        await sleep(400);
    }
    throw new Error("timeout: " + label);
}

async function apiSetup() {
    const r = await fetch(API + "/auth/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "D", email: EMAIL, password: PASSWORD }),
    });
    const reg = await r.json();
    const tok = reg.tokens.access_token;
    const H = { Authorization: "Bearer " + tok };

    const d = await (await fetch(API + "/presentations", {
        method: "POST", headers: { ...H, "Content-Type": "application/json" },
        body: JSON.stringify({ title: "Diag deck" }),
    })).json();

    const fd = new FormData();
    const pptxBytes = fs.readFileSync(PPTX);
    fd.append("source", new Blob([pptxBytes], { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" }), "ML_UNIT3_PPT.pptx");
    const up = await fetch(`${API}/presentations/${d.data.id}/source`, { method: "POST", headers: H, body: fd });
    if (!up.ok) throw new Error("upload failed " + up.status);

    let slideCount = -1;
    await waitFor(async () => {
        const p = await (await fetch(`${API}/presentations/${d.data.id}`, { headers: H })).json();
        if (p.data.extraction_status === "ready") { slideCount = p.data.slide_count; return true; }
        return false;
    }, 120000, "extraction");

    const l = await (await fetch(`${API}/presentations/${d.data.id}/lessons`, {
        method: "POST", headers: { ...H, "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "slide" }),
    })).json();
    const lessonId = l.data.id;
    await waitFor(async () => {
        const lr = await (await fetch(`${API}/presentations/${d.data.id}/lessons/${lessonId}`, { headers: H })).json();
        return ["ready", "completed", "failed"].includes(lr.data.status);
    }, 180000, "lesson ready");
    console.log(`setup ok: deck=${d.data.id} lesson=${lessonId} slides=${slideCount}`);
    return { token: tok, deckId: d.data.id, lessonId };
}

(async () => {
    const { token, deckId, lessonId } = await apiSetup();

    const browser = await puppeteer.launch({
        executablePath: CHROME, headless: true,
        defaultViewport: { width: 1440, height: 900 },
        args: ["--no-first-run"],
    });
    const page = await browser.newPage();
    page.on("pageerror", e => pageErrors.push(String(e.message).substring(0, 300)));
    page.on("console", m => { if (m.type() === "error") pageErrors.push("CONSOLE: " + m.text().substring(0, 200)); });

    // seed auth storage on a guard-free page, then open player
    await page.goto(BASE + "/index.html", { waitUntil: "networkidle2", timeout: 30000 });
    await page.evaluate((t, email) => {
        localStorage.setItem("access_token", t);
        localStorage.setItem("refresh_token", "");
        localStorage.setItem("user", JSON.stringify({ name: "Diag", email }));
    }, token, EMAIL);
    await page.goto(`${BASE}/player.html?lesson=${lessonId}&deck=${deckId}`, { waitUntil: "networkidle2", timeout: 45000 });
    await waitFor(async () => (await page.$$(".thumb")).length > 0, 60000, "thumbnails");

    // ── reproduce E2E sequence: canvas on thumb-1 ────────────────────────────
    await page.click("#thumb-1");
    await page.waitForSelector("#types-0", { timeout: 10000 });
    await page.click('#types-0 .type-btn[data-type="image"]');
    const btns = await page.$$("#viewport button");
    for (const b of btns) {
        const t = await b.evaluate(el => el.textContent);
        if (/Generate Visual/i.test(t)) { await b.click(); break; }
    }
    let canvasOk = false;
    try {
        await waitFor(async () => (await page.$$eval("#va-0 svg circle", els => els.length)) > 0, 90000, "canvas svg");
        canvasOk = true;
    } catch (e) { console.log("canvas generation FAILED: " + e.message); }

    // helper to describe an element
    const describeEl = `(() => (el) => {
        if (!el) return "null";
        const cs = getComputedStyle(el);
        const cls = el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || "");
        return el.tagName + "#" + (el.id || "") + "." + String(cls).split(" ").filter(Boolean).join(".") +
            " [pointer-events=" + cs.pointerEvents + ", position=" + cs.position +
            ", z=" + cs.zIndex + ", overflow=" + cs.overflow + "]";
    })()`;

    // ── PRE-CLICK EVIDENCE ────────────────────────────────────────────────────
    await page.evaluate(() => { const t = document.getElementById("thumb-4"); if (t) t.scrollIntoView({ block: "center" }); });
    await sleep(300);

    const pre = await page.evaluate(describeEl);
    const evidence = await page.evaluate(`
        (() => {
            const out = {};
            const th = document.getElementById("thumb-4");
            out.thumb4Exists = !!th;
            if (!th) return out;
            const r = th.getBoundingClientRect();
            out.thumb4Box = { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
            const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
            out.thumb4Center = { x: Math.round(cx), y: Math.round(cy) };

            const hit = document.elementFromPoint(cx, cy);
            const desc = el => {
                if (!el) return "null";
                const cls = el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || "");
                const cs = getComputedStyle(el);
                return el.tagName + "#" + (el.id || "") + "." + String(cls).substring(0, 40) +
                    " [pe=" + cs.pointerEvents + " pos=" + cs.position + " z=" + cs.zIndex + " ovf=" + cs.overflow + "]";
            };
            out.hitElement = desc(hit);
            out.hitIsThumbOrChild = !!hit && !!th && (hit === th || th.contains(hit));

            const box = sel => {
                const el = typeof sel === "string" ? document.querySelector(sel) : sel;
                if (!el) return null;
                const b = el.getBoundingClientRect();
                return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
            };
            out.svgBox = box("#va-0 svg");
            out.svgParentBox = box("#va-0");
            out.viewportBox = box("#viewport");
            out.sidebarBox = box("#sidebar");
            out.frameBox = box("#frame");
            const inter = (a, b) => !a || !b ? 0 :
                Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) *
                Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
            out.svgOverlapsSidebarPx = inter(out.svgBox, out.sidebarBox);

            out.current = typeof current !== "undefined" ? current : "UNDEFINED";
            out.kind = slides[current] ? slides[current].kind : "?";
            out.topicIdx = slides[current] ? slides[current].topicIdx : "?";
            out.types2ExistsBefore = !!document.getElementById("types-2");
            out.url = location.href;
            return out;
        })()
    `);
    console.log("\n---- PRE-CLICK EVIDENCE ----");
    console.log(JSON.stringify(evidence, null, 2));

    // ── THE CLICK (same as E2E) ───────────────────────────────────────────────
    await page.click("#thumb-4").catch(e => console.log("page.click threw: " + e.message));
    await sleep(500);

    const post = await page.evaluate(`
        (() => {
            const out = {};
            out.currentAfterClick = typeof current !== "undefined" ? current : "UNDEFINED";
            out.kindAfter = slides[current] ? slides[current].kind : "?";
            out.topicIdxAfter = slides[current] ? slides[current].topicIdx : "?";
            out.types2ExistsAfter = !!document.getElementById("types-2");
            out.activeElement = document.activeElement ? document.activeElement.tagName + "#" + (document.activeElement.id || "") : "";
            out.counterText = document.getElementById("counter").textContent.replace(/\\s+/g, "");
            return out;
        })()
    `);
    console.log("\n---- POST-CLICK STATE ----");
    console.log(JSON.stringify(post, null, 2));

    // ── comparison: programmatic DOM click ────────────────────────────────────
    await page.evaluate(() => document.getElementById("thumb-8") && document.getElementById("thumb-8").click());
    await sleep(400);
    const domClick = await page.evaluate(`
        (() => ({
            currentAfterDomClick: typeof current !== "undefined" ? current : "UNDEFINED",
            types4Exists: !!document.getElementById("types-4"),
        }))()
    `);
    console.log("\n---- DOM .click() COMPARISON (thumb-8) ----");
    console.log(JSON.stringify(domClick, null, 2));

    await browser.close();

    // ── CONCLUSION ────────────────────────────────────────────────────────────
    const overlapYes = evidence.svgOverlapsSidebarPx > 0;
    let conclusion;
    if (!evidence.hitIsThumbOrChild && post.currentAfterClick !== 4) conclusion = "CLICK INTERCEPTION";
    else if (post.currentAfterClick === 4 && !post.types2ExistsAfter) conclusion = "DOM ISSUE (state changed, selector missing)";
    else if (post.currentAfterClick === 4 && post.types2ExistsAfter) conclusion = "TEST SCRIPT / TIMING ISSUE (state fine)";
    else conclusion = "STATE ISSUE (click received, goTo did not run)";

    console.log(`
==================================================
CLICK DIAGNOSTIC
==================================================
Canvas generation:            ${canvasOk ? "PASS" : "FAIL"}
thumb-4:                      ${evidence.thumb4Exists ? "FOUND" : "MISSING"}
thumb-4 bounding box:         ${JSON.stringify(evidence.thumb4Box)}
thumb-4 center:               ${JSON.stringify(evidence.thumb4Center)}
elementFromPoint:             ${evidence.hitElement}
elementFromPoint is thumb:    ${evidence.hitIsThumbOrChild ? "YES" : "NO"}
SVG box:                      ${JSON.stringify(evidence.svgBox)}
SVG parent (#va-0) box:       ${JSON.stringify(evidence.svgParentBox)}
#viewport box:                ${JSON.stringify(evidence.viewportBox)}
#sidebar box:                 ${JSON.stringify(evidence.sidebarBox)}
SVG/sidebar overlap px:       ${evidence.svgOverlapsSidebarPx} (${overlapYes ? "OVERLAPS" : "no overlap"})
current before click:         ${evidence.current} (${evidence.kind}, topic ${evidence.topicIdx})
current after click:          ${post.currentAfterClick} (${post.kindAfter}, topic ${post.topicIdxAfter})
types-2 exists after:         ${post.types2ExistsAfter ? "YES" : "NO"}
activeElement after:          ${post.activeElement}
counter after:                ${post.counterText}
DOM .click() on thumb-8:      current=${domClick.currentAfterDomClick} types-4=${domClick.types4Exists}
page errors:                  ${pageErrors.length}${pageErrors.length ? "\n  " + pageErrors.join("\n  ") : ""}

Conclusion: ${conclusion}
==================================================`);
})().catch(e => { console.error("FATAL:", e); process.exit(2); });
