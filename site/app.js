/* IdeaForge frontend — vanilla JS, no framework, no build step.
   Loads data/ideas.json, then filters / searches / sorts client-side. */

(() => {
  "use strict";

  // ideas.json lives in ../data when serving the repo root, or ./data when the
  // deploy bundles it alongside index.html. Try both so local + Pages both work.
  const DATA_CANDIDATES = ["data/ideas.json", "../data/ideas.json"];

  const els = {
    cards: document.getElementById("cards"),
    status: document.getElementById("status"),
    search: document.getElementById("search"),
    difficulty: document.getElementById("filter-difficulty"),
    domain: document.getElementById("filter-domain"),
    tag: document.getElementById("filter-tag"),
    sort: document.getElementById("sort"),
    reset: document.getElementById("reset"),
    generated: document.getElementById("generated"),
    template: document.getElementById("card-template"),
    themeToggle: document.getElementById("theme-toggle"),
    showMore: document.getElementById("show-more"),
  };

  const PAGE_SIZE = 60;        // cap initial render; reveal the rest on demand
  let ALL = [];
  let view = [];               // current filtered/sorted list
  let visible = PAGE_SIZE;     // how many of `view` are currently rendered

  // ---------- inline Lucide SVG icons (no emojis, no icon font) ----------
  const svg = (paths) =>
    `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

  const ICONS = {
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'),
    moon: svg('<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'),
    trendingUp: svg('<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>'),
    github: svg('<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C4 2 3 2 3 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 2 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/>'),
    devto: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/>'),
    hackernews: svg('<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>'),
    link: svg('<path d="M7 7h10v10"/><path d="M7 17 17 7"/>'),
  };
  const SOURCE_ICON = { github: ICONS.github, devto: ICONS.devto, hackernews: ICONS.hackernews };

  // ---------- theme ----------
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    els.themeToggle.innerHTML = theme === "dark" ? ICONS.sun : ICONS.moon;
    try { localStorage.setItem("ideaforge-theme", theme); } catch (_) {}
  }
  function initTheme() {
    let theme = "dark";
    try { theme = localStorage.getItem("ideaforge-theme") || theme; } catch (_) {}
    applyTheme(theme);
    els.themeToggle.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  }

  // ---------- data load ----------
  async function loadData() {
    for (const url of DATA_CANDIDATES) {
      try {
        const res = await fetch(url, { cache: "no-cache" });
        if (res.ok) return await res.json();
      } catch (_) { /* try next candidate */ }
    }
    throw new Error("could not load ideas.json");
  }

  // ---------- search ----------
  // Multi-term matching: every whitespace-separated term must match the idea.
  // A term matches if it's a substring of the haystack OR is within one edit
  // (insert/delete/substitute) of some word in it — light typo tolerance without
  // the false positives a loose subsequence matcher produces.
  function withinOneEdit(term, word) {
    if (term === word) return true;
    const la = term.length, lb = word.length;
    if (Math.abs(la - lb) > 1) return false;
    let i = 0, j = 0, edits = 0;
    while (i < la && j < lb) {
      if (term[i] === word[j]) { i++; j++; continue; }
      if (++edits > 1) return false;
      if (la > lb) i++;            // deletion from term
      else if (la < lb) j++;       // insertion into term
      else { i++; j++; }           // substitution
    }
    return edits + (la - i) + (lb - j) <= 1;
  }

  function termMatches(term, haystack, words) {
    if (haystack.includes(term)) return true;
    if (term.length < 4) return false;            // only fuzz longer terms
    return words.some((w) => withinOneEdit(term, w));
  }

  function haystackOf(idea) {
    return `${idea.title} ${idea.description || ""} ${(idea.tags || []).join(" ")}`.toLowerCase();
  }

  function matchesQuery(idea, q) {
    if (!q) return true;
    const hay = haystackOf(idea);
    const words = hay.split(/[^a-z0-9]+/).filter(Boolean);
    return q.toLowerCase().split(/\s+/).filter(Boolean)
      .every((term) => termMatches(term, hay, words));
  }

  // Relevance score for ordering search results: title hits beat body hits.
  function searchRank(idea, q) {
    const title = idea.title.toLowerCase();
    return q.toLowerCase().split(/\s+/).filter(Boolean)
      .reduce((s, t) => s + (title.includes(t) ? 2 : 1), 0);
  }

  // ---------- filter population ----------
  function populateFilters(ideas) {
    const domains = [...new Set(ideas.map((i) => i.domain).filter(Boolean))].sort();
    const tags = [...new Set(ideas.flatMap((i) => i.tags || []))].sort();
    for (const d of domains) addOption(els.domain, d);
    for (const t of tags) addOption(els.tag, t);
  }
  function addOption(select, value) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = value;
    select.appendChild(o);
  }

  // ---------- render ----------
  function currentView() {
    const q = els.search.value.trim();
    const diff = els.difficulty.value;
    const dom = els.domain.value;
    const tag = els.tag.value;
    const sort = els.sort.value;

    let list = ALL.filter((i) =>
      (!diff || i.difficulty === diff) &&
      (!dom || i.domain === dom) &&
      (!tag || (i.tags || []).includes(tag)) &&
      matchesQuery(i, q)
    );

    if (q) {
      list.sort((a, b) => searchRank(b, q) - searchRank(a, q) || (b.score || 0) - (a.score || 0));
    } else if (sort === "recency") {
      list.sort((a, b) => (b.last_seen || "").localeCompare(a.last_seen || ""));
    } else {
      list.sort((a, b) => (b.score || 0) - (a.score || 0));
    }
    return list;
  }

  // Full re-filter (resets paging to the first page).
  function render() {
    view = currentView();
    visible = PAGE_SIZE;
    els.status.textContent = view.length
      ? `${view.length} idea${view.length === 1 ? "" : "s"}`
      : "No ideas match your filters.";
    els.cards.innerHTML = "";
    paint();
  }

  // Render up to `visible` cards from `view` and manage the Show-more button.
  function paint() {
    const frag = document.createDocumentFragment();
    for (const idea of view.slice(els.cards.childElementCount, visible)) {
      frag.appendChild(renderCard(idea));
    }
    els.cards.appendChild(frag);

    const remaining = view.length - visible;
    els.showMore.hidden = remaining <= 0;
    if (remaining > 0) els.showMore.textContent = `Show more (${remaining} more)`;
  }

  function renderCard(idea) {
    const node = els.template.content.cloneNode(true);

    const diff = node.querySelector(".difficulty");
    diff.textContent = idea.difficulty || "—";
    diff.dataset.level = idea.difficulty || "";

    node.querySelector(".domain").textContent = idea.domain || "—";

    const score = node.querySelector(".score");
    score.innerHTML = ICONS.trendingUp;            // static SVG, no user data
    score.append(document.createTextNode((idea.score ?? 0).toFixed(2)));
    score.title = "Computed rank score";

    node.querySelector(".card-title").textContent = idea.title || "Untitled";
    node.querySelector(".card-desc").textContent = idea.description || "";

    const tagsWrap = node.querySelector(".card-tags");
    for (const t of (idea.tags || []).slice(0, 6)) {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = t;
      span.title = `Filter by "${t}"`;
      span.addEventListener("click", () => { els.tag.value = t; render(); });
      tagsWrap.appendChild(span);
    }

    const srcWrap = node.querySelector(".card-sources");
    for (const s of idea.sources || []) {
      const a = document.createElement("a");
      a.className = "source-link";
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.title = `${s.platform} — ${s.engagement_score || 0} engagement`;
      // Icon is a trusted static constant; platform/engagement are appended as text nodes.
      a.innerHTML = SOURCE_ICON[s.platform] || ICONS.link;
      a.append(document.createTextNode(s.platform));
      if (s.engagement_score) {
        const eng = document.createElement("span");
        eng.className = "eng";
        eng.textContent = s.engagement_score;
        a.append(eng);
      }
      srcWrap.appendChild(a);
    }
    return node;
  }

  // ---------- events ----------
  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  function wireEvents() {
    els.search.addEventListener("input", debounce(render, 120));
    [els.difficulty, els.domain, els.tag, els.sort].forEach((el) =>
      el.addEventListener("change", render));
    els.reset.addEventListener("click", () => {
      els.search.value = "";
      els.difficulty.value = els.domain.value = els.tag.value = "";
      els.sort.value = "score";
      render();
    });
    els.showMore.addEventListener("click", () => {
      visible += PAGE_SIZE;
      paint();
    });
    // "/" focuses search (ignored while typing in a field).
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) {
        e.preventDefault();
        els.search.focus();
      }
    });
  }

  // ---------- boot ----------
  async function init() {
    initTheme();
    wireEvents();
    try {
      const data = await loadData();
      ALL = data.ideas || [];
      if (data.generated_at) els.generated.textContent = `updated ${data.generated_at}`;
      populateFilters(ALL);
      render();
    } catch (err) {
      els.status.textContent =
        "Couldn't load ideas.json. Run the pipeline (py -m scraper.pipeline) or serve from the repo root.";
      console.error(err);
    }
  }

  init();
})();
