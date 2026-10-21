/* Interactions légères : pré-remplissage, filtrage et saisie rétroactive. */
(function () {
  "use strict";

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  /* --- 1. Dérogation obligatoire dès qu'une date d'effet est passée ----- */
  function setupBackdating() {
    var today = todayISO();
    document.querySelectorAll("[data-backdate-source]").forEach(function (input) {
      var block = document.getElementById("derogation-block");
      if (!block) {
        return;
      }
      var refresh = function () {
        var value = (input.value || "").trim();
        var isPast = value !== "" && value < today;
        block.style.display = isPast ? "block" : "none";
        var area = block.querySelector("textarea");
        if (area) {
          area.required = isPast;
        }
      };
      input.addEventListener("change", refresh);
      input.addEventListener("input", refresh);
      refresh();
    });
  }

  /* --- 2. Pré-remplissage depuis le type d'équipement ---------------------- */
  function setupPrefill() {
    var select = document.querySelector("[data-prefill]");
    if (!select) {
      return;
    }
    var targets = (select.getAttribute("data-prefill-target") || "").split(",");
    var apply = function () {
      var option = select.options[select.selectedIndex];
      if (!option || !option.value) {
        return;
      }
      targets.forEach(function (id) {
        var field = document.getElementById(id);
        if (!field || field.value) {
          return;
        }
        var value = option.getAttribute("data-" + id.replace("eq-", "")) || "";
        field.value = value;
      });
    };
    select.addEventListener("change", apply);
  }

  /* --- 3. Filtrage des emplacements selon l'usine choisie ----------------- */
  function setupLocationFilter() {
    var siteSelect = document.querySelector("[data-location-filter]");
    var locationSelect = document.getElementById("eq-location");
    if (!siteSelect || !locationSelect) {
      return;
    }
    var refresh = function () {
      var siteId = siteSelect.value;
      Array.prototype.forEach.call(locationSelect.options, function (option) {
        if (!option.value) {
          option.hidden = false;
          return;
        }
        var match = option.getAttribute("data-site") === siteId;
        option.hidden = !match;
        option.disabled = !match;
      });
    };
    siteSelect.addEventListener("change", refresh);
    refresh();
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupBackdating();
    setupPrefill();
    setupLocationFilter();
  });
})();
