document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('student-search-input');
    var container = document.getElementById('student-table-container');

    // Only runs on pages that actually have the search box + table
    // (i.e. the student list) — silently does nothing everywhere else.
    if (!input || !container) {
        return;
    }

    var debounceTimer = null;
    var DEBOUNCE_MS = 350;

    function runSearch() {
        var url = new URL(window.location.href);
        url.searchParams.set('q', input.value);
        url.searchParams.delete('page'); // a new search always starts at page 1

        fetch(url.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (response) { return response.text(); })
            .then(function (html) {
                container.innerHTML = html;
                window.history.replaceState({}, '', url.toString());
            })
            .catch(function () {
                // Network hiccup: leave the existing table as-is rather
                // than clearing it, so the user doesn't lose their view.
            });
    }

    input.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(runSearch, DEBOUNCE_MS);
    });

    // Handle clicking Previous/Next inside the live-loaded table
    // fragment without a full page reload.
    container.addEventListener('click', function (event) {
        var link = event.target.closest('.pagination a');
        if (!link) {
            return;
        }
        event.preventDefault();
        fetch(link.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (response) { return response.text(); })
            .then(function (html) {
                container.innerHTML = html;
                window.history.replaceState({}, '', link.href);
            });
    });
});
