import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { test } from "node:test";
const require = createRequire(
  new URL("../../../frontend/package.json", import.meta.url),
);
const { JSDOM } = require("jsdom");
const base = new URL("../pages/gallery/", import.meta.url);
const templates = JSON.parse(
  readFileSync(new URL("../templates.json", import.meta.url), "utf8"),
);

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 20));
}

const task = {
  id: "task-one",
  prompt: "a cat",
  mode: "generate",
  status: "success",
  size: "1024x1024",
  image_count: 1,
  created: 100,
  finished: 110,
  images: [{ id: "asset-one", name: "cat.png", available: true }],
  source: "provider",
};

const stats = {
  total_tasks: 1,
  uses: 1,
  active_users: 1,
  success: 1,
  failed: 0,
  cache_hits: 0,
  output_images: 1,
  edits: 0,
  series: [
    { date: "2026-09-09", uses: 0, active_users: 0, success: 0, failed: 0 },
    { date: "2026-09-10", uses: 1, active_users: 1, success: 1, failed: 0 },
  ],
};

/** Mount the page against a stub bridge that reports `locale`, the way the host does. */
function mount(locale, { historyItems = [task] } = {}) {
  const dom = new JSDOM(readFileSync(new URL("index.html", base), "utf8"), {
    runScripts: "outside-only",
    url: "https://plugin.example/",
  });
  const { window } = dom;
  const calls = [];
  const listeners = [];
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  window.CapstonePluginPage = {
    ready: async () => ({ locale }),
    onContext: (handler) => listeners.push(handler),
    dataUrl: async () => "data:image/png;base64,iVBORw0KGgo=",
    apiGet: async (endpoint, query) => {
      calls.push({ endpoint, query });
      if (endpoint === "templates") return { items: templates };
      if (endpoint === "gallery")
        return { items: [{ id: "asset-one", name: "cat.png", task_id: "task-one" }] };
      if (endpoint === "history")
        return { items: historyItems, total: historyItems.length, page: 1 };
      if (endpoint === "stats") return stats;
      throw new Error(endpoint);
    },
    apiPost: async (endpoint, body) => {
      calls.push({ endpoint, body });
      return { id: "submitted-task", status: "queued" };
    },
  };
  window.eval(readFileSync(new URL("app.js", base), "utf8"));
  return { window, doc: window.document, calls, listeners };
}

test("studio UI applies templates, selects references, submits edits, filters history and charts usage", async () => {
  const { window, doc, calls } = mount("zh-CN");
  try {
    await settle();
    assert.equal(doc.querySelectorAll(".template-card").length, 12);
    doc.querySelector('[data-tab="templates"]').click();
    doc.querySelector(".template-card button").click();
    await settle();
    assert.match(doc.getElementById("prompt").value, /商品/);
    assert.equal(doc.getElementById("create").hidden, false);
    doc
      .getElementById("generate")
      .dispatchEvent(new window.Event("submit", { cancelable: true }));
    await settle();
    assert.match(doc.getElementById("notice").textContent, /替换/);
    assert.equal(calls.filter((c) => c.endpoint === "tasks").length, 0);
    doc.querySelector("#grid button").click();
    await settle();
    assert.equal(doc.getElementById("reference-preview").hidden, false);
    doc.getElementById("prompt").value = "Change the background to blue";
    doc
      .getElementById("generate")
      .dispatchEvent(new window.Event("submit", { cancelable: true }));
    await settle();
    const submit = calls.find((c) => c.endpoint === "tasks");
    assert.equal(submit.body.reference, "asset-one");
    assert.equal(submit.body.parent_id, "task-one");
    assert.equal(submit.body.image_count, 1);
    doc.querySelector('[data-tab="history"]').click();
    await settle();
    assert.equal(doc.querySelectorAll(".task").length, 1);
    doc.getElementById("status-filter").value = "error";
    doc.getElementById("status-filter").dispatchEvent(new window.Event("change"));
    await settle();
    assert.equal(
      calls.filter((c) => c.endpoint === "history").at(-1).query.status,
      "error",
    );
    doc.querySelector('[data-tab="analytics"]').click();
    await settle();
    assert.equal(doc.querySelectorAll(".stat").length, 8);
    assert.ok(doc.querySelector("#chart svg polyline"));
    assert.equal(doc.querySelectorAll("#daily-table tbody tr").length, 2);
    doc.getElementById("clear-reference").click();
    assert.equal(doc.getElementById("reference-preview").hidden, true);
  } finally {
    window.close();
  }
});

test("studio UI renders in the locale the host reports and follows a language switch", async () => {
  const { window, doc, listeners } = mount("en");
  try {
    await settle();
    assert.equal(doc.documentElement.getAttribute("lang"), "en");
    assert.equal(doc.querySelector('[data-tab="create"]').textContent, "Create");
    assert.equal(doc.getElementById("mode-title").textContent, "Start creating");
    assert.match(doc.getElementById("prompt").getAttribute("placeholder"), /Describe the subject/);
    assert.match(doc.querySelector(".template-card p").textContent, /Shoot a hero product image/);
    // No Chinese characters anywhere on an English page.
    assert.ok(!/[一-鿿]/.test(doc.body.textContent), doc.body.textContent);

    assert.equal(listeners.length, 1);
    listeners[0]({ locale: "zh-CN" });
    await settle();
    assert.equal(doc.documentElement.getAttribute("lang"), "zh-CN");
    assert.equal(doc.querySelector('[data-tab="create"]').textContent, "创作");
    assert.match(doc.querySelector(".template-card p").textContent, /电商主图/);
  } finally {
    window.close();
  }
});

test("studio UI turns a backend message code into text the reader can act on", async () => {
  const failed = { ...task, id: "task-two", status: "error", error: "task_failed" };
  const english = mount("en", { historyItems: [failed] });
  try {
    await settle();
    english.doc.querySelector('[data-tab="history"]').click();
    await settle();
    const shown = english.doc.querySelector(".task .error").textContent;
    assert.equal(shown, "The task failed or was interrupted. Check the service settings and retry.");
    assert.ok(!shown.includes("task_failed"));
  } finally {
    english.window.close();
  }

  const chinese = mount("zh", { historyItems: [failed] });
  try {
    await settle();
    chinese.doc.querySelector('[data-tab="history"]').click();
    await settle();
    assert.match(chinese.doc.querySelector(".task .error").textContent, /任务失败或执行中断/);
  } finally {
    chinese.window.close();
  }
});

test("every markup i18n key renders in both languages", async () => {
  const markup = readFileSync(new URL("index.html", base), "utf8");
  const keys = [...markup.matchAll(/data-i18n(?:-placeholder|-aria-label|-alt)?="([^"]+)"/g)].map(
    (match) => match[1],
  );
  assert.ok(keys.length > 20, `expected many keys, found ${keys.length}`);

  for (const locale of ["en", "zh"]) {
    const { window, doc } = mount(locale);
    try {
      await settle();
      // A key missing from the dictionary would render as the key itself or as nothing.
      for (const el of doc.querySelectorAll("[data-i18n]")) {
        const text = el.textContent.trim();
        assert.ok(text, `${locale}: ${el.dataset.i18n} rendered empty`);
        assert.notEqual(text, el.dataset.i18n, `${locale}: ${el.dataset.i18n} has no translation`);
      }
      for (const [attribute, dataset] of [
        ["placeholder", "i18nPlaceholder"],
        ["aria-label", "i18nAriaLabel"],
        ["alt", "i18nAlt"],
      ]) {
        for (const el of doc.querySelectorAll(`[data-${attribute === "aria-label" ? "i18n-aria-label" : "i18n-" + attribute}]`)) {
          const value = el.getAttribute(attribute);
          assert.ok(value, `${locale}: ${el.dataset[dataset]} rendered no ${attribute}`);
          assert.notEqual(value, el.dataset[dataset], `${locale}: ${el.dataset[dataset]} has no translation`);
        }
      }
    } finally {
      window.close();
    }
  }
});

test("the two dictionaries cover exactly the same keys", () => {
  // Trim every line: the working tree may hold CRLF endings, and a stray carriage
  // return would silently defeat an exact match and let page code into the slice.
  const lines = readFileSync(new URL("app.js", base), "utf8")
    .split(String.fromCharCode(10))
    .map((line) => line.replace(/\s+$/, ""));
  const zhAt = lines.findIndex((line) => line.trim() === "zh: {");
  const enAt = lines.findIndex((line) => line.trim() === "en: {");
  // The STRINGS object closes on the first `};` at two spaces; page code follows it.
  const endAt = lines.findIndex((line, index) => index > enAt && line === "  };");
  assert.ok(zhAt >= 0 && enAt > zhAt && endAt > enAt);
  const keysIn = (from, to) =>
    new Set(
      lines
        .slice(from, to)
        .map((line) => /^ {6}"([^"]+)":/.exec(line))
        .filter(Boolean)
        .map((match) => match[1]),
    );
  const zhKeys = keysIn(zhAt, enAt);
  const enKeys = keysIn(enAt, endAt);
  assert.ok(zhKeys.size > 80, `expected a full dictionary, found ${zhKeys.size}`);
  assert.deepEqual([...zhKeys].sort(), [...enKeys].sort());
});
