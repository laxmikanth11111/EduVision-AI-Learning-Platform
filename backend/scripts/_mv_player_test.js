/* Headless verification of the EduVision Presentation Player against the live API. */
const { JSDOM } = require("jsdom");
const fs = require("fs");

const BASE = "http://localhost:8000";
const TOKEN = fs.readFileSync(process.env.TOKEN_FILE, "utf8").trim();
const LESSON = process.argv[2] || "lesson_4089ba247bde4efe";

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name); }
}

async function main() {
  const pageHtml = await (await fetch(BASE + "/frontend/player.html?lesson=" + LESSON)).text();

  const dom = new JSDOM(pageHtml, {
    url: BASE + "/frontend/player.html?lesson=" + LESSON,
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = async (url, opts) => {
        const full = url.startsWith("http") ? url : BASE + url;
        opts = opts || {};
        opts.headers = Object.assign({}, opts.headers, { Authorization: "Bearer " + TOKEN });
        return fetch(full, opts);
      };
      window.localStorage.setItem("user", JSON.stringify({ name: "MV Tester", email: "mvtest@example.com" }));
      window.localStorage.setItem("access_token", TOKEN);
      window.HTMLElement.prototype.scrollIntoView = function () {};
      window.Element.prototype.scrollTo = function () {};
    },
  });

  const w = dom.window;
  const doc = w.document;
  w.document.documentElement.requestFullscreen = async () => {};
  w.document.exitFullscreen = async () => {};

  await new Promise(r => setTimeout(r, 4000));

  const cur = () => w.eval("current");
  const total = () => w.eval("slides.length");
  const counterTxt = () => doc.getElementById("counter").textContent.replace(/\s/g, "");
  const kd = key => doc.dispatchEvent(new w.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

  // ── Loading / data ──
  check("12 topics loaded -> 24 dynamic slides", total() === 24);
  check("thumbnails rendered (24)", doc.querySelectorAll(".thumb").length === 24);
  check("counter shows '1 / 24'", counterTxt() === "1/24");
  check("first thumbnail active", doc.getElementById("thumb-0").classList.contains("active"));

  // ── Concept slide render ──
  check("concept slide title rendered", doc.querySelector(".slide-title").textContent.length > 0);
  check("concept slide text rendered", doc.querySelector(".slide-text").textContent.length > 10);

  // ── Next / Prev buttons ──
  w.eval("nextSlide()");
  check("Next -> visual slide (type selector)", !!doc.getElementById("types-0"));
  check("counter shows '2 / 24'", counterTxt() === "2/24");
  check("thumb-1 active", doc.getElementById("thumb-1").classList.contains("active"));
  w.eval("prevSlide()");
  check("Prev -> back to concept slide", !doc.getElementById("types-0") && cur() === 0);

  // ── Keyboard ──
  kd("ArrowRight");
  check("ArrowRight advances", cur() === 1);
  kd("ArrowLeft");
  check("ArrowLeft goes back", cur() === 0);
  kd("End");
  check("End -> last slide (23)", cur() === 23);
  check("Next disabled at end", doc.getElementById("nextBtn").disabled === true);
  kd("Home");
  check("Home -> first slide", cur() === 0);
  check("Prev disabled at start", doc.getElementById("prevBtn").disabled === true);

  // ── Thumbnail click ──
  doc.getElementById("thumb-6").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  check("thumbnail click opens slide 7", cur() === 6);

  // ── Present mode ──
  await w.enterPresent();
  check("Present mode activates", doc.body.classList.contains("presenting"));
  kd("Escape");
  check("Escape exits Present mode", !doc.body.classList.contains("presenting"));

  // ── Canvas/SVG generation (live API) ──
  w.eval("goTo(7)"); // topic 3 visual slide
  console.log("DEBUG after goTo(6): cur=" + cur() + " va3=" + !!doc.getElementById("va-3") + " vp=" + (doc.getElementById("viewport").innerHTML || "").substring(0, 120));
  w.selectType(3, "image");
  await w.generateVisual(3);
  check("canvas SVG generated into slide", !!(doc.getElementById("va-3") || { querySelector: () => null }).querySelector("svg"));

  // ── Animation blueprint playback (live API) ──
  w.eval("goTo(9)"); // topic 4 visual
  w.selectType(4, "auto");
  check("Auto type selected by default", doc.querySelector("#types-4 .type-btn.selected").dataset.type === "auto");
  check("recommendation chip shows reasoning", (doc.getElementById("reco-4") || { innerHTML: "" }).innerHTML.length > 10);
  w.selectType(4, "animation");
  await w.generateVisual(4);
  await new Promise(r => setTimeout(r, 2500));
  check("motion stage rendered", !!doc.getElementById("ae-wrap-4"));
  check("components placed on stage", doc.querySelectorAll("#ae-stage-4 .ae-node").length > 0);
  const eng = w.eval("window['_ae_4']");
  check("engine built with scenes", eng && eng.scenes && eng.scenes.length > 0);
  check("explanations built for every component", eng && eng.compIds.every(id => eng.explanations[id]));
  // let it play
  await new Promise(r => setTimeout(r, 2500));
  const revealed = doc.querySelectorAll("#ae-stage-4 .ae-node.revealed").length;
  check("components animated in over time (" + revealed + " revealed)", revealed > 0);
  check("progress bar advancing", parseFloat(doc.getElementById("ae-fill-4").style.width) > 0);
  // click-to-inspect
  if (eng.compIds.length > 0) {
    w.eval(`aeInspect(4, '${eng.compIds[0]}')`);
    check("inspector opens on component click", doc.getElementById("ae-insp-4").classList.contains("open"));
    check("inspector shows explanation text", doc.getElementById("ae-inspbody-4").textContent.length > 30);
    w.eval("aeCloseInspector(4)");
    check("inspector closes", !doc.getElementById("ae-insp-4").classList.contains("open"));
  }
  // pause / seek / speed
  w.eval("aeTogglePlay(4)");
  check("pause works", w.eval("window['_ae_4'].playing") === false);
  w.eval("aeSeek(4, 0)");
  check("seek to start resets state", w.eval("window['_ae_4'].t") === 0);
  w.eval("aeSetSpeed(4, 2)");
  check("speed control works", w.eval("window['_ae_4'].speed") === 2);

  // ── Simulation session (live API) ──
  w.eval("goTo(11)"); // topic 5 visual
  w.selectType(5, "simulation");
  try {
    await w.generateVisual(5);
    check("simulation step UI rendered", (doc.getElementById("sim-session-5") || {}).innerHTML > "");
  } catch (e) {
    check("simulation step UI rendered (" + e.message + ")", false);
  }

  // ── Video render (live API, ~15s) ──
  w.eval("goTo(13)"); // topic 6 visual
  w.selectType(6, "video");
  try {
    await w.generateVisual(6);
    const va6 = doc.getElementById("va-6");
    check("video player or storyboard rendered", !!va6.querySelector("video") || va6.innerHTML.includes("scenes"));
  } catch (e) {
    check("video player or storyboard rendered (" + e.message + ")", false);
  }

  // ── Large deck scalability (100 topics -> 200 slides, client logic) ──
  w.eval(`
    topics = Array.from({ length: 100 }, (_, i) => ({ index: i, title: "Topic " + i, description: "Desc " + i }));
    slides = [];
    topics.forEach((t, i) => { slides.push({ kind: "concept", topicIdx: i }); slides.push({ kind: "visual", topicIdx: i }); });
    buildThumbnails();
  `);
  check("200-slide deck: all thumbnails built", doc.querySelectorAll(".thumb").length === 200);
  w.eval("goTo(150, false)");
  check("200-slide deck: jump to 151 works", counterTxt() === "151/200");
  check("200-slide deck: active thumb marked", doc.getElementById("thumb-150").classList.contains("active"));
  kd("ArrowRight");
  kd("End");
  check("200-slide deck: End reaches slide 200", cur() === 199 && doc.getElementById("nextBtn").disabled === true);
  kd("Home");
  check("200-slide deck: Home returns to slide 1", cur() === 0);

  console.log("\nRESULT: " + pass + " passed, " + fail + " failed");
  process.exit(fail > 0 ? 1 : 0);
}

main().catch(e => { console.error("TEST CRASH:", e); process.exit(1); });
