(function () {
    "use strict";

    document.addEventListener("input", function (event) {
        const input = event.target.closest(
            "[data-admin-filter-search]"
        );

        if (!input) {
            return;
        }

        const details = input.closest("details");
        if (!details) {
            return;
        }

        const query = input.value.trim().toLocaleLowerCase();

        details.querySelectorAll(
            "[data-admin-filter-options] > li"
        ).forEach(function (item) {
            const link = item.querySelector("a");
            const label = link
                ? link.textContent.trim().toLocaleLowerCase()
                : "";

            item.hidden = query.length > 0 && !label.includes(query);
        });
    });
})();