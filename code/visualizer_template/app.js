/**
 * Hebrew Astrological Manuscripts 1250-1450 - Academic Visualizer & Facsimile Reader
 * English Interface with Scholarly Typography & Multilingual Support
 */

document.addEventListener("DOMContentLoaded", () => {
  const data = window.SPHAERA_DATA;
  if (!data) {
    console.error("SPHAERA_DATA dataset is not loaded!");
    return;
  }

  // Application State
  const state = {
    activeTab: "tab-catalogue",
    catalogueFilters: {
      search: "",
      century: "",
      script: "",
      library: "",
      downloadedOnly: false,
      queryTerm: ""
    },
    reader: {
      activeMmsId: null,
      activePageIndex: 0,
      zoomLevel: 1.0
    },
    map: {
      leafletInstance: null,
      layerType: "writing", // "writing" or "holding"
      activePeriod: null,
      markersLayer: null
    },
    personsSearch: "",
    personsRoleFilter: "",
    catalogueSort: { key: "", asc: true },
    personsSort: { key: "count", asc: false },
    personsOpen: null
  };

  // -----------------------------------------------------------
  // 0. Initialize Masthead Global Statistics
  // -----------------------------------------------------------
  document.getElementById("stat-total-ms").textContent = data.stats.total_manuscripts;
  // Books = physical codices; several catalogue records can describe works bound in the same book
  const s = data.stats;
  document.getElementById("stat-downloaded-ms").textContent = s.downloaded_books !== undefined
    ? `${s.downloaded_books} books, ${s.downloaded_book_pages.toLocaleString()} pages (${s.downloaded_manuscripts} catalogue records)`
    : `${s.downloaded_manuscripts} (${s.total_downloaded_pages.toLocaleString()} pages)`;
  document.getElementById("stat-open-catalog").textContent = s.open_books !== undefined
    ? `${s.open_books} books, ${s.open_book_pages.toLocaleString()} pages (${s.total_open_in_catalog} catalogue records)`
    : `${s.total_open_in_catalog} (${s.total_pages_in_catalog.toLocaleString()} pages)`;
  const persons = data.persons || [];
  const roleCounts = {};
  persons.forEach(p => { roleCounts[p.role] = (roleCounts[p.role] || 0) + 1; });
  const roleShort = { "Author": "authors", "Translator": "translators", "Commentator": "commentators",
                      "Scribe / Copyist": "scribes", "Associated Person / Owner": "owners & others" };
  const roleText = Object.keys(roleShort).filter(r => roleCounts[r])
    .concat(Object.keys(roleCounts).filter(r => !roleShort[r]))
    .map(r => `${roleCounts[r]} ${roleShort[r] || r}`).join(", ");
  document.getElementById("stat-persons").textContent = roleText ? `${persons.length} (${roleText})` : persons.length;
  document.getElementById("stat-places").textContent = (data.places || []).length;
  const homeIllustrations = data.illustrations || [];
  const illustrationMss = new Set(homeIllustrations.map(r => r.mms_id)).size;
  document.getElementById("stat-illustrations").textContent =
    `${homeIllustrations.length.toLocaleString()} (in ${illustrationMss} manuscripts)`;
  const repeatingGroups = ((data.clusters && data.clusters.clusters) || []).filter(c => c.label.startsWith("repeating"));
  const acrossGroups = repeatingGroups.filter(c => c.n_manuscripts > 1).length;
  document.getElementById("stat-clusters").textContent = data.clusters
    ? `${repeatingGroups.length} repeating groups (${acrossGroups} across manuscripts)`
    : "not computed yet";

  // -----------------------------------------------------------
  // 1. Navigation & Tab Switching
  // -----------------------------------------------------------
  const navTabs = document.querySelectorAll("#main-nav .nav-tab");
  const tabPanes = document.querySelectorAll(".tab-pane");

  function switchTab(targetId) {
    state.activeTab = targetId;
    navTabs.forEach(t => t.classList.toggle("active", t.dataset.tab === targetId));
    tabPanes.forEach(p => p.classList.toggle("active", p.id === targetId));

    if (targetId === "tab-map") {
      setTimeout(() => {
        if (state.map.leafletInstance) {
          state.map.leafletInstance.invalidateSize();
        } else {
          initMap();
        }
      }, 100);
    } else if (targetId === "tab-all-visuals") {
      // Initialize visuals gallery and clusters
      if (window.initAllVisuals) {
        window.initAllVisuals();
      }
    }
    state.activeTab = targetId;
    navTabs.forEach(t => t.classList.toggle("active", t.dataset.tab === targetId));
    tabPanes.forEach(p => p.classList.toggle("active", p.id === targetId));

    if (targetId === "tab-map") {
      setTimeout(() => {
        if (state.map.leafletInstance) {
          state.map.leafletInstance.invalidateSize();
        } else {
          initMap();
        }
      }, 100);
    }
  }

  navTabs.forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // -----------------------------------------------------------
  // 2. Tab 1: Catalogue & Filtering
  // -----------------------------------------------------------
  const catalogueSearch = document.getElementById("catalogue-search");
  const filterCentury = document.getElementById("filter-century");
  const filterScript = document.getElementById("filter-script");
  const filterLibrary = document.getElementById("filter-library");
  const filterDownloaded = document.getElementById("filter-downloaded-only");
  const queryChipsContainer = document.getElementById("query-chips");
  const manuscriptsGrid = document.getElementById("catalogue-table-body");
  const countActive = document.getElementById("filter-count-active");
  const countTotal = document.getElementById("filter-count-total");
  const btnReset = document.getElementById("btn-reset-filters");

  // Populate Century Dropdown
  const centuryKeys = [
    "12th Century (1101–1200)",
    "13th Century (1201–1300)",
    "14th Century (1301–1400)",
    "15th Century (1401–1500)",
    "16th Century (1501–1600)",
    "17th Century (1601–1700)",
    "18th Century (1701–1800)",
    "19th Century (1801–1900)",
    "Unknown Era"
  ];
  centuryKeys.forEach(c => {
    if (data.centuries[c]) {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = `${c} (${data.centuries[c]} MSS)`;
      filterCentury.appendChild(opt);
    }
  });

  // Populate Scripts Dropdown
  const scriptKeys = Object.keys(data.scripts).sort();
  scriptKeys.forEach(s => {
    if (s && s !== "Not Specified") {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = `${s} (${data.scripts[s]})`;
      filterScript.appendChild(opt);
    }
  });

  // Populate Libraries Dropdown
  const libraryNames = Array.from(new Set(data.manuscripts.map(m => m.library).filter(Boolean))).sort();
  libraryNames.forEach(l => {
    const opt = document.createElement("option");
    opt.value = l;
    opt.textContent = l.length > 40 ? l.substring(0, 40) + "..." : l;
    filterLibrary.appendChild(opt);
  });

  // Query Term Chips
  const queryLabels = {
    "": "All Queries",
    "אסטרולוגיה (any field)": "The Hebrew word, anywhere in the catalogue record",
    "Astrology (any field)": "The English word, anywhere in the catalogue record",
    "Astrology (subject heading)": "Subject heading Astrology / אסטרולוגיה only"
  };

  const queryAllChip = document.createElement("button");
  queryAllChip.className = "chip-btn active";
  queryAllChip.textContent = "All Queries";
  queryAllChip.onclick = () => {
    state.catalogueFilters.queryTerm = "";
    document.querySelectorAll("#query-chips .chip-btn").forEach(c => c.classList.remove("active"));
    queryAllChip.classList.add("active");
    renderCatalogue();
  };
  queryChipsContainer.appendChild(queryAllChip);

  Object.keys(data.query_terms).forEach(q => {
    const chip = document.createElement("button");
    chip.className = "chip-btn";
    chip.textContent = `${queryLabels[q] || q} (${data.query_terms[q]})`;
    chip.onclick = () => {
      state.catalogueFilters.queryTerm = q;
      document.querySelectorAll("#query-chips .chip-btn").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      renderCatalogue();
    };
    queryChipsContainer.appendChild(chip);
  });

  // Filtering Logic
  function getFilteredManuscripts() {
    return data.manuscripts.filter(m => {
      // Free text search
      if (state.catalogueFilters.search) {
        const q = state.catalogueFilters.search.toLowerCase();
        const haystack = [
          m.shelfmark,
          m.title,
          m.author,
          m.added_names,
          m.library,
          m.library_city,
          m.place_writing,
          m.colophon,
          m.notes,
          m.subjects
        ].join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }

      // Century
      if (state.catalogueFilters.century && m.century !== state.catalogueFilters.century) {
        return false;
      }

      // Script
      if (state.catalogueFilters.script && !m.script.includes(state.catalogueFilters.script)) {
        return false;
      }

      // Library
      if (state.catalogueFilters.library && m.library !== state.catalogueFilters.library) {
        return false;
      }

      // Downloaded only
      if (state.catalogueFilters.downloadedOnly && !m.has_local_images) {
        return false;
      }

      // Query term
      if (state.catalogueFilters.queryTerm && !m.query_terms.includes(state.catalogueFilters.queryTerm)) {
        return false;
      }

      return true;
    });
  }

  function renderCatalogue() {
    const filtered = getFilteredManuscripts();
    countActive.textContent = filtered.length;
    countTotal.textContent = data.manuscripts.length;

    if (filtered.length === 0) {
      manuscriptsGrid.innerHTML = `
        <tr><td colspan="8" class="table-empty">
          <h3>No manuscripts match your filter criteria</h3>
          <p>Try relaxing your search keywords or resetting the selected filters.</p>
          <button id="btn-empty-reset" class="btn-primary">Reset Filters</button>
        </td></tr>
      `;
      const btnEmptyReset = document.getElementById("btn-empty-reset");
      if (btnEmptyReset) btnEmptyReset.onclick = resetFilters;
      return;
    }

    sortRows(filtered, state.catalogueSort, catalogueSortValue);
    manuscriptsGrid.innerHTML = filtered.map(m => {
      // Images column: local facsimile > Ktiv IIIF > catalogue record only
      let statusHtml = "";
      if (m.has_local_images) {
        statusHtml = `<button class="status-pill downloaded btn-open-reader" data-mms="${m.mms_id}" title="Open the local facsimile in the reader">Read (${m.downloaded_pages_count} pp)</button>`;
      } else if (m.ktiv_link) {
        statusHtml = `<a class="status-pill open-iiif" href="${m.ktiv_link}" target="_blank" rel="noopener noreferrer" title="Open the record on the Ktiv portal">Ktiv ↗</a>`;
      } else {
        statusHtml = `<span class="status-pill catalog-only">Record only</span>`;
      }
      const nIll = illustrationCountByMs[m.mms_id] || 0;

      return `
        <tr class="clickable-row" data-mms="${m.mms_id}" title="Show the full record">
          <td class="cell-shelfmark">${escapeHtml(m.shelfmark || "—")}</td>
          <td class="cell-hebrew" dir="rtl">${escapeHtml(m.title || "")}</td>
          <td dir="auto">${escapeHtml(m.author || "")}</td>
          <td class="cell-nowrap">${escapeHtml(m.century.replace(/ \(.*\)/, ""))}</td>
          <td dir="auto">${escapeHtml(m.place_writing || "")}</td>
          <td>${escapeHtml(m.library_city ? `${m.library}, ${m.library_city}` : m.library)}</td>
          <td class="num">${nIll ? `<button class="link-btn btn-ms-illustrations" data-mms="${m.mms_id}" title="Show this manuscript's illustrations">${nIll}</button>` : ""}</td>
          <td>${statusHtml}</td>
        </tr>
      `;
    }).join("");

    manuscriptsGrid.querySelectorAll(".clickable-row").forEach(row => {
      row.addEventListener("click", () => openManuscriptModal(row.dataset.mms));
    });
    manuscriptsGrid.querySelectorAll(".btn-open-reader").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        openManuscriptInReader(btn.dataset.mms);
      });
    });
    manuscriptsGrid.querySelectorAll(".btn-ms-illustrations").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        illFilterMs.value = btn.dataset.mms;
        illFilterClass.value = "";
        renderIllustrations();
        switchTab("tab-illustrations");
      });
    });
    manuscriptsGrid.querySelectorAll("a.status-pill").forEach(a => {
      a.addEventListener("click", e => e.stopPropagation());
    });
  }

  // Sorting shared by the catalogue and persons tables: click a heading to sort, again to reverse
  function sortRows(rows, sort, valueOf) {
    if (!sort.key) return;
    const dir = sort.asc ? 1 : -1;
    rows.sort((a, b) => {
      const va = valueOf(a, sort.key), vb = valueOf(b, sort.key);
      if (typeof va === "number") return (va - vb) * dir;
      // empty values always last
      if (!va !== !vb) return va ? -1 : 1;
      return String(va).localeCompare(String(vb), undefined, { numeric: true }) * dir;
    });
  }

  function makeSortable(table, sort, render) {
    const headers = table.querySelectorAll("th[data-sort]");
    const mark = () => headers.forEach(th => {
      th.classList.toggle("sorted", th.dataset.sort === sort.key);
      th.dataset.dir = th.dataset.sort === sort.key ? (sort.asc ? "asc" : "desc") : "";
    });
    headers.forEach(th => th.addEventListener("click", () => {
      if (sort.key === th.dataset.sort) {
        sort.asc = !sort.asc;
      } else {
        sort.key = th.dataset.sort;
        sort.asc = !th.classList.contains("num");     // numbers start largest first
      }
      mark();
      render();
    }));
    mark();
  }

  const illustrationCountByMs = {};
  (data.illustrations || []).forEach(il => {
    illustrationCountByMs[il.mms_id] = (illustrationCountByMs[il.mms_id] || 0) + 1;
  });

  function catalogueSortValue(m, key) {
    switch (key) {
      case "illustrations": return illustrationCountByMs[m.mms_id] || 0;
      case "status": return m.has_local_images ? "1" : m.ktiv_link ? "2" : "3";
      case "place": return m.place_writing;
      default: return m[key];
    }
  }

  // Filter Event Listeners
  catalogueSearch.addEventListener("input", e => {
    state.catalogueFilters.search = e.target.value.trim();
    renderCatalogue();
  });

  filterCentury.addEventListener("change", e => {
    state.catalogueFilters.century = e.target.value;
    renderCatalogue();
  });

  filterScript.addEventListener("change", e => {
    state.catalogueFilters.script = e.target.value;
    renderCatalogue();
  });

  filterLibrary.addEventListener("change", e => {
    state.catalogueFilters.library = e.target.value;
    renderCatalogue();
  });

  filterDownloaded.addEventListener("change", e => {
    state.catalogueFilters.downloadedOnly = e.target.checked;
    renderCatalogue();
  });

  function resetFilters() {
    state.catalogueFilters.search = "";
    state.catalogueFilters.century = "";
    state.catalogueFilters.script = "";
    state.catalogueFilters.library = "";
    state.catalogueFilters.downloadedOnly = false;
    state.catalogueFilters.queryTerm = "";

    catalogueSearch.value = "";
    filterCentury.value = "";
    filterScript.value = "";
    filterLibrary.value = "";
    filterDownloaded.checked = false;

    document.querySelectorAll("#query-chips .chip-btn").forEach(c => c.classList.remove("active"));
    queryAllChip.classList.add("active");

    renderCatalogue();
  }

  btnReset.addEventListener("click", resetFilters);

  // -----------------------------------------------------------
  // 3. Tab 2: Facsimile Reader / Viewer
  // -----------------------------------------------------------
  const readerSelect = document.getElementById("reader-ms-select");
  const readerMetaBox = document.getElementById("reader-meta-box");
  const readerThumbnails = document.getElementById("reader-thumbnails");
  const readerActiveInfo = document.getElementById("reader-active-info");
  const readerCounter = document.getElementById("reader-page-counter");
  const readerMainImg = document.getElementById("reader-main-img");
  const btnPrev = document.getElementById("btn-prev-page");
  const btnNext = document.getElementById("btn-next-page");
  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnZoomReset = document.getElementById("btn-zoom-reset");
  const btnViewToggle = document.getElementById("btn-view-toggle");
  const readerViewport = document.getElementById("reader-viewport");
  const readerGallery = document.getElementById("reader-gallery");
  const readerHeader = document.getElementById("reader-ms-header");
  const readerIllPanel = document.getElementById("reader-illustrations");
  readerMetaBox.style.display = "none";   // the full record is shown in readerHeader above the reader
  state.reader.illOnlyThisPage = false;

  // Lookups for the reader header and illustrations panel
  const readerPersonsByMs = {};
  (data.persons || []).forEach(p => p.manuscripts.forEach(id => {
    (readerPersonsByMs[id] = readerPersonsByMs[id] || []).push(p);
  }));
  // illustrations belong to a manuscript folder, which records sharing a codex have in common
  const readerIllByFolder = {};
  (data.illustrations || []).forEach(il => {
    (readerIllByFolder[il.manuscript_folder] = readerIllByFolder[il.manuscript_folder] || []).push(il);
  });
  const readerClusterOf = {};
  ((data.clusters && data.clusters.clusters) || []).forEach(c => c.illustration_ids.forEach(id => { readerClusterOf[id] = c; }));
  const recordsByFolder = {};
  data.manuscripts.filter(m => m.image_folder).forEach(m => {
    (recordsByFolder[m.image_folder] = recordsByFolder[m.image_folder] || []).push(m);
  });
  const folderName = ms => (ms.image_folder || "").split("/").pop();

  state.reader.galleryMode = false;
  state.reader.gallerySize = 220;   // gallery thumbnail width in px, changed with + / -

  const downloadedManuscripts = data.manuscripts.filter(m => m.has_local_images && m.pages.length > 0);

  // Populate Reader Dropdown
  downloadedManuscripts.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.mms_id;
    opt.textContent = `${m.shelfmark} (${m.downloaded_pages_count} pp) — ${m.library}`;
    readerSelect.appendChild(opt);
  });

  function openManuscriptInReader(mmsId, targetPageIndex = 0) {
    switchTab("tab-reader");
    readerSelect.value = mmsId;
    loadManuscriptIntoReader(mmsId, targetPageIndex);
  }

  function loadManuscriptIntoReader(mmsId, initialPageIndex = 0) {
    const ms = downloadedManuscripts.find(m => m.mms_id === mmsId) || downloadedManuscripts[0];
    if (!ms) return;

    state.reader.activeMmsId = ms.mms_id;
    state.reader.activePageIndex = initialPageIndex;
    state.reader.zoomLevel = 1.0;

    renderReaderHeader(ms);
    renderReaderIllustrations(ms);

    // Render metadata summary card
    readerMetaBox.innerHTML = `
      <div style="font-family: var(--font-mono); font-size: 0.82rem; font-weight: 600; color: var(--accent-navy); margin-bottom: 0.25rem;">
        ${escapeHtml(ms.shelfmark)}
      </div>
      <div style="font-family: var(--font-hebrew); font-size: 1.05rem; font-weight: 700; direction: rtl; text-align: right; color: var(--ink-primary); margin-bottom: 0.35rem;">
        ${escapeHtml(ms.title || "")}
      </div>
      <div style="font-size: 0.78rem; color: var(--ink-secondary); line-height: 1.4;">
        <div><strong>Repository:</strong> ${escapeHtml(ms.library)}</div>
        <div><strong>Era:</strong> ${escapeHtml(ms.century)}</div>
        ${ms.place_writing ? `<div><strong>Origin:</strong> ${escapeHtml(ms.place_writing)}</div>` : ""}
        ${ms.colophon ? `<div style="margin-top: 0.35rem; color: var(--accent-crimson); font-style: italic;">Colophon Recorded</div>` : ""}
      </div>
    `;

    // Render thumbnails grid
    readerThumbnails.innerHTML = ms.pages.map((p, idx) => `
      <div class="thumb-item ${idx === initialPageIndex ? 'active' : ''}" data-index="${idx}">
        <img src="../${p.relative_path}" alt="Page ${p.page_number}" loading="lazy">
        <div class="thumb-label">${escapeHtml(p.canvas_label || `Page ${p.page_number}`)}</div>
      </div>
    `).join("");

    // Attach click handlers to thumbnails
    readerThumbnails.querySelectorAll(".thumb-item").forEach(item => {
      item.addEventListener("click", () => {
        const pageIdx = parseInt(item.dataset.index, 10);
        setReaderPage(pageIdx);
      });
    });

    // Render the gallery (all pages, uncropped); clicking a page opens it in single-page view
    readerGallery.innerHTML = ms.pages.map((p, idx) => `
      <div class="gallery-item" data-index="${idx}" title="Open this page">
        <img src="../${p.relative_path}" alt="Page ${p.page_number}" loading="lazy">
        <div class="gallery-label">${escapeHtml(p.canvas_label || `Page ${p.page_number}`)}</div>
      </div>
    `).join("");
    readerGallery.querySelectorAll(".gallery-item").forEach(item => {
      item.addEventListener("click", () => {
        setGalleryMode(false);
        setReaderPage(parseInt(item.dataset.index, 10));
      });
    });

    setReaderPage(initialPageIndex);
    if (state.reader.galleryMode) setGalleryMode(true);
  }

  // Catalogue record above the reader: time and place of production, script, people, illustrations
  function renderReaderHeader(ms) {
    const field = (label, value) => `
      <div class="rmh-field">
        <div class="rmh-label">${label}</div>
        <div class="rmh-value">${value || '<span class="muted">not recorded</span>'}</div>
      </div>`;
    const heb = s => s ? `<span class="hebrew">${escapeHtml(s)}</span>` : "";

    const date = [ms.date_place ? heb(ms.date_place) : "", ms.century && ms.century !== "Unknown Era" ? escapeHtml(ms.century) : ""]
      .filter(Boolean).join("<br>");
    const ills = readerIllByFolder[folderName(ms)] || [];
    const groups = new Set(ills.map(il => readerClusterOf[il.illustration_id])
      .filter(c => c && c.label.startsWith("repeating")));
    const sharedGroups = [...groups].filter(c => c.n_manuscripts > 1).length;
    const illText = ills.length
      ? `${ills.length} found on ${new Set(ills.map(il => il.page_number)).size} pages<br>
         ${groups.size} repeating group${groups.size === 1 ? "" : "s"}${sharedGroups ? `, ${sharedGroups} shared with other manuscripts` : ""}`
      : "";

    const people = (readerPersonsByMs[ms.mms_id] || []);
    const peopleHtml = people.length ? `
      <div class="rmh-people rmh-field">
        <div class="rmh-label">People associated (${people.length})</div>
        <div class="rmh-chips">${people.map(p => `
          <span class="rmh-chip"><span class="name">${escapeHtml(p.name)}</span><span class="role">${escapeHtml(p.role)}</span></span>`).join("")}
        </div>
      </div>` : "";

    const siblings = (recordsByFolder[ms.image_folder] || []).filter(m => m.mms_id !== ms.mms_id);
    const siblingsHtml = siblings.length
      ? `<span>Same physical book as: ${siblings.map(m => `<span class="hebrew">${escapeHtml(m.title || m.mms_id)}</span>`).join(", ")}</span>` : "";

    readerHeader.innerHTML = `
      <div class="rmh-top">
        <div>
          <div class="rmh-shelfmark">${escapeHtml(ms.shelfmark)}</div>
          <div class="rmh-library">${escapeHtml(ms.library)}${ms.library_city ? `, ${escapeHtml(ms.library_city)}` : ""}</div>
        </div>
        <div>
          <div class="rmh-title">${escapeHtml(ms.title || "")}</div>
          ${ms.author ? `<div class="rmh-author">${escapeHtml(ms.author)}</div>` : ""}
        </div>
      </div>
      <div class="rmh-grid">
        ${field("Time of production", date)}
        ${field("Place of writing", heb(ms.place_writing))}
        ${field("Script", heb(ms.script))}
        ${field("Extent", heb(ms.extent) || (ms.downloaded_pages_count ? `${ms.downloaded_pages_count} images` : ""))}
        ${field("Illustrations", illText)}
        ${ms.colophon ? field("Colophon", heb(ms.colophon.length > 160 ? ms.colophon.slice(0, 160) + "…" : ms.colophon)) : ""}
      </div>
      ${peopleHtml}
      <div class="rmh-links">
        ${ms.ktiv_link ? `<a href="${escapeHtml(ms.ktiv_link)}" target="_blank" rel="noopener">Open in Ktiv ↗</a>` : ""}
        <span style="color: var(--ink-dim); font-family: var(--font-mono);">MMS ${escapeHtml(ms.mms_id)}</span>
        ${siblingsHtml}
      </div>
    `;
  }

  // Illustrations of this manuscript below the reader, each with its page and similarity group
  function renderReaderIllustrations(ms) {
    const all = (readerIllByFolder[folderName(ms)] || []).slice()
      .sort((a, b) => parseInt(a.page_number, 10) - parseInt(b.page_number, 10));
    if (!all.length) {
      readerIllPanel.innerHTML = `<div class="rip-head"><span class="rip-title">Illustrations</span></div>
        <p class="empty-note">No illustrations were detected in this manuscript.</p>`;
      return;
    }
    const currentPage = ms.pages[state.reader.activePageIndex];
    const shown = state.reader.illOnlyThisPage && currentPage
      ? all.filter(il => parseInt(il.page_number, 10) === parseInt(currentPage.page_number, 10))
      : all;

    const groupBadge = il => {
      const c = readerClusterOf[il.illustration_id];
      if (!c) return "";
      if (c.label.startsWith("repeating")) {
        const across = c.n_manuscripts > 1;
        return `<button class="rip-group ${across ? "across" : "within"}" data-cluster="${c.cluster_id}"
                  title="Show this group in the Clusters tab">Group ${c.cluster_id} · ${across ? `${c.n_manuscripts} mss` : "this ms only"}</button>`;
      }
      return `<span class="rip-group">${c.cluster_id === 0 ? "no close match" : "not compared"}</span>`;
    };

    readerIllPanel.innerHTML = `
      <div class="rip-head">
        <div>
          <span class="rip-title">Illustrations in this manuscript</span>
          <span class="rip-sub">&nbsp;${all.length} found · click one to open its page · click a group to see similar illustrations</span>
        </div>
        <label class="rip-toggle"><input type="checkbox" id="rip-only-page" ${state.reader.illOnlyThisPage ? "checked" : ""}> Only the current page</label>
      </div>
      <div class="rip-grid">
        ${shown.length ? shown.map(il => `
          <div class="rip-card" data-page="${parseInt(il.page_number, 10)}" title="Open page ${escapeHtml(il.page_number)}">
            <div class="ill-thumb"><img src="../${escapeHtml(il.crop_file)}" alt="${escapeHtml(il.class)}" loading="lazy"></div>
            <div class="rip-caption">
              <div><span class="rip-page">p. ${parseInt(il.page_number, 10)}</span> <span class="rip-class">· ${escapeHtml(il.class)}</span></div>
              ${groupBadge(il)}
            </div>
          </div>`).join("") : `<p class="empty-note">No illustrations on this page.</p>`}
      </div>
    `;

    document.getElementById("rip-only-page").addEventListener("change", e => {
      state.reader.illOnlyThisPage = e.target.checked;
      renderReaderIllustrations(ms);
    });
    readerIllPanel.querySelectorAll(".rip-card").forEach(card => {
      card.addEventListener("click", e => {
        if (e.target.closest(".rip-group")) return;
        const idx = ms.pages.findIndex(p => parseInt(p.page_number, 10) === parseInt(card.dataset.page, 10));
        if (idx < 0) return;
        if (state.reader.galleryMode) setGalleryMode(false);
        setReaderPage(idx);
        document.querySelector(".reader-main-stage").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
    readerIllPanel.querySelectorAll("button.rip-group").forEach(btn => {
      btn.addEventListener("click", () => goToCluster(btn.dataset.cluster));
    });
    markPageIllustrations();
  }

  function markPageIllustrations() {
    const ms = downloadedManuscripts.find(m => m.mms_id === state.reader.activeMmsId);
    const page = ms && ms.pages[state.reader.activePageIndex];
    readerIllPanel.querySelectorAll(".rip-card").forEach(card => {
      card.classList.toggle("on-page", !!page && parseInt(card.dataset.page, 10) === parseInt(page.page_number, 10));
    });
  }

  function goToCluster(clusterId) {
    openClusterDetail(clusterId);
  }

  // Zoom by resizing the image (not CSS scale), so the scrollbars can reach every part of a zoomed page
  function applyZoom() {
    const zoom = state.reader.zoomLevel;
    if (zoom === 1 || !readerMainImg.naturalWidth) {
      readerMainImg.classList.remove("zoomed");
      readerMainImg.style.width = "";
      return;
    }
    const style = getComputedStyle(readerViewport);
    const availW = readerViewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const availH = readerViewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    const fitWidth = Math.min(availW, availH * readerMainImg.naturalWidth / readerMainImg.naturalHeight,
                              readerMainImg.naturalWidth);
    readerMainImg.classList.add("zoomed");
    readerMainImg.style.width = `${Math.round(fitWidth * zoom)}px`;
  }
  readerMainImg.addEventListener("load", applyZoom);

  function setGalleryMode(on) {
    state.reader.galleryMode = on;
    readerGallery.hidden = !on;
    readerViewport.hidden = on;
    readerViewport.style.display = on ? "none" : "";
    btnViewToggle.textContent = on ? "Single page" : "Gallery view";
    btnViewToggle.title = on ? "Back to one page at a time (G)" : "Show all pages at once (G)";
    btnPrev.style.display = btnNext.style.display = on ? "none" : "";
    btnZoomIn.title = on ? "Bigger thumbnails" : "Zoom in";
    btnZoomOut.title = on ? "Smaller thumbnails" : "Zoom out";
    const ms = downloadedManuscripts.find(m => m.mms_id === state.reader.activeMmsId);
    if (on && ms) {
      readerActiveInfo.textContent = `All ${ms.pages.length} pages - click a page to open it`;
      readerGallery.style.setProperty("--gallery-size", `${state.reader.gallerySize}px`);
      const active = readerGallery.querySelector(`.gallery-item[data-index="${state.reader.activePageIndex}"]`);
      readerGallery.querySelectorAll(".gallery-item").forEach(g => g.classList.toggle("active", g === active));
      if (active) active.scrollIntoView({ block: "center" });
    } else {
      setReaderPage(state.reader.activePageIndex);
    }
  }

  btnViewToggle.addEventListener("click", () => setGalleryMode(!state.reader.galleryMode));

  // Drag the zoomed page with the mouse to move around it
  let drag = null;
  readerViewport.addEventListener("mousedown", e => {
    drag = { x: e.clientX, y: e.clientY, left: readerViewport.scrollLeft, top: readerViewport.scrollTop };
    readerViewport.classList.add("dragging");
    e.preventDefault();
  });
  window.addEventListener("mousemove", e => {
    if (!drag) return;
    readerViewport.scrollLeft = drag.left - (e.clientX - drag.x);
    readerViewport.scrollTop = drag.top - (e.clientY - drag.y);
  });
  window.addEventListener("mouseup", () => {
    drag = null;
    readerViewport.classList.remove("dragging");
  });

  function setReaderPage(index) {
    const ms = downloadedManuscripts.find(m => m.mms_id === state.reader.activeMmsId);
    if (!ms || !ms.pages[index]) return;

    state.reader.activePageIndex = index;
    const page = ms.pages[index];

    readerMainImg.src = `../${page.relative_path}`;
    applyZoom();
    if (state.reader.illOnlyThisPage) renderReaderIllustrations(ms);
    else markPageIllustrations();

    readerActiveInfo.textContent = `${page.canvas_label || `Page ${page.page_number}`} (${page.file_name})`;
    readerCounter.textContent = `${index + 1} / ${ms.pages.length}`;

    // Highlight thumbnail
    readerThumbnails.querySelectorAll(".thumb-item").forEach((thumb, idx) => {
      thumb.classList.toggle("active", idx === index);
      if (idx === index) {
        thumb.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    // Button states
    btnPrev.disabled = index <= 0;
    btnNext.disabled = index >= ms.pages.length - 1;
  }

  // Reader Controls
  readerSelect.addEventListener("change", e => {
    loadManuscriptIntoReader(e.target.value, 0);
  });

  btnPrev.addEventListener("click", () => {
    if (state.reader.activePageIndex > 0) {
      setReaderPage(state.reader.activePageIndex - 1);
    }
  });

  btnNext.addEventListener("click", () => {
    const ms = downloadedManuscripts.find(m => m.mms_id === state.reader.activeMmsId);
    if (ms && state.reader.activePageIndex < ms.pages.length - 1) {
      setReaderPage(state.reader.activePageIndex + 1);
    }
  });

  function setGallerySize(px) {
    state.reader.gallerySize = Math.max(120, Math.min(600, px));
    readerGallery.style.setProperty("--gallery-size", `${state.reader.gallerySize}px`);
  }

  btnZoomIn.addEventListener("click", () => {
    if (state.reader.galleryMode) return setGallerySize(state.reader.gallerySize + 60);
    state.reader.zoomLevel = Math.min(4, state.reader.zoomLevel + 0.25);
    applyZoom();
  });

  btnZoomOut.addEventListener("click", () => {
    if (state.reader.galleryMode) return setGallerySize(state.reader.gallerySize - 60);
    state.reader.zoomLevel = Math.max(0.5, state.reader.zoomLevel - 0.25);
    applyZoom();
  });

  btnZoomReset.addEventListener("click", () => {
    if (state.reader.galleryMode) return setGallerySize(220);
    state.reader.zoomLevel = 1.0;
    applyZoom();
  });

  window.addEventListener("resize", applyZoom);

  // Keyboard navigation for reader
  window.addEventListener("keydown", e => {
    if (state.activeTab === "tab-reader") {
      if (e.key === "ArrowLeft") {
        btnPrev.click();
      } else if (e.key === "ArrowRight") {
        btnNext.click();
      } else if (e.key === "+" || e.key === "=") {
        btnZoomIn.click();
      } else if (e.key === "-") {
        btnZoomOut.click();
      } else if (e.key === "0") {
        btnZoomReset.click();
      } else if ((e.key === "g" || e.key === "G") && !["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) {
        btnViewToggle.click();
      }
    }
  });

  // -----------------------------------------------------------
  // 4. Tab 3: Prosopography & Persons Directory
  // -----------------------------------------------------------
  const personsSearch = document.getElementById("persons-search");
  const personsCount = document.getElementById("persons-count");
  const personsRole = document.getElementById("persons-role");
  const personsBody = document.getElementById("persons-table-body");

  [...new Set(data.persons.map(p => p.role))].sort().forEach(role => {
    const opt = document.createElement("option");
    opt.value = role;
    opt.textContent = `${role} (${data.persons.filter(p => p.role === role).length})`;
    personsRole.appendChild(opt);
  });

  function renderPersons() {
    const q = state.personsSearch.toLowerCase();
    const filtered = data.persons.filter(p => {
      if (q && !p.name.toLowerCase().includes(q)) return false;
      if (state.personsRoleFilter && p.role !== state.personsRoleFilter) return false;
      return true;
    });

    personsCount.textContent = filtered.length;
    sortRows(filtered, state.personsSort, (p, key) => p[key]);

    personsBody.innerHTML = filtered.length ? filtered.map(p => {
      const key = `${p.name}|${p.role}`;
      const open = state.personsOpen === key;
      return `
        <tr class="clickable-row ${open ? "open" : ""}" data-key="${escapeHtml(key)}" title="Show this person's manuscripts">
          <td class="cell-person" dir="auto">${escapeHtml(p.name)}</td>
          <td><span class="person-role-badge">${escapeHtml(p.role)}</span></td>
          <td class="num">${p.count}</td>
          <td class="cell-toggle">${open ? "▾" : "▸"}</td>
        </tr>
        ${open ? `
        <tr class="detail-row"><td colspan="4">
          <ul class="person-ms-list">
            ${p.manuscripts.map(id => msById[id]).filter(Boolean).map(m => `
              <li>
                <button class="link-btn btn-person-ms" data-mms="${m.mms_id}">${escapeHtml(m.shelfmark || m.mms_id)}</button>
                <span class="person-ms-meta">${escapeHtml(m.library)} · ${escapeHtml(m.century.replace(/ \(.*\)/, ""))}</span>
                ${m.has_local_images ? `<span class="status-pill downloaded">facsimile</span>` : ""}
              </li>`).join("")}
          </ul>
          <button class="btn-secondary btn-person-filter" data-name="${escapeHtml(p.name)}">Show these in the Catalogue</button>
        </td></tr>` : ""}
      `;
    }).join("") : `<tr><td colspan="4" class="table-empty"><p>No persons match your search.</p></td></tr>`;

    personsBody.querySelectorAll(".clickable-row").forEach(row => {
      row.addEventListener("click", () => {
        state.personsOpen = state.personsOpen === row.dataset.key ? null : row.dataset.key;
        renderPersons();
      });
    });
    personsBody.querySelectorAll(".btn-person-ms").forEach(btn => {
      btn.addEventListener("click", () => openManuscriptModal(btn.dataset.mms));
    });
    personsBody.querySelectorAll(".btn-person-filter").forEach(btn => {
      btn.addEventListener("click", () => {
        state.catalogueFilters.search = btn.dataset.name;
        catalogueSearch.value = btn.dataset.name;
        switchTab("tab-catalogue");
        renderCatalogue();
      });
    });
  }

  personsSearch.addEventListener("input", e => {
    state.personsSearch = e.target.value.trim();
    renderPersons();
  });

  personsRole.addEventListener("change", e => {
    state.personsRoleFilter = e.target.value;
    renderPersons();
  });

  // -----------------------------------------------------------
  // 5. Tab 4: Geographic Map & Timeline (Leaflet)
  // -----------------------------------------------------------
  function initMap() {
    if (state.map.leafletInstance) return;

    // Center on Mediterranean / Europe
    const map = L.map("leaflet-map", {
      center: [45.0, 15.0],
      zoom: 4,
      zoomControl: true
    });

    // Academic OpenStreetMap Base Map
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 18
    }).addTo(map);

    state.map.leafletInstance = map;
    state.map.markersLayer = L.layerGroup().addTo(map);

    renderMapMarkers();
  }

  function renderMapMarkers() {
    if (!state.map.leafletInstance) return;
    state.map.markersLayer.clearLayers();

    const layerType = state.map.layerType;
    const period = state.map.activePeriod;

    // Filter places
    const matchingPlaces = data.places.filter(p => p.type === layerType);

    matchingPlaces.forEach(p => {
      // Find manuscripts matching century if active
      let msList = p.manuscripts.map(id => data.manuscripts.find(m => m.mms_id === id)).filter(Boolean);

      if (period) {
        // overlap: a manuscript dated only by century falls in every period of that century
        msList = msList.filter(m => m.year_from != null && m.year_from <= period[1] && m.year_to >= period[0]);
      }

      if (msList.length === 0) return;

      // Custom Academic Pin Icon
      const isHolding = layerType === "holding";
      const iconHtml = `<div class="custom-map-icon ${isHolding ? 'holding' : ''}" style="width: 28px; height: 28px;">${msList.length}</div>`;
      const icon = L.divIcon({
        className: "",
        html: iconHtml,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });

      const marker = L.marker([p.lat, p.lon], { icon: icon });

      marker.bindTooltip(`<strong>${p.label}</strong><br>${msList.length} manuscript${msList.length > 1 ? 's' : ''}`, {
        direction: "top"
      });

      marker.on("click", () => {
        showPlaceDetails(p, msList);
      });

      state.map.markersLayer.addLayer(marker);
    });
  }

  function showPlaceDetails(place, msList) {
    const placeTitle = document.getElementById("map-place-title");
    const placeDesc = document.getElementById("map-place-desc");
    const placeMsList = document.getElementById("map-place-ms-list");

    placeTitle.textContent = place.label;
    placeDesc.innerHTML = `
      <strong>${msList.length}</strong> manuscript${msList.length > 1 ? 's' : ''} associated with this center as 
      <em>${place.type === 'writing' ? 'Place of Copying / Origin' : 'Modern Holding Repository'}</em>:
    `;

    placeMsList.innerHTML = msList.map(m => `
      <div style="background: var(--bg-subtle); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.75rem;">
        <div style="font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; color: var(--accent-navy);">
          ${escapeHtml(m.shelfmark)}
        </div>
        <div style="font-family: var(--font-hebrew); font-size: 0.95rem; font-weight: 700; direction: rtl; text-align: right; margin: 0.2rem 0;">
          ${escapeHtml(m.title || "ללא כותר")}
        </div>
        <div style="font-size: 0.76rem; color: var(--ink-secondary); margin-bottom: 0.4rem;">
          ${escapeHtml(m.century)} · ${escapeHtml(m.library)}
        </div>
        <div style="display: flex; gap: 0.4rem;">
          ${m.has_local_images ? `
            <button class="btn-primary btn-mini-reader" data-mms="${m.mms_id}" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;">
              Read
            </button>
          ` : ""}
          <button class="btn-secondary btn-mini-modal" data-mms="${m.mms_id}" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;">
            Details
          </button>
        </div>
      </div>
    `).join("");

    placeMsList.querySelectorAll(".btn-mini-reader").forEach(btn => {
      btn.onclick = () => openManuscriptInReader(btn.dataset.mms);
    });

    placeMsList.querySelectorAll(".btn-mini-modal").forEach(btn => {
      btn.onclick = () => openManuscriptModal(btn.dataset.mms);
    });
  }

  // Map Controls
  const btnMapWriting = document.getElementById("btn-map-writing");
  const btnMapHolding = document.getElementById("btn-map-holding");

  btnMapWriting.addEventListener("click", () => {
    state.map.layerType = "writing";
    btnMapWriting.classList.add("active");
    btnMapHolding.classList.remove("active");
    renderMapMarkers();
  });

  btnMapHolding.addEventListener("click", () => {
    state.map.layerType = "holding";
    btnMapHolding.classList.add("active");
    btnMapWriting.classList.remove("active");
    renderMapMarkers();
  });

  // Timeline periods of MAP_PERIOD_YEARS years, from MAP_FIRST_YEAR up to the period in which the latest manuscript begins
  const MAP_PERIOD_YEARS = 50;
  const MAP_FIRST_YEAR = 1250;
  const timelineBox = document.getElementById("map-timeline-buttons");
  const lastYear = Math.max(...data.manuscripts.map(m => m.year_from || 0));
  for (let start = MAP_FIRST_YEAR; start <= lastYear; start += MAP_PERIOD_YEARS) {
    const btn = document.createElement("button");
    btn.className = "chip-btn";
    btn.dataset.period = `${start}-${start + MAP_PERIOD_YEARS - 1}`;
    btn.textContent = `${start}–${start + MAP_PERIOD_YEARS - 1}`;
    timelineBox.appendChild(btn);
  }

  document.querySelectorAll("#map-timeline-buttons .chip-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#map-timeline-buttons .chip-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.map.activePeriod = btn.dataset.period ? btn.dataset.period.split("-").map(Number) : null;
      renderMapMarkers();
    });
  });

  // -----------------------------------------------------------
  // 6. Tab 5: Search Queries Matrix
  // -----------------------------------------------------------
  const queriesContainer = document.getElementById("queries-matrix-container");
  if (queriesContainer) {
    queriesContainer.innerHTML = Object.keys(data.query_terms).map(q => {
      const count = data.query_terms[q];
      const label = queryLabels[q] || q;
      return `
        <div class="query-card">
          <div>
            <h3>${escapeHtml(q)}</h3>
            <div style="font-family: var(--font-serif-text); font-style: italic; color: var(--ink-secondary); margin-bottom: 0.6rem;">
              ${escapeHtml(label)}
            </div>
            <div style="font-size: 0.88rem; color: var(--ink-muted); margin-bottom: 1rem;">
              Harvested <strong>${count}</strong> catalog records in Alma.
            </div>
          </div>
          <button class="btn-secondary btn-apply-query" data-query="${escapeHtml(q)}">
            Filter Catalogue by this Query (${count})
          </button>
        </div>
      `;
    }).join("");

    queriesContainer.querySelectorAll(".btn-apply-query").forEach(btn => {
      btn.addEventListener("click", () => {
        const q = btn.dataset.query;
        state.catalogueFilters.queryTerm = q;
        document.querySelectorAll("#query-chips .chip-btn").forEach(c => {
          c.classList.toggle("active", c.textContent.includes(q));
        });
        switchTab("tab-catalogue");
        renderCatalogue();
      });
    });
  }

  // -----------------------------------------------------------
  // 7. Modal: Detailed Scholarly Manuscript Record
  // -----------------------------------------------------------
  const modal = document.getElementById("ms-modal");
  const modalClose = document.getElementById("modal-close");
  const modalBody = document.getElementById("modal-body");

  function openManuscriptModal(mmsId) {
    const ms = data.manuscripts.find(m => m.mms_id === mmsId);
    if (!ms) return;

    modalBody.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.25rem; gap: 1rem;">
        <div>
          <span class="ms-shelfmark-badge" style="font-size: 0.95rem;">${escapeHtml(ms.shelfmark)}</span>
          <h2 style="font-family: var(--font-hebrew); font-size: 1.6rem; font-weight: 700; direction: rtl; text-align: right; color: var(--ink-primary); margin-top: 0.5rem;">
            ${escapeHtml(ms.title || "ללא כותר עברי")}
          </h2>
          ${ms.author ? `<div style="font-family: var(--font-serif-text); font-size: 1.05rem; font-style: italic; color: var(--ink-secondary);">${escapeHtml(ms.author)}</div>` : ""}
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; background: var(--bg-subtle); padding: 1rem 1.25rem; border-radius: var(--radius-sm); margin-bottom: 1.25rem; border: 1px solid var(--border-color); font-size: 0.85rem;">
        <div><strong>Holding Library:</strong><br>${escapeHtml(ms.library)}</div>
        <div><strong>Current City:</strong><br>${escapeHtml(ms.library_city || "Not Recorded")}</div>
        <div><strong>Historical Era:</strong><br>${escapeHtml(ms.century)}</div>
        <div><strong>Place of Origin:</strong><br>${escapeHtml(ms.place_writing || "Unknown")}</div>
        <div><strong>Script & Hand:</strong><br>${escapeHtml(ms.script)}</div>
        <div><strong>Extent & Format:</strong><br>${escapeHtml(ms.extent || "Not Recorded")}</div>
      </div>

      ${ms.colophon ? `
        <div style="margin-bottom: 1.25rem;">
          <h4 style="font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent-crimson); margin-bottom: 0.4rem;">
            Scribe's Colophon (קולופון המעתיק):
          </h4>
          <div class="scholarly-blockquote">${escapeHtml(ms.colophon)}</div>
        </div>
      ` : ""}

      ${ms.added_names ? `
        <div style="margin-bottom: 1rem; font-size: 0.85rem;">
          <strong>Associated Persons, Scribes & Translators:</strong><br>
          <span style="color: var(--ink-secondary);">${escapeHtml(ms.added_names)}</span>
        </div>
      ` : ""}

      ${ms.notes ? `
        <div style="margin-bottom: 1rem; font-size: 0.85rem;">
          <strong>Cataloguer's Notes:</strong><br>
          <span style="color: var(--ink-secondary); line-height: 1.5;">${escapeHtml(ms.notes)}</span>
        </div>
      ` : ""}

      ${ms.subjects ? `
        <div style="margin-bottom: 1.25rem; font-size: 0.82rem;">
          <strong>Subject Headings:</strong><br>
          <span style="color: var(--ink-muted);">${escapeHtml(ms.subjects)}</span>
        </div>
      ` : ""}

      <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-color); padding-top: 1.25rem; margin-top: 1.5rem; flex-wrap: wrap; gap: 0.75rem;">
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--ink-muted);">
          MMS ID: ${escapeHtml(ms.mms_id)}
        </div>
        <div style="display: flex; gap: 0.6rem;">
          ${ms.has_local_images ? `
            <button class="btn-primary" id="modal-btn-read" data-mms="${ms.mms_id}">
              Open in Facsimile Reader
            </button>
          ` : ""}
          ${ms.manifest_url ? `
            <a href="${ms.manifest_url}" target="_blank" rel="noopener noreferrer" class="btn-secondary" title="View IIIF v2.1 JSON Manifest">
              IIIF Manifest
            </a>
          ` : ""}
          ${ms.ktiv_link ? `
            <a href="${ms.ktiv_link}" target="_blank" rel="noopener noreferrer" class="btn-secondary">
              View on Ktiv Portal
            </a>
          ` : ""}
        </div>
      </div>
    `;

    const modalBtnRead = document.getElementById("modal-btn-read");
    if (modalBtnRead) {
      modalBtnRead.onclick = () => {
        closeManuscriptModal();
        openManuscriptInReader(ms.mms_id);
      };
    }

    modal.classList.add("open");
  }

  function closeManuscriptModal() {
    modal.classList.remove("open");
  }

  modalClose.addEventListener("click", closeManuscriptModal);
  modal.addEventListener("click", e => {
    if (e.target === modal) closeManuscriptModal();
  });
  window.addEventListener("keydown", e => {
    if (e.key === "Escape" && modal.classList.contains("open")) {
      closeManuscriptModal();
    }
  });

  // -----------------------------------------------------------
  // 8. Tab 6: Illustrations (crops extracted in step 4)
  // -----------------------------------------------------------
  const illustrations = data.illustrations || [];
  const illById = Object.fromEntries(illustrations.map(il => [il.illustration_id, il]));
  const msById = Object.fromEntries(data.manuscripts.map(m => [m.mms_id, m]));
  const illFilterMs = document.getElementById("ill-filter-ms");
  const illFilterClass = document.getElementById("ill-filter-class");
  const illGrid = document.getElementById("ill-grid");

  // cluster id per illustration, and the groups themselves (step 5; may be absent)
  const clusterGroups = (data.clusters && data.clusters.clusters) || [];
  const clusterOf = {};
  clusterGroups.forEach(c => c.illustration_ids.forEach(id => { clusterOf[id] = c; }));

  function shelfmarkOf(mmsId) {
    const ms = msById[mmsId];
    return ms ? ms.shelfmark.split(" | ")[0] : mmsId;
  }

  function illustrationCard(il) {
    return `
      <div class="ill-card" data-id="${escapeHtml(il.illustration_id)}" title="Open page ${escapeHtml(il.page_number)} in the reader">
        <div class="ill-thumb"><img src="../${escapeHtml(il.crop_file)}" alt="${escapeHtml(il.class)}" loading="lazy"></div>
        <div class="ill-caption">
          <div class="ill-shelfmark">${escapeHtml(shelfmarkOf(il.mms_id))}</div>
          <div class="ill-meta">p. ${escapeHtml(il.page_number)} · ${escapeHtml(il.class)}</div>
        </div>
      </div>
    `;
  }

  function openIllustrationPage(id) {
    const il = illById[id];
    const ms = il && downloadedManuscripts.find(m => m.mms_id === il.mms_id);
    if (!ms) return;
    const pageIndex = ms.pages.findIndex(p => String(p.page_number) === String(parseInt(il.page_number, 10)));
    openManuscriptInReader(ms.mms_id, Math.max(pageIndex, 0));
  }

  function attachIllustrationClicks(container) {
    container.querySelectorAll(".ill-card").forEach(card => {
      card.addEventListener("click", () => openIllustrationPage(card.dataset.id));
    });
  }

  [...new Set(illustrations.map(il => il.mms_id))].forEach(mmsId => {
    const opt = document.createElement("option");
    opt.value = mmsId;
    opt.textContent = `${shelfmarkOf(mmsId)} (${illustrations.filter(il => il.mms_id === mmsId).length})`;
    illFilterMs.appendChild(opt);
  });
  [...new Set(illustrations.map(il => il.class))].sort().forEach(cls => {
    const opt = document.createElement("option");
    opt.value = cls;
    opt.textContent = `${cls} (${illustrations.filter(il => il.class === cls).length})`;
    illFilterClass.appendChild(opt);
  });

  function renderIllustrations() {
    const shown = illustrations.filter(il =>
      (!illFilterMs.value || il.mms_id === illFilterMs.value) &&
      (!illFilterClass.value || il.class === illFilterClass.value));
    document.getElementById("ill-count").textContent = shown.length;
    document.getElementById("ill-total").textContent = illustrations.length;
    illGrid.innerHTML = shown.length
      ? shown.map(illustrationCard).join("")
      : `<p class="empty-note">No illustrations yet. Run code/04_extract_illustrations.py and rebuild.</p>`;
    attachIllustrationClicks(illGrid);
  }

  illFilterMs.addEventListener("change", renderIllustrations);
  illFilterClass.addEventListener("change", renderIllustrations);

  // -----------------------------------------------------------
  // 9. Tab 7: Clusters (repeating illustrations from step 5)
  // -----------------------------------------------------------
  // Physical manuscripts (codices) from step 3: several catalogue records can describe one book
  const codices = data.codices || [];
  const codexById = Object.fromEntries(codices.map(c => [c.codex_id, c]));
  function codexOfMms(mmsId) {
    const ms = msById[mmsId];
    return ms && codexById[ms.codex_id] ? codexById[ms.codex_id]
      : { codex_id: mmsId, shelfmark: shelfmarkOf(mmsId), library: ms ? ms.library : "", library_city: "",
          century: ms ? ms.century : "", year: ms ? ms.year : null, place_writing: ms ? ms.place_writing : "",
          image_record: mmsId, has_images: true, texts: [], records: [mmsId] };
  }
  const codexOfIll = il => codexOfMms(il.mms_id);
  // a date for plotting: the catalogue year, else the middle of the recorded century
  function codexYear(c) {
    if (c.year) return c.year;
    const m = /\((\d{4})\D+(\d{4})\)/.exec(c.century || "");
    return m ? Math.round((+m[1] + +m[2]) / 2) : null;
  }
  const shortCentury = c => {
    const m = /^(\d+\w+) Century/.exec(c.century || "");
    return c.year ? String(c.year) : (m ? `${m[1]} c.` : "undated");
  };
  const codexLabel = c => c.shelfmark.split(" | ")[0];
  const codexPlace = c => (c.place_writing || "").split("|")[0].trim();

  // codices per repeating group
  const repGroups = clusterGroups.filter(c => c.label.startsWith("repeating"));
  const groupCodices = {};
  clusterGroups.forEach(c => {
    groupCodices[c.cluster_id] = [...new Set(c.illustration_ids.map(id => illById[id]).filter(Boolean)
      .map(il => codexOfIll(il).codex_id))];
  });
  const nCodices = c => (groupCodices[c.cluster_id] || []).length;
  const exampleOf = c => illById[c.example_id] || illById[c.illustration_ids[0]];

  function clusterTile(c) {
    const ex = exampleOf(c);
    const mss = (groupCodices[c.cluster_id] || []).map(id => codexLabel(codexById[id] || codexOfMms(id)));
    const name = c.label.startsWith("repeating") ? `Group ${c.cluster_id}` : c.label.replace(" (not compared)", "");
    return `
      <div class="cluster-tile" data-cluster="${c.cluster_id}" title="Open this group">
        <div class="ill-thumb">${ex ? `<img src="../${escapeHtml(ex.crop_file)}" alt="${escapeHtml(name)}" loading="lazy">` : ""}</div>
        <div class="cluster-tile-caption">
          <div class="cluster-tile-name">${escapeHtml(name)}</div>
          <div class="cluster-tile-counts">${c.illustration_ids.length} illustrations · ${mss.length} manuscript${mss.length === 1 ? "" : "s"}</div>
          <div class="cluster-tile-mss" title="${escapeHtml(mss.join(", "))}">${escapeHtml(mss.join(" · "))}</div>
        </div>
      </div>`;
  }

  function attachTileClicks(container) {
    container.querySelectorAll(".cluster-tile").forEach(t => {
      t.addEventListener("click", () => openClusterDetail(t.dataset.cluster));
    });
  }

  function msChip(c) {
    const place = codexPlace(c);
    return `<span class="ms-chip">${escapeHtml(codexLabel(c))} <span class="muted">· ${escapeHtml(shortCentury(c))}${place ? ` · ${escapeHtml(place)}` : ""}</span></span>`;
  }

  // One group in full: its manuscripts and every illustration in it
  function openClusterDetail(clusterId) {
    const c = clusterGroups.find(g => String(g.cluster_id) === String(clusterId));
    if (!c) return;
    switchTab("tab-clusters");
    const detail = document.getElementById("cluster-detail");
    const mss = (groupCodices[c.cluster_id] || []).map(id => codexById[id] || codexOfMms(id))
      .sort((a, b) => (codexYear(a) || 9999) - (codexYear(b) || 9999));
    const name = c.label.startsWith("repeating") ? `Group ${c.cluster_id}` : c.label;
    detail.innerHTML = `
      <div class="cluster-detail-head">
        <span class="cluster-detail-title">${escapeHtml(name)}</span>
        <span class="cluster-counts">${c.illustration_ids.length} illustrations · ${mss.length} manuscript${mss.length === 1 ? "" : "s"}</span>
        <button class="btn-quiet" id="cluster-detail-close">Close ✕</button>
      </div>
      <div class="cluster-ms-list">${mss.map(msChip).join("")}</div>
      <div class="ill-grid compact">${c.illustration_ids.map(id => illById[id]).filter(Boolean).map(illustrationCard).join("")}</div>
    `;
    detail.hidden = false;
    attachIllustrationClicks(detail);
    document.getElementById("cluster-detail-close").addEventListener("click", () => { detail.hidden = true; });
    requestAnimationFrame(() => requestAnimationFrame(() => detail.scrollIntoView({ block: "start" })));
  }

  function barRows(items, max, gold) {
    return items.map(([label, value, title]) => `
      <div class="bar-row" title="${escapeHtml(title || label)}">
        <span class="bar-label">${escapeHtml(label)}</span>
        <span class="bar-track"><span class="bar-fill ${gold ? "gold" : ""}" style="width: ${max ? Math.max(2, 100 * value / max) : 0}%; display: block;"></span></span>
        <span class="bar-value">${value}</span>
      </div>`).join("");
  }

  // clusters.json: id 0 = "other (no close match)", "repeating group N" = groups above the
  // similarity threshold, "... (not compared)" = classes left out of the comparison.
  function renderClusters() {
    const summary = document.getElementById("clusters-summary");
    const body = document.getElementById("clusters-body");
    if (!clusterGroups.length) {
      summary.innerHTML = `<p class="empty-note">No clusters yet. Run code/05_cluster_illustrations.py and rebuild.</p>`;
      return;
    }

    const other = clusterGroups.find(c => c.cluster_id === 0) || { illustration_ids: [] };
    const notCompared = clusterGroups.filter(c => c.label.endsWith("(not compared)"));
    const across = repGroups.filter(c => nCodices(c) > 1)
      .sort((a, b) => nCodices(b) - nCodices(a) || b.illustration_ids.length - a.illustration_ids.length);
    const within = repGroups.filter(c => nCodices(c) <= 1)
      .sort((a, b) => b.illustration_ids.length - a.illustration_ids.length);
    const nClustered = repGroups.reduce((n, c) => n + c.illustration_ids.length, 0);
    const nCompared = nClustered + other.illustration_ids.length;
    const pct = nCompared ? Math.round(100 * nClustered / nCompared) : 0;
    const threshold = data.clusters.similarity_threshold;

    // how many manuscripts each shared group spans
    const spread = {};
    across.forEach(c => { const k = Math.min(nCodices(c), 6); spread[k] = (spread[k] || 0) + 1; });
    const spreadRows = Object.keys(spread).sort((a, b) => a - b)
      .map(k => [`${k}${k === "6" ? "+" : ""} manuscripts`, spread[k]]);
    // manuscripts that take part in the most shared groups
    const perCodex = {};
    across.forEach(c => groupCodices[c.cluster_id].forEach(id => { perCodex[id] = (perCodex[id] || 0) + 1; }));
    const topCodices = Object.entries(perCodex).sort((a, b) => b[1] - a[1]).slice(0, 10)
      .map(([id, n]) => { const c = codexById[id] || codexOfMms(id); return [`${codexLabel(c)} · ${shortCentury(c)}`, n, `${codexLabel(c)}, ${c.library}`]; });

    summary.innerHTML = `
      <div class="clusters-headline">
        <span class="clusters-big">${nClustered}</span> of ${nCompared} diagrams (${pct}%) were found in repeating groups
      </div>
      <div class="clusters-stats">
        <div class="stat-item"><span class="label">Repeating groups</span> <span class="value">${repGroups.length}</span></div>
        <div class="stat-item"><span class="label">Shared by 2+ manuscripts</span> <span class="value">${across.length}</span></div>
        <div class="stat-item"><span class="label">Within one manuscript</span> <span class="value">${within.length}</span></div>
        <div class="stat-item"><span class="label">No close match</span> <span class="value">${other.illustration_ids.length}</span></div>
      </div>
      <div class="overview-grid">
        <div class="overview-box">
          <h4>How many manuscripts share each group</h4>
          ${barRows(spreadRows, Math.max(...spreadRows.map(r => r[1]), 1), true)}
        </div>
        <div class="overview-box">
          <h4>Manuscripts in the most shared groups</h4>
          ${barRows(topCodices, topCodices.length ? topCodices[0][1] : 1)}
          <p class="clusters-note" style="margin-top: 0.5rem;">Which manuscripts share with which, over time and place:
            <button class="link-btn" id="goto-families">open Visual Families →</button></p>
        </div>
      </div>
      <p class="clusters-note">
        A group is formed only when every two diagrams in it are at least
        ${threshold != null ? `<strong>${Math.round(threshold * 100)}%</strong>` : "the chosen level"} similar
        (${escapeHtml(data.clusters.method)}). Each tile shows the group's most typical illustration; click it to see the whole group.
      </p>
    `;
    document.getElementById("goto-families").addEventListener("click", () => switchTab("tab-families"));

    const section = (title, note, inner) => `
      <h3 class="clusters-section-title">${title}</h3>
      <p class="clusters-section-note">${note}</p>
      ${inner}
    `;
    body.innerHTML =
      section(`Shared by several manuscripts (${across.length} groups)`,
              "The same kind of diagram found in two or more manuscripts, most widely shared first.",
              `<div class="cluster-tiles">${across.map(clusterTile).join("")}</div>`) +
      section(`Repeating within one manuscript (${within.length} groups)`,
              "Similar diagrams that recur inside a single manuscript.",
              `<div class="cluster-tiles">${within.map(clusterTile).join("")}</div>`) +
      (notCompared.length ? section(`Initials, decorations and tables`,
              "Collected by class, not compared for similarity.",
              `<div class="cluster-tiles">${notCompared.map(clusterTile).join("")}</div>`) : "") +
      section(`No close match (${other.illustration_ids.length})`,
              "Diagrams with no other diagram above the similarity level: these appear only once in the corpus.",
              `<button class="btn-quiet" id="show-unmatched">Show all ${other.illustration_ids.length}</button>
               <div id="unmatched-grid" class="ill-grid compact" style="margin-top: 0.8rem;"></div>`);
    attachTileClicks(body);
    document.getElementById("show-unmatched").addEventListener("click", e => {
      const grid = document.getElementById("unmatched-grid");
      grid.innerHTML = other.illustration_ids.map(id => illById[id]).filter(Boolean).map(illustrationCard).join("");
      attachIllustrationClicks(grid);
      e.target.remove();
    });
  }

  // -----------------------------------------------------------
  // 10. Tab: Included Texts (works inside the manuscripts, from the catalogue)
  // -----------------------------------------------------------
  const texts = data.texts || [];
  const textsBody = document.getElementById("texts-body");
  const textsSearch = document.getElementById("texts-search");
  const textsMultiOnly = document.getElementById("texts-multi-only");
  let openText = null;

  function renderTextsSummary() {
    const s = data.stats || {};
    const shared = texts.filter(t => t.count > 1).length;
    document.getElementById("texts-summary").innerHTML = `
      <div class="clusters-headline">
        <span class="clusters-big">${codices.length}</span> physical manuscripts in the corpus
        <span style="color: var(--ink-muted); font-size: 0.95rem;">(${s.total_manuscripts || data.manuscripts.length} catalogue records)</span>
      </div>
      <div class="clusters-stats">
        <div class="stat-item"><span class="label">Distinct texts</span> <span class="value">${texts.length}</span></div>
        <div class="stat-item"><span class="label">Texts in 2+ manuscripts</span> <span class="value">${shared}</span></div>
        <div class="stat-item"><span class="label">With page images</span> <span class="value">${codices.filter(c => c.has_images).length} manuscripts</span></div>
      </div>
      <p class="clusters-note">One physical manuscript often has several catalogue records: one for the volume ("קובץ") and one per work in it.
        Texts are taken from the records' titles and their added titles (MARC 740); spelling variants are kept apart, and "(קטע)" marks a fragment.</p>
    `;
  }

  function renderTexts() {
    const q = textsSearch.value.trim();
    const shown = texts.filter(t => (!q || t.title.includes(q)) && (!textsMultiOnly.checked || t.count > 1));
    document.getElementById("texts-count").textContent = shown.length;
    const max = texts.length ? texts[0].count : 1;
    textsBody.innerHTML = shown.map(t => `
      <tr class="text-row ${openText === t.title ? "open" : ""}" data-title="${escapeHtml(t.title)}">
        <td><span class="text-title">${escapeHtml(t.title)}</span>
          ${t.fragment_in.length ? `<span style="font-size: 0.75rem; color: var(--ink-muted);"> · fragment in ${t.fragment_in.length}</span>` : ""}</td>
        <td><div class="text-count-cell">
          <span class="bar-track"><span class="bar-fill" style="width: ${Math.max(2, 100 * t.count / max)}%; display: block;"></span></span>
          <span class="text-count-num">${t.count}</span></div></td>
      </tr>
      ${openText === t.title ? `<tr class="text-detail"><td colspan="2">${textDetail(t)}</td></tr>` : ""}
    `).join("");
    textsBody.querySelectorAll(".text-row").forEach(row => {
      row.addEventListener("click", () => {
        openText = openText === row.dataset.title ? null : row.dataset.title;
        renderTexts();
      });
    });
    textsBody.querySelectorAll(".btn-read-codex").forEach(btn => {
      btn.addEventListener("click", e => { e.stopPropagation(); openManuscriptInReader(btn.dataset.mms); });
    });
  }

  function textDetail(t) {
    const mss = t.codices.map(id => codexById[id]).filter(Boolean)
      .sort((a, b) => (codexYear(a) || 9999) - (codexYear(b) || 9999));
    const together = {};
    mss.forEach(c => c.texts.forEach(o => { if (o !== t.title) together[o] = (together[o] || 0) + 1; }));
    const top = Object.entries(together).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return `
      <table class="text-ms-table">
        <thead><tr><th>Manuscript</th><th>Library</th><th>Date</th><th>Place</th><th>Other texts in it</th><th></th></tr></thead>
        <tbody>${mss.map(c => `
          <tr>
            <td style="font-family: var(--font-mono); white-space: nowrap;">${escapeHtml(codexLabel(c))}${t.fragment_in.includes(c.codex_id) ? " <em>(fragment)</em>" : ""}</td>
            <td>${escapeHtml(c.library)}</td>
            <td style="white-space: nowrap;">${escapeHtml(shortCentury(c))}</td>
            <td>${escapeHtml(codexPlace(c))}</td>
            <td class="text-others">${escapeHtml(c.texts.filter(o => o !== t.title).join(" · "))}</td>
            <td>${c.has_images ? `<button class="status-pill downloaded btn-read-codex" data-mms="${escapeHtml(c.image_record)}">Read</button>` : ""}</td>
          </tr>`).join("")}
        </tbody>
      </table>
      ${top.length ? `<div class="text-together"><strong>Often copied together with:</strong>
        ${top.map(([o, n]) => `<span class="text-others">${escapeHtml(o)}</span> (${n})`).join(" · ")}</div>` : ""}
    `;
  }

  textsSearch.addEventListener("input", renderTexts);
  textsMultiOnly.addEventListener("change", renderTexts);

  // -----------------------------------------------------------
  // 11. Tab: Visual Families (which manuscripts share illustration groups, over time and place)
  // -----------------------------------------------------------
  // pairs of codices -> shared repeating groups
  const pairGroups = {};
  repGroups.forEach(c => {
    const ids = (groupCodices[c.cluster_id] || []).slice().sort();
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        (pairGroups[`${ids[i]}|${ids[j]}`] = pairGroups[`${ids[i]}|${ids[j]}`] || []).push(c);
      }
    }
  });
  const sharedCount = (a, b) => (pairGroups[a < b ? `${a}|${b}` : `${b}|${a}`] || []).length;
  const illsPerCodex = {};
  illustrations.forEach(il => { const id = codexOfIll(il).codex_id; illsPerCodex[id] = (illsPerCodex[id] || 0) + 1; });
  const familiesThreshold = document.getElementById("families-threshold");

  // groups shared with other manuscripts, per codex
  const sharedGroupsOf = {};
  repGroups.forEach(c => {
    const ids = groupCodices[c.cluster_id] || [];
    if (ids.length > 1) ids.forEach(id => (sharedGroupsOf[id] = sharedGroupsOf[id] || new Set()).add(c.cluster_id));
  });
  // overlap of two manuscripts: shared groups / groups found in either (Jaccard)
  function overlap(a, b) {
    const A = sharedGroupsOf[a], B = sharedGroupsOf[b];
    if (!A || !B) return 0;
    let n = 0;
    A.forEach(g => { if (B.has(g)) n++; });
    return n / (A.size + B.size - n);
  }
  // average-linkage clustering: join the two most similar families while their average overlap >= t
  const familiesCache = {};
  function computeFamilies(t) {
    if (familiesCache[t]) return familiesCache[t];
    let fams = Object.keys(sharedGroupsOf).map(id => [id]);
    const sim = (A, B) => { let s = 0; A.forEach(a => B.forEach(b => { s += overlap(a, b); })); return s / (A.length * B.length); };
    for (;;) {
      let best = -1, bi = -1, bj = -1;
      for (let i = 0; i < fams.length; i++) {
        for (let j = i + 1; j < fams.length; j++) {
          const s = sim(fams[i], fams[j]);
          if (s > best) { best = s; bi = i; bj = j; }
        }
      }
      if (best < t) break;
      fams[bi] = fams[bi].concat(fams[bj]);
      fams.splice(bj, 1);
    }
    return (familiesCache[t] = fams.filter(f => f.length > 1).sort((a, b) => b.length - a.length));
  }
  const FAMILY_COLOURS = ["#8e283b", "#1d6fa5", "#b07d2b", "#2b7042", "#6b3fa0", "#c2571a", "#0f7c7c", "#a8326e",
                          "#4a5d23", "#5b6ee1", "#8a5a44", "#d4a017"];
  const familiesRows = document.getElementById("families-rows");

  function renderFamilies() {
    const t = parseFloat(familiesThreshold.value);
    const famList = computeFamilies(t);
    const familyOf = {};
    famList.forEach((f, i) => f.forEach(id => { familyOf[id] = i; }));
    const withIlls = Object.keys(illsPerCodex);
    const sharing = Object.keys(sharedGroupsOf);
    const strongest = Object.entries(pairGroups).sort((a, b) => b[1].length - a[1].length)[0];

    document.getElementById("families-summary").innerHTML = `
      <div class="clusters-headline">
        <span class="clusters-big">${sharing.length}</span> of ${withIlls.length} illustrated manuscripts share at least one illustration group with another manuscript
      </div>
      <div class="clusters-stats">
        <div class="stat-item"><span class="label">Families at ${Math.round(t * 100)}% overlap</span> <span class="value">${famList.length} (${famList.reduce((n, f) => n + f.length, 0)} manuscripts)</span></div>
        ${strongest ? `<div class="stat-item"><span class="label">Most shared groups</span> <span class="value">${escapeHtml(strongest[0].split("|").map(id => codexLabel(codexById[id] || codexOfMms(id))).join(" & "))}: ${strongest[1].length}</span></div>` : ""}
      </div>`;

    document.getElementById("families-list").innerHTML = famList.length ? famList.map((members, i) => {
      const set = new Set(members);
      const groups = repGroups.filter(c => (groupCodices[c.cluster_id] || []).filter(id => set.has(id)).length >= 2)
        .sort((a, b) => (groupCodices[b.cluster_id] || []).filter(id => set.has(id)).length
                      - (groupCodices[a.cluster_id] || []).filter(id => set.has(id)).length);
      const cs = members.map(id => codexById[id] || codexOfMms(id)).sort((a, b) => (codexYear(a) || 9999) - (codexYear(b) || 9999));
      let pairs = 0, sum = 0;
      members.forEach((a, x) => members.slice(x + 1).forEach(b => { pairs++; sum += overlap(a, b); }));
      const colour = FAMILY_COLOURS[i % FAMILY_COLOURS.length];
      return `
        <div class="family-item" style="border-left: 4px solid ${colour};">
          <div class="family-head">Family ${i + 1}: ${members.length} manuscripts
            <span class="muted">· ${groups.length} illustration groups shared inside the family · average overlap ${Math.round(100 * sum / pairs)}%</span></div>
          <div class="cluster-ms-list" style="margin: 0;">${cs.map(msChip).join("")}</div>
          <div class="family-examples">${groups.slice(0, 14).map(c => {
            const ex = exampleOf(c);
            return ex ? `<img src="../${escapeHtml(ex.crop_file)}" data-cluster="${c.cluster_id}" title="Group ${c.cluster_id}: open it" loading="lazy">` : "";
          }).join("")}</div>
        </div>`;
    }).join("") : `<p class="empty-note">No families at this level. Choose a lower percentage above.</p>`;
    document.querySelectorAll("#families-list .family-examples img").forEach(img => {
      img.addEventListener("click", () => openClusterDetail(img.dataset.cluster));
    });

    renderFamiliesTimeline(famList, familyOf);
    renderFamiliesMatrix(sharing);
  }

  function renderFamiliesTimeline(famList, familyOf) {
    const ids = Object.keys(illsPerCodex);
    const cs = ids.map(id => codexById[id] || codexOfMms(id));
    const byScript = familiesRows.value === "script";
    const unknown = byScript ? "Script not recorded" : "Place not recorded";
    const rowOf = c => (byScript ? (c.script || "").split("|")[0].trim() : codexPlace(c)) || unknown;
    const rowCount = {};
    cs.forEach(c => { rowCount[rowOf(c)] = (rowCount[rowOf(c)] || 0) + 1; });
    const rows = Object.keys(rowCount).sort((a, b) =>
      (a === unknown) - (b === unknown) || rowCount[b] - rowCount[a] || a.localeCompare(b));
    const years = cs.map(codexYear).filter(Boolean);
    const minY = Math.floor((Math.min(...years) - 20) / 50) * 50, maxY = Math.ceil((Math.max(...years) + 20) / 50) * 50;
    const W = 980, left = 190, right = 90, top = 20, rowH = byScript ? 40 : 26, H = top + rows.length * rowH + 40;
    const plotW = W - left - right;
    const x = y => y ? left + plotW * (y - minY) / (maxY - minY) : W - right / 2;
    const yPos = {};
    rows.forEach((r, i) => { yPos[r] = top + i * rowH + rowH / 2; });
    // spread manuscripts that land on the same spot
    const seen = {}, pos = {};
    cs.forEach(c => {
      const px = x(codexYear(c)), py = yPos[rowOf(c)];
      const key = `${Math.round(px / 8)}|${py}`;
      const n = seen[key] = (seen[key] || 0) + 1;
      pos[c.codex_id] = [px + ((n - 1) % 4) * 7, py + (Math.floor((n - 1) / 4) % 3 - 1) * (byScript ? 9 : 0)];
    });
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" role="img" aria-label="Manuscripts by date and ${byScript ? "script" : "place"}">`;
    rows.forEach(r => {
      const y = yPos[r];
      svg += `<line x1="${left}" x2="${W - 10}" y1="${y}" y2="${y}" stroke="var(--border-light)"/>
        <text x="${left - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="var(--ink-secondary)">${escapeHtml(r.length > 28 ? r.slice(0, 27) + "…" : r)} (${rowCount[r]})</text>`;
    });
    for (let yr = minY; yr <= maxY; yr += 50) {
      svg += `<line x1="${x(yr)}" x2="${x(yr)}" y1="${top - 6}" y2="${H - 30}" stroke="var(--border-light)" stroke-dasharray="${yr % 100 ? "2 3" : ""}"/>
        <text x="${x(yr)}" y="${H - 14}" text-anchor="middle" font-size="11" fill="var(--ink-muted)">${yr}</text>`;
    }
    svg += `<text x="${W - right / 2}" y="${H - 14}" text-anchor="middle" font-size="11" fill="var(--ink-muted)">undated</text>`;
    // lines join members of a family, in date order
    famList.forEach((members, i) => {
      const colour = FAMILY_COLOURS[i % FAMILY_COLOURS.length];
      const ordered = members.filter(id => pos[id]).sort((a, b) => pos[a][0] - pos[b][0]);
      for (let k = 1; k < ordered.length; k++) {
        const [a, b] = [ordered[k - 1], ordered[k]];
        svg += `<line x1="${pos[a][0]}" y1="${pos[a][1]}" x2="${pos[b][0]}" y2="${pos[b][1]}" stroke="${colour}" stroke-opacity="0.55" stroke-width="2"/>`;
      }
    });
    cs.forEach(c => {
      const [px, py] = pos[c.codex_id];
      const r = Math.max(3, Math.min(11, Math.sqrt(illsPerCodex[c.codex_id] || 1) * 1.3));
      const fam = familyOf[c.codex_id];
      const colour = fam === undefined ? "#9aa3ae" : FAMILY_COLOURS[fam % FAMILY_COLOURS.length];
      svg += `<circle class="fam-dot" data-mms="${escapeHtml(c.image_record || c.codex_id)}" cx="${px}" cy="${py}" r="${r}"
        fill="${colour}" fill-opacity="0.85" stroke="#fff" stroke-width="1"><title>${escapeHtml(codexLabel(c))}, ${escapeHtml(c.library)}
${escapeHtml(shortCentury(c))}${codexPlace(c) ? ", " + escapeHtml(codexPlace(c)) : ""}${c.script ? ", script: " + escapeHtml(c.script) : ""}
${illsPerCodex[c.codex_id] || 0} illustrations${fam === undefined ? "" : ` · Family ${fam + 1}`}</title></circle>`;
    });
    svg += `</svg>`;
    const box = document.getElementById("families-timeline");
    box.innerHTML = svg;
    box.querySelectorAll(".fam-dot").forEach(dot => {
      dot.addEventListener("click", () => {
        if (downloadedManuscripts.some(m => m.mms_id === dot.dataset.mms)) openManuscriptInReader(dot.dataset.mms);
      });
    });
  }

  function renderFamiliesMatrix(ids) {
    const cs = ids.map(id => codexById[id] || codexOfMms(id))
      .sort((a, b) => (codexYear(a) || 9999) - (codexYear(b) || 9999) || codexLabel(a).localeCompare(codexLabel(b)));
    const n = cs.length;
    const box = document.getElementById("families-matrix");
    if (!n) { box.innerHTML = ""; return; }
    const cell = Math.max(7, Math.min(14, Math.floor(760 / n)));
    const label = 170, size = label + n * cell + 10;
    let max = 1;
    cs.forEach(a => cs.forEach(b => { if (a !== b) max = Math.max(max, sharedCount(a.codex_id, b.codex_id)); }));
    let svg = `<svg viewBox="0 0 ${size} ${size}" width="${size}" role="img" aria-label="Shared groups between manuscripts">`;
    cs.forEach((c, i) => {
      const t = `${codexLabel(c)} · ${shortCentury(c)}`;
      svg += `<text x="${label - 6}" y="${label + i * cell + cell * 0.75}" text-anchor="end" font-size="${Math.min(10, cell)}" fill="var(--ink-secondary)">${escapeHtml(t.length > 30 ? t.slice(0, 29) + "…" : t)}</text>`;
      svg += `<text transform="translate(${label + i * cell + cell * 0.75},${label - 6}) rotate(-60)" font-size="${Math.min(10, cell)}" fill="var(--ink-secondary)">${escapeHtml(codexLabel(c).slice(0, 22))}</text>`;
    });
    cs.forEach((a, i) => cs.forEach((b, j) => {
      const v = i === j ? 0 : sharedCount(a.codex_id, b.codex_id);
      const fill = i === j ? "var(--border-color)" : v ? "var(--accent-crimson)" : "var(--bg-subtle)";
      const op = i === j || !v ? 1 : 0.18 + 0.82 * v / max;
      svg += `<rect class="${v ? "fam-cell" : ""}" data-a="${escapeHtml(a.codex_id)}" data-b="${escapeHtml(b.codex_id)}" x="${label + j * cell}" y="${label + i * cell}"
        width="${cell - 1}" height="${cell - 1}" fill="${fill}" fill-opacity="${op}">${v ? `<title>${escapeHtml(codexLabel(a))} & ${escapeHtml(codexLabel(b))}: ${v} shared groups</title>` : ""}</rect>`;
    }));
    svg += `</svg>`;
    box.innerHTML = svg;
    box.querySelectorAll(".fam-cell").forEach(r => r.addEventListener("click", () => renderPair(r.dataset.a, r.dataset.b)));
  }

  function renderPair(a, b) {
    const gs = (pairGroups[a < b ? `${a}|${b}` : `${b}|${a}`] || []).slice().sort((x, y) => nCodices(y) - nCodices(x));
    const ca = codexById[a] || codexOfMms(a), cb = codexById[b] || codexOfMms(b);
    const box = document.getElementById("families-pair");
    box.innerHTML = `
      <h4 class="clusters-section-title" style="font-size: 1rem;">${escapeHtml(codexLabel(ca))} & ${escapeHtml(codexLabel(cb))}: ${gs.length} shared groups</h4>
      <div class="cluster-ms-list">${msChip(ca)}${msChip(cb)}</div>
      <div class="cluster-tiles">${gs.map(clusterTile).join("")}</div>`;
    attachTileClicks(box);
    box.scrollIntoView({ block: "nearest" });
  }

  familiesThreshold.addEventListener("change", renderFamilies);
  familiesRows.addEventListener("change", renderFamilies);

  // Utility: HTML Escaping
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // -----------------------------------------------------------
  // Initial Boot
  // -----------------------------------------------------------
  makeSortable(document.getElementById("catalogue-table"), state.catalogueSort, renderCatalogue);
  makeSortable(document.getElementById("persons-table"), state.personsSort, renderPersons);
  renderCatalogue();
  renderPersons();
  renderIllustrations();
  renderClusters();
  renderTextsSummary();
  renderTexts();
  renderFamilies();

  // Pre-load first downloaded manuscript into reader
  if (downloadedManuscripts.length > 0) {
    loadManuscriptIntoReader(downloadedManuscripts[0].mms_id, 0);
  }
});
