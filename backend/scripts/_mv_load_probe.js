const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs");
const BASE = "http://localhost:8000";
const TOKEN = fs.readFileSync(process.env.TOKEN_FILE, "utf8").trim();

(async () => {
  const pageHtml = await (await fetch(BASE + "/frontend/player.html")).text();
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => console.log("JSDOM_ERROR:", e.message, ((e.detail && e.detail.stack) || "").split("\n").slice(0, 4).join(" | ")));
  vc.on("error", (...a) => console.log("CONSOLE_ERROR:", a.join(" ")));
  const dom = new JSDOM(pageHtml, {
    url: BASE + "/frontend/player.html",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = async (u, o) => {
        const f = u.startsWith("http") ? u : BASE + u;
        o = o || {};
        o.headers = Object.assign({}, o.headers, { Authorization: "Bearer " + TOKEN });
        return fetch(f, o);
      };
      w.localStorage.setItem("access_token", TOKEN);
    },
  });
  await new Promise(r => setTimeout(r, 4000));
  try {
    const t = dom.window.eval("typeof slides");
    console.log("typeof slides:", t, t !== "undefined" ? "len=" + dom.window.eval("slides.length") : "");
    console.log("typeof buildThumbnails:", dom.window.eval("typeof buildThumbnails"));
  } catch (e) {
    console.log("EVAL_FAIL:", e.message);
  }
  process.exit(0);
})();
