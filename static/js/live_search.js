document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('student-search-input');
    var container = document.getElementById('student-table-container');

    // Only runs on pages that actually have the search box + table
    // (i.e. the student list) — silently does nothing everywhere else.
    if (!input || !container) {
        return;
    }

    var DEBOUNCE_MS = 350;
    var SKELETON_DELAY_MS = 120;     // quick answers never flash a skeleton
    var debounceTimer = null;
    var skeletonTimer = null;
    var requestId = 0;               // so a slow, older answer can't overwrite a newer one
    var skeletonShown = false;
    var lastHtml = '';

    function startLoading() {
        clearTimeout(skeletonTimer);
        skeletonShown = false;
        lastHtml = container.innerHTML;
        skeletonTimer = setTimeout(function () {
            if (window.Skeleton) {
                skeletonShown = true;
                container.innerHTML = window.Skeleton.tableHtml(7);
            }
        }, SKELETON_DELAY_MS);
    }

    function finishLoading() {
        clearTimeout(skeletonTimer);
        skeletonShown = false;
    }

    function load(fetchUrl, historyUrl) {
        var mine = ++requestId;
        startLoading();

        fetch(fetchUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (response) { return response.text(); })
            .then(function (html) {
                if (mine !== requestId) { return; }      // a newer search already started
                finishLoading();
                container.innerHTML = html;
                if (window.Skeleton) { window.Skeleton.watchImages(container); }
                window.history.replaceState({}, '', historyUrl);
            })
            .catch(function () {
                if (mine !== requestId) { return; }
                // Network hiccup: put the previous table back rather than leaving
                // the grey skeleton, so the user doesn't lose their view.
                if (skeletonShown) { container.innerHTML = lastHtml; }
                finishLoading();
            });
    }

    function runSearch() {
        var url = new URL(window.location.href);
        url.searchParams.set('q', input.value);
        url.searchParams.delete('page'); // a new search always starts at page 1
        load(url.toString(), url.toString());
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
        load(link.href, link.href);
    });
});
