/* ==========================================================================
   Campus Equipment System — progressive enhancement only.
   Everything here is optional: the site works without JavaScript.
   ========================================================================== */
(function () {
    "use strict";

    var body = document.body;

    /* ---------------------------------------------------------------- Nav */
    var sidebar = document.getElementById("app-sidebar");
    var navToggle = document.querySelector("[data-nav-toggle]");
    var navOverlay = document.querySelector("[data-nav-overlay]");
    var navClose = document.querySelector("[data-nav-close]");

    function isNarrow() {
        // Defines the mobile/tablet breakpoint (1100px and below)
        return window.matchMedia("(max-width: 1100px)").matches;
    }

    function openNav() {
        // Defensive guard: kung walang sidebar o KUNG HINDI narrow ang screen, walang mangyayari
        if (!sidebar || !isNarrow()) return;

        sidebar.classList.add("is-open");
        body.classList.add("nav-open");
        if (navOverlay) navOverlay.hidden = false;
        if (navToggle) navToggle.setAttribute("aria-expanded", "true");
        var first = sidebar.querySelector(".nav-item, button, a");
        if (first) first.focus({ preventScroll: true });
    }

    function closeNav(returnFocus) {
        if (!sidebar) return;
        sidebar.classList.remove("is-open");
        body.classList.remove("nav-open");
        if (navOverlay) navOverlay.hidden = true;
        if (navToggle) {
            navToggle.setAttribute("aria-expanded", "false");
            if (returnFocus && isNarrow()) navToggle.focus({ preventScroll: true });
        }
    }

    if (navToggle) {
        navToggle.addEventListener("click", function () {
            if (sidebar && sidebar.classList.contains("is-open")) {
                closeNav(true);
            } else {
                openNav();
            }
        });
    }

    if (navOverlay) {
        navOverlay.addEventListener("click", function () {
            closeNav(true);
        });
    }

    if (navClose) {
        navClose.addEventListener("click", function () {
            closeNav(true);
        });
    }

    if (sidebar) {
        sidebar.addEventListener("click", function (event) {
            if (isNarrow() && event.target.closest(".nav-item")) closeNav(false);
        });
    }

    window.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && body.classList.contains("nav-open")) {
            closeNav(true);
        }
    });

    window.addEventListener("resize", function () {
        // Kung lumaki ang screen lagpas 1100px, i-close automatically ang nav
        if (!isNarrow() && body.classList.contains("nav-open")) closeNav(false);
    });

    /* ------------------------------------------------------- User menu */
    var menus = Array.prototype.slice.call(document.querySelectorAll(".user-menu"));
    menus.forEach(function (menu) {
        menu.addEventListener("toggle", function () {
            if (!menu.open) return;
            menus.forEach(function (other) {
                if (other !== menu) other.open = false;
            });
        });
    });

    document.addEventListener("click", function (event) {
        menus.forEach(function (menu) {
            if (menu.open && !menu.contains(event.target)) menu.open = false;
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        menus.forEach(function (menu) {
            if (!menu.open) return;
            menu.open = false;
            var summary = menu.querySelector("summary");
            if (summary) summary.focus({ preventScroll: true });
        });
    });

    /* --------------------------------------------------- Toasts */
    var toasts = Array.prototype.slice.call(document.querySelectorAll("[data-toast]"));

    function dismissToast(toast) {
        if (!toast || toast.classList.contains("is-leaving")) return;
        toast.classList.add("is-leaving");
        window.setTimeout(function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
            var stack = document.querySelector(".toast-stack");
            if (stack && !stack.querySelector("[data-toast]")) stack.remove();
        }, 220);
    }

    toasts.forEach(function (toast) {
        var close = toast.querySelector("[data-dismiss]");
        if (close) {
            close.addEventListener("click", function () {
                dismissToast(toast);
            });
        }
        window.setTimeout(function () {
            dismissToast(toast);
        }, 6500);
    });

    /* --------------------------------------------- Confirmation dialog */
    var dialog = null;
    var dialogMessage = null;
    var pendingResolve = null;

    function buildDialog() {
        dialog = document.createElement("dialog");
        dialog.className = "confirm-dialog";
        dialog.innerHTML =
            '<form method="dialog" class="confirm-dialog__panel">' +
            '<span class="confirm-dialog__icon" aria-hidden="true">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" ' +
            'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.5 20h19Z"/>' +
            '<path d="M12 9v4"/><path d="M12 17h.01"/></svg></span>' +
            '<h2 class="confirm-dialog__title">Confirm action</h2>' +
            '<p class="confirm-dialog__text" data-confirm-message></p>' +
            '<div class="confirm-dialog__actions">' +
            '<button class="btn btn--outline" type="submit" value="cancel" autofocus>Cancel</button>' +
            '<button class="btn btn--danger" type="submit" value="confirm">Confirm</button>' +
            "</div></form>";
        document.body.appendChild(dialog);
        dialogMessage = dialog.querySelector("[data-confirm-message]");

        dialog.addEventListener("close", function () {
            var resolve = pendingResolve;
            pendingResolve = null;
            if (resolve) resolve(dialog.returnValue === "confirm");
        });

        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                dialog.close("cancel");
            }
        });
    }

    function askConfirm(message) {
        if (typeof dialog === "undefined" || dialog === null) buildDialog();
        if (typeof dialog.showModal !== "function") {
            return Promise.resolve(window.confirm(message));
        }
        dialogMessage.textContent = message;
        dialog.returnValue = "cancel";
        pendingResolve = null;
        return new Promise(function (resolve) {
            pendingResolve = resolve;
            dialog.showModal();
        });
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest("[data-confirm]");
        if (!trigger || trigger.dataset.confirmBusy === "true") return;

        var message = trigger.getAttribute("data-confirm");
        if (!message) return;

        event.preventDefault();
        trigger.dataset.confirmBusy = "true";

        askConfirm(message).then(function (confirmed) {
            delete trigger.dataset.confirmBusy;
            if (!confirmed) return;

            if (trigger.tagName === "A" && trigger.href) {
                window.location.href = trigger.href;
            } else if (trigger.form) {
                trigger.form.requestSubmit(trigger);
            } else {
                trigger.removeAttribute("data-confirm");
                trigger.click();
            }
        });
    });

    /* -------------------------------------------------- Password reveal */
    document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
        button.addEventListener("click", function () {
            var target = document.getElementById(button.getAttribute("data-password-toggle"));
            if (!target) return;
            var show = target.type === "password";
            target.type = show ? "text" : "password";
            button.setAttribute("aria-pressed", show ? "true" : "false");
            button.setAttribute("aria-label", show ? "Hide password" : "Show password");
            var icon = button.querySelector("use");
            if (icon) icon.setAttribute("href", show ? "#i-eye-off" : "#i-eye");
        });
    });

    /* ------------------------------------- Request history status filter */
    var filterBar = document.querySelector("[data-request-filter]");
    if (filterBar) {
        var filterButtons = Array.prototype.slice.call(
            filterBar.querySelectorAll("[data-status]")
        );
        var requestCards = Array.prototype.slice.call(
            document.querySelectorAll("[data-request-status]")
        );
        var emptyFilter = document.querySelector("[data-filter-empty]");

        function applyFilter(status) {
            var visible = 0;
            requestCards.forEach(function (card) {
                var show = status === "all" || card.getAttribute("data-request-status") === status;
                card.hidden = !show;
                if (show) visible += 1;
            });
            if (emptyFilter) emptyFilter.hidden = visible !== 0;
            filterButtons.forEach(function (button) {
                var active = button.getAttribute("data-status") === status;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }

        filterButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                applyFilter(button.getAttribute("data-status"));
            });
        });
    }

    /* --------------------------------------- Collapse details on outside click */
    document.addEventListener("click", function (event) {
        document.querySelectorAll("details.action-dropdown[open], details.row-actions[open]").forEach(
            function (details) {
                if (!details.contains(event.target)) details.open = false;
            }
        );
    });

    /* ------------------------------------------------ Sticky header shadow */
    var topbar = document.querySelector(".topbar");
    if (topbar) {
        var sentinel = document.createElement("div");
        sentinel.setAttribute("aria-hidden", "true");
        sentinel.style.cssText = "position:absolute;top:0;height:1px;width:1px;";
        document.body.appendChild(sentinel);
        if ("IntersectionObserver" in window) {
            new IntersectionObserver(
                function (entries) {
                    topbar.classList.toggle("is-scrolled", !entries[0].isIntersecting);
                },
                { threshold: 0 }
            ).observe(sentinel);
        }
    }
})();