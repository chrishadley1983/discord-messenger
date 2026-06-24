(function () {
  "use strict";

  // --- A: Bottom spacer for iframe content ---
  // Adds invisible space at the bottom so inputs can scroll to centre
  // above the on-screen keyboard (wvkbd ~300px)
  var isInIframe = window.self !== window.top;
  if (isInIframe) {
    var spacer = document.createElement("div");
    spacer.setAttribute("data-kiosk-spacer", "1");
    spacer.style.cssText =
      "height:50vh;width:100%;visibility:hidden;pointer-events:none;" +
      "position:relative;clear:both;flex-shrink:0;";
    document.body.appendChild(spacer);
  }

  // --- B: Scroll focused input into view above on-screen keyboard ---
  var FOCUSABLE = { INPUT: 1, TEXTAREA: 1, SELECT: 1 };
  var SKIP_TYPES = { hidden: 1, submit: 1, button: 1, reset: 1, image: 1 };
  var scrollTimer = null;

  document.addEventListener("focusin", function (e) {
    var el = e.target;
    if (!el || !FOCUSABLE[el.tagName]) return;
    if (el.type && SKIP_TYPES[el.type]) return;

    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function () {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      scrollTimer = null;
    }, 350);
  });
})();
