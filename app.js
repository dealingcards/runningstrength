(() => {
  "use strict";

  const STORAGE_KEY = "runner-strength-state-v1";
  const PROGRAM_ORDER = ["base", "base-v2", "race"];
  const PROGRAM_SELECTOR_LABELS = {
    base: "Base",
    "base-v2": "Base V2",
    race: "Race"
  };
  const app = document.getElementById("app");
  const ui = {
    expandedSessions: new Set(),
    touchStart: null
  };
  let deferredInstallPrompt = null;

  function createDefaultState() {
    return {
      selectedProgram: "base",
      lastViewedWeek: { base: 1, "base-v2": 1, race: 1 },
      raceDate: "",
      completed: {}
    };
  }

  function loadState() {
    const fallback = createDefaultState();
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      const selectedProgram = PROGRAMS[saved.selectedProgram] ? saved.selectedProgram : "base";
      return {
        selectedProgram: selectedProgram,
        lastViewedWeek: {
          base: Number(saved.lastViewedWeek && saved.lastViewedWeek.base) || 1,
          "base-v2": Number(saved.lastViewedWeek && saved.lastViewedWeek["base-v2"]) || 1,
          race: Number(saved.lastViewedWeek && saved.lastViewedWeek.race) || 1
        },
        raceDate: typeof saved.raceDate === "string" ? saved.raceDate : "",
        completed: saved.completed && typeof saved.completed === "object" ? saved.completed : {}
      };
    } catch (error) {
      return fallback;
    }
  }

  let state = loadState();

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      // The app remains usable during the current visit if storage is unavailable.
    }
  }

  function getProgram() {
    return PROGRAMS[state.selectedProgram];
  }

  function getCurrentWeek(program) {
    const wanted = state.lastViewedWeek[program.id] || 1;
    const safeNumber = Math.min(Math.max(wanted, 1), program.weeks.length);
    return program.weeks[safeNumber - 1];
  }

  function isSessionComplete(sessionId) {
    return Boolean(state.completed[sessionId]);
  }

  function completedSessions(program) {
    return program.weeks.reduce((total, week) => {
      return total + week.sessions.filter((session) => isSessionComplete(session.id)).length;
    }, 0);
  }

  function completeCountForWeek(week) {
    return week.sessions.filter((session) => isSessionComplete(session.id)).length;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[character];
    });
  }

  function calculateRaceWindow() {
    if (!state.raceDate) {
      return {
        kind: "unset",
        text: "Set your race date to receive the Race Builder switch reminder.",
        inWindow: false
      };
    }

    const parts = state.raceDate.split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) {
      return {
        kind: "unset",
        text: "Set your race date to receive the Race Builder switch reminder.",
        inWindow: false
      };
    }

    const target = new Date(parts[0], parts[1] - 1, parts[2]);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const difference = Math.round((target.getTime() - today.getTime()) / 86400000);

    if (difference < 0) {
      return {
        kind: "past",
        text: "That race date has passed. Choose your next race.",
        inWindow: false
      };
    }

    const weeks = Math.ceil(difference / 7);
    if (difference <= 84) {
      return {
        kind: "switch",
        text: weeks === 0 ? "Race week is here." : "Race Builder starts now - about " + weeks + " week" + (weeks === 1 ? "" : "s") + " to race.",
        inWindow: true
      };
    }

    const untilSwitch = Math.ceil((difference - 84) / 7);
    return {
      kind: "countdown",
      text: "Race Builder begins in about " + untilSwitch + " week" + (untilSwitch === 1 ? "" : "s") + ".",
      inWindow: false
    };
  }

  function sessionRpe(session) {
    const rpes = [];
    session.sections.forEach((section) => {
      section.exercises.forEach((exercise) => {
        if (exercise.rpe && !rpes.includes(exercise.rpe)) rpes.push(exercise.rpe);
      });
    });
    return rpes.length ? rpes.join(" · ") : "Session plan";
  }

  function renderExercise(exercise) {
    const meta = [];
    if (exercise.rpe) {
      meta.push('<span class="rpe-pill">' + escapeHtml(exercise.rpe) + "</span>");
    }
    if (exercise.note) {
      meta.push('<span class="note-pill">' + escapeHtml(exercise.note) + "</span>");
    }

    return (
      '<li class="exercise">' +
        '<span class="exercise-name">' + escapeHtml(exercise.name) + "</span>" +
        (exercise.prescription ? '<span class="exercise-prescription">' + escapeHtml(exercise.prescription) + "</span>" : "") +
        (meta.length ? '<div class="exercise-meta">' + meta.join("") + "</div>" : "") +
      "</li>"
    );
  }

  function renderSection(section, index) {
    return (
      '<details class="section-detail"' + (index === 0 ? " open" : "") + ">" +
        "<summary>" + escapeHtml(section.title) + "</summary>" +
        '<ul class="exercise-list">' + section.exercises.map(renderExercise).join("") + "</ul>" +
      "</details>"
    );
  }

  function renderSession(session, index) {
    const completed = isSessionComplete(session.id);
    const expanded = ui.expandedSessions.has(session.id);
    const status = completed ? "Completed" : "Mark complete";
    const indexLabel = completed ? "Done" : String(index + 1).padStart(2, "0");

    return (
      '<article class="session-card' + (completed ? " is-complete" : "") + (expanded ? " is-expanded" : "") + '">' +
        '<div class="session-head">' +
          '<button type="button" class="session-toggle" data-action="toggle-session" data-session-id="' + escapeHtml(session.id) + '" aria-expanded="' + String(expanded) + '">' +
            '<span class="session-index">' + indexLabel + "</span>" +
            '<span class="session-name">' +
              "<strong>" + escapeHtml(session.label) + "</strong>" +
              "<span>" + escapeHtml(sessionRpe(session)) + "</span>" +
            "</span>" +
            '<span class="session-chevron" aria-hidden="true">&rsaquo;</span>' +
          "</button>" +
          '<button type="button" class="completion-button" data-action="toggle-complete" data-session-id="' + escapeHtml(session.id) + '" aria-pressed="' + String(completed) + '">' + status + "</button>" +
        "</div>" +
        '<div class="session-body">' +
          session.sections.map(renderSection).join("") +
        "</div>" +
      "</article>"
    );
  }

  function renderWeekRail(program, currentWeek) {
    return program.weeks.map((week) => {
      const done = completeCountForWeek(week);
      const classes = [
        "week-chip",
        week.number === currentWeek.number ? "is-current" : "",
        done === week.sessions.length ? "is-complete" : ""
      ].filter(Boolean).join(" ");
      return (
        '<button type="button" class="' + classes + '" data-action="jump-week" data-week="' + week.number + '" aria-label="Open Week ' + week.number + '">' +
          "W" + week.number +
        "</button>"
      );
    }).join("");
  }

  function renderWeekTiles(program, currentWeek) {
    return program.weeks.map((week) => {
      const done = completeCountForWeek(week);
      const classes = [
        "week-tile",
        week.number === currentWeek.number ? "is-current" : "",
        done === week.sessions.length ? "is-complete" : ""
      ].filter(Boolean).join(" ");
      return (
        '<button type="button" class="' + classes + '" data-action="jump-week" data-week="' + week.number + '" aria-label="Open Week ' + week.number + ', ' + done + " of " + week.sessions.length + ' sessions complete">' +
          "<strong>W" + week.number + "</strong>" +
          "<span>" + done + "/" + week.sessions.length + "</span>" +
        "</button>"
      );
    }).join("");
  }

  function renderRaceAlert(race) {
    if (!race.inWindow) return "";
    const action = state.selectedProgram !== "race"
      ? '<button type="button" data-action="switch-race">Open Race Builder</button>'
      : "";
    return (
      '<section class="race-alert" aria-label="Race Builder reminder">' +
        '<div class="race-alert-copy">' +
          "<strong>Race Builder starts now</strong>" +
          "<span>" + escapeHtml(race.text) + "</span>" +
        "</div>" +
        action +
      "</section>"
    );
  }

  function renderProgramChoices(program) {
    return PROGRAM_ORDER.map((programId) => {
      const active = program.id === programId;
      return (
        '<button type="button" class="program-choice' + (active ? " is-active" : "") + '" data-action="switch-program" data-program="' + programId + '" role="tab" aria-selected="' + String(active) + '">' +
          PROGRAM_SELECTOR_LABELS[programId] +
        "</button>"
      );
    }).join("");
  }

  function render() {
    const program = getProgram();
    const week = getCurrentWeek(program);
    const doneInProgram = completedSessions(program);
    const totalInProgram = program.weeks.reduce((total, item) => total + item.sessions.length, 0);
    const doneInWeek = completeCountForWeek(week);
    const completionPercent = Math.round((doneInProgram / totalInProgram) * 100);
    const race = calculateRaceWindow();
    const previousDisabled = week.number === 1 ? " disabled" : "";
    const nextDisabled = week.number === program.weeks.length ? " disabled" : "";
    const focus = week.focus ? week.focus : "Training week";

    app.innerHTML = (
      '<div class="app-shell">' +
        '<header class="topbar">' +
          '<div class="brand" aria-label="Runner Strength">' +
            '<span class="brand-mark" aria-hidden="true">RS</span>' +
            '<span class="brand-copy"><strong>Runner Strength</strong><span>Private training planner</span></span>' +
          "</div>" +
          (deferredInstallPrompt ? '<button type="button" class="install-button" data-action="install">Install</button>' : "") +
        "</header>" +

        '<section class="program-card" aria-label="Program selection">' +
          '<div class="program-switcher" role="tablist" aria-label="Training program">' +
            renderProgramChoices(program) +
          "</div>" +
          '<div class="program-summary">' +
            '<div class="program-heading-row">' +
              "<div>" +
                '<p class="eyebrow">' + program.weeks.length + " week program</p>" +
                '<h1 class="program-heading">' + escapeHtml(program.title) + "</h1>" +
                '<p class="program-focus">' + escapeHtml(focus) + (week.rpe ? " · " + escapeHtml(week.rpe) : "") + "</p>" +
              "</div>" +
              '<div class="completion-count"><strong>' + doneInProgram + "/" + totalInProgram + '</strong><span>complete</span></div>' +
            "</div>" +
            '<div class="progress-line">' +
              '<div class="meter" aria-label="' + completionPercent + '% of this program complete"><span style="width:' + completionPercent + '%"></span></div>' +
              "<small>" + completionPercent + "%</small>" +
            "</div>" +
          "</div>" +
        "</section>" +

        '<section class="race-panel" aria-labelledby="race-title">' +
          '<div class="race-panel-heading"><h2 id="race-title">Next race</h2><span class="race-private">Stored on this phone</span></div>' +
          '<div class="race-field"><label for="race-date">Race date</label><input id="race-date" type="date" value="' + escapeHtml(state.raceDate) + '"></div>' +
          '<p class="race-status">' + escapeHtml(race.text) + "</p>" +
        "</section>" +

        renderRaceAlert(race) +

        '<section class="week-card" aria-label="Current workout week">' +
          '<div class="week-nav">' +
            '<button type="button" class="nav-button" data-action="previous-week" aria-label="Previous week"' + previousDisabled + '>&lsaquo;</button>' +
            '<div class="week-label"><p class="week-name">Week ' + week.number + '</p><p class="week-context">' + escapeHtml(focus) + (week.rpe ? " · " + escapeHtml(week.rpe) : "") + "</p></div>" +
            '<button type="button" class="nav-button" data-action="next-week" aria-label="Next week"' + nextDisabled + '>&rsaquo;</button>' +
          "</div>" +
          '<div class="week-rail" aria-label="Jump to a week">' + renderWeekRail(program, week) + "</div>" +
          '<div class="week-progress"><strong>' + doneInWeek + " of " + week.sessions.length + " sessions complete</strong><span>Tap a session to view it</span></div>" +
          '<div class="session-list">' + week.sessions.map(renderSession).join("") + "</div>" +
        "</section>" +

        '<section class="progress-card" aria-labelledby="progress-title">' +
          '<div class="progress-heading"><h2 id="progress-title">Progress overview</h2><span>Tap a week to revisit it</span></div>' +
          '<div class="week-grid">' + renderWeekTiles(program, week) + "</div>" +
        "</section>" +

        '<p class="privacy-note">Your plan, race date, and progress stay in this browser. Nothing is sent anywhere.</p>' +
      "</div>"
    );

    const activeWeek = app.querySelector(".week-chip.is-current");
    if (activeWeek) {
      activeWeek.scrollIntoView({ block: "nearest", inline: "center" });
    }
  }

  function setWeek(number) {
    const program = getProgram();
    const next = Math.min(Math.max(Number(number) || 1, 1), program.weeks.length);
    state.lastViewedWeek[program.id] = next;
    saveState();
    render();
  }

  function switchProgram(programId) {
    if (!PROGRAMS[programId]) return;
    state.selectedProgram = programId;
    saveState();
    render();
  }

  function toggleComplete(sessionId) {
    if (isSessionComplete(sessionId)) {
      delete state.completed[sessionId];
    } else {
      state.completed[sessionId] = { completedAt: new Date().toISOString() };
    }
    saveState();
    render();
  }

  app.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;

    if (action === "switch-program") {
      switchProgram(button.dataset.program);
    } else if (action === "previous-week") {
      setWeek(getCurrentWeek(getProgram()).number - 1);
    } else if (action === "next-week") {
      setWeek(getCurrentWeek(getProgram()).number + 1);
    } else if (action === "jump-week") {
      setWeek(button.dataset.week);
    } else if (action === "toggle-session") {
      const sessionId = button.dataset.sessionId;
      if (ui.expandedSessions.has(sessionId)) {
        ui.expandedSessions.delete(sessionId);
      } else {
        ui.expandedSessions.add(sessionId);
      }
      render();
    } else if (action === "toggle-complete") {
      toggleComplete(button.dataset.sessionId);
    } else if (action === "switch-race") {
      switchProgram("race");
    } else if (action === "install" && deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      render();
    }
  });

  app.addEventListener("change", (event) => {
    if (event.target && event.target.id === "race-date") {
      state.raceDate = event.target.value || "";
      saveState();
      render();
    }
  });

  app.addEventListener("touchstart", (event) => {
    if (event.target.closest("button, input, summary, .week-rail")) return;
    const touch = event.changedTouches[0];
    ui.touchStart = { x: touch.clientX, y: touch.clientY };
  }, { passive: true });

  app.addEventListener("touchend", (event) => {
    if (!ui.touchStart) return;
    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - ui.touchStart.x;
    const deltaY = touch.clientY - ui.touchStart.y;
    ui.touchStart = null;
    if (Math.abs(deltaX) < 70 || Math.abs(deltaX) < Math.abs(deltaY) * 1.4) return;
    setWeek(getCurrentWeek(getProgram()).number + (deltaX < 0 ? 1 : -1));
  }, { passive: true });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    render();
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    render();
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./service-worker.js").catch(() => {});
    });
  }

  render();
})();
