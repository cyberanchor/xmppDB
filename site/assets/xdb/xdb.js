// Theme switch on every page; search, filters, sorting and export for the server table on the home page.
// The table is complete without this script. Values are read from the cells once; filters and sorting live in
// the address, so a view can be linked: #state=online&reg=open&sort=auth&dir=asc
(() => {
  // Light / dark: the button flips the current look and saves it; without a saved choice the system decides.
  const html = document.documentElement;
  const dark = () => html.dataset.theme ? html.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.querySelectorAll("[data-xdb-theme]").forEach((b) => b.addEventListener("click", () => {
    html.dataset.theme = dark() ? "light" : "dark";
    try { localStorage.setItem("xdb-theme", html.dataset.theme); } catch (e) { /* storage blocked */ }
  }));

  const root = document.querySelector(".xdb-servers");
  if (!root) return;
  const $ = (sel) => root.querySelector(sel);
  const list = $("[data-xdb-list]");
  const empty = $(".xdb-empty");  // shown when no row matches
  const count = $("[data-xdb-count]");
  const reset = $("[data-xdb-reset]");
  const q = $("[data-xdb-q]");
  const filters = [...root.querySelectorAll("[data-xdb-f]")]; // <select data-xdb-f="state|reg|cat|country">
  const sortButtons = [...root.querySelectorAll("[data-xdb-sort]")];

  // Sort keys from cell text; "" (no value) always sorts last.
  const FLAG = /^[\u{1F1E6}-\u{1F1FF}]{2}\s*/u;
  const AUTH = ["SCRAM-SHA-512-PLUS", "SCRAM-SHA-256-PLUS", "SCRAM-SHA-1-PLUS", "SCRAM-SHA-512", "SCRAM-SHA-256",
    "SCRAM-SHA-1", "PLAIN", "DIGEST-MD5", "EXTERNAL", "ANONYMOUS"];
  const KIND = {
    text: (s) => s.toLowerCase(),
    country: (s) => s.replace(FLAG, ""),
    yn: (s) => ({ yes: "1", no: "2" })[s] || "",
    eyes: (s) => ({ "5 Eyes": "1", "9 Eyes": "2", "14 Eyes": "3", no: "4" })[s] || "",
    reg: (s) => (s.includes("in-band") ? "1" : s.includes("web") ? "2" : s === "closed" ? "3" : ""),
    auth: (s) => (!s ? "" : AUTH.includes(s) ? String(AUTH.indexOf(s)).padStart(2, "0") : "50"),
  };
  const kinds = sortButtons.map((b) => KIND[b.dataset.xdbSort] || KIND.text);
  const rows = [...list.querySelectorAll("tr[data-st]")].map((el) => {
    const text = [...el.cells].map((td) => td.textContent.trim());
    const keys = text.map((t, i) => (kinds[i] ? kinds[i](t) : t));
    const reg = keys[5] === "1" ? "open" : keys[5] === "2" ? "web" : keys[5] === "3" ? "closed" : "";
    return {
      el, keys, name: keys[0],
      f: { state: el.dataset.st, reg, cat: text[8], country: keys[1] },
      search: [keys[0], keys[1].toLowerCase(), keys[9], el.dataset.sw || ""].join(" "),
    };
  });
  const sortIndex = (key) => sortButtons.findIndex((b) => b.dataset.xdbKey === key);
  let sort = { key: "server", dir: "asc" };

  const match = (row, key, want) => {
    if (!want) return true;
    const have = row.f[key] || "";
    if (key === "cat") return want === "listed" ? have !== "" : want === "none" ? have === "" : have === want;
    return have === want;
  };

  const readHash = () => {
    const p = new URLSearchParams(location.hash.slice(1));
    q.value = p.get("q") || "";
    filters.forEach((f) => {
      const v = p.get(f.dataset.xdbF) || "";
      f.value = [...f.options].some((o) => o.value === v) ? v : "";
    });
    const key = p.get("sort");
    sort = sortIndex(key) >= 0 ? { key, dir: p.get("dir") === "desc" ? "desc" : "asc" } : { key: "server", dir: "asc" };
  };

  const writeHash = () => {
    const p = new URLSearchParams();
    if (q.value.trim()) p.set("q", q.value.trim());
    filters.forEach((f) => f.value && p.set(f.dataset.xdbF, f.value));
    if (sort.key !== "server" || sort.dir !== "asc") { p.set("sort", sort.key); p.set("dir", sort.dir); }
    const hash = p.toString();
    history.replaceState(null, "", hash ? "#" + hash : location.pathname + location.search);
  };

  const apply = () => {
    const terms = q.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const row of rows) {
      const ok = filters.every((f) => match(row, f.dataset.xdbF, f.value)) && terms.every((t) => row.search.includes(t));
      row.el.hidden = !ok;
      if (ok) shown++;
    }
    empty.hidden = shown > 0;
    count.textContent = shown;
    reset.hidden = !(q.value.trim() || filters.some((f) => f.value));
    sortButtons.forEach((b) => (b.dataset.xdbKey === sort.key ? b.setAttribute("data-dir", sort.dir) : b.removeAttribute("data-dir")));
  };

  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const order = () => {
    const i = sortIndex(sort.key);
    const sign = sort.dir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      const x = a.keys[i], y = b.keys[i];
      if (!x !== !y) return x ? -1 : 1;
      return collator.compare(x, y) * sign || collator.compare(a.name, b.name);
    });
    const frag = document.createDocumentFragment();
    rows.forEach((r) => frag.appendChild(r.el));
    list.appendChild(frag);
  };

  const update = () => { apply(); writeHash(); };

  sortButtons.forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.xdbKey;
    sort = { key, dir: sort.key === key && sort.dir === "asc" ? "desc" : "asc" };
    order();
    update();
  }));
  filters.forEach((f) => f.addEventListener("change", update));
  let timer;
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(update, 150); });
  reset.addEventListener("click", () => { q.value = ""; filters.forEach((f) => (f.value = "")); update(); });

  // Links in the summary line set one filter: <a data-xdb-set="reg=open">
  document.querySelectorAll("[data-xdb-set]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    const [key, value] = a.dataset.xdbSet.split("=");
    q.value = "";
    filters.forEach((f) => (f.value = f.dataset.xdbF === key ? value : ""));
    update();
    root.scrollIntoView({ behavior: "smooth", block: "start" });
  }));

  // Export: the domains of the rows shown, one per line.
  $("[data-xdb-export]").addEventListener("click", () => {
    const names = rows.filter((r) => !r.el.hidden).map((r) => r.name);
    const blob = new Blob([names.join("\n") + "\n"], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "xmpp-domains.txt";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  });

  // "/" focuses the search box, Escape clears it.
  document.addEventListener("keydown", (e) => {
    const el = document.activeElement;
    const typing = el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
    if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) { e.preventDefault(); q.focus(); }
  });
  q.addEventListener("keydown", (e) => { if (e.key === "Escape" && q.value) { q.value = ""; update(); } });
  window.addEventListener("hashchange", () => { readHash(); order(); apply(); });

  readHash();
  if (sort.key !== "server" || sort.dir !== "asc") order();
  apply();
})();
