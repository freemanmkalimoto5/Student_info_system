/*
 * Skeleton loading for the whole system.
 *
 *  1. PAGE CHANGES  - the moment someone clicks a link or submits a form, the
 *     page content is swapped for a grey "skeleton" shaped like the page they
 *     are going to, until the next page arrives. (A skeleton only appears if
 *     the wait is longer than SHOW_DELAY_MS, so fast pages never flash.)
 *  2. IMAGES        - photos, QR codes and logos shimmer until they finish loading.
 *  3. LIVE SEARCH   - live_search.js uses Skeleton.tableHtml() for its table.
 *
 * Opt a link or form out with the attribute  data-no-skeleton.
 */
(function () {
    'use strict';

    var SHOW_DELAY_MS = 150;     // faster than this = no skeleton at all
    var SAFETY_MS = 25000;       // if a navigation never finishes, give the page back
    var showTimer = null;
    var safetyTimer = null;

    // Links/forms that end in a file download never replace the page, so no skeleton.
    var DOWNLOAD_LIKE = /(\/download\/|\/export\/|\/report\/pdf\/|[?&]sample=1|\.(pdf|xlsx|xlsm|xls|csv|zip|png|jpe?g)$|^\/(media|static)\/)/i;

    // Which skeleton shape fits which destination.
    var ROUTES = [
        [/^\/students\/?$/, 'students'],
        [/^\/students\/(new|\d+\/edit|import)\/?$/, 'form'],
        [/^\/students\/\d+\/?$/, 'detail'],
        [/^\/qrcodes\/?$/, 'qr'],
        [/^\/qrcodes\/id-cards\/?$/, 'idcards'],
        [/^\/accounts\/administrators\/?$/, 'cards'],
        [/^\/accounts\/(settings|add-admin|complete-profile)\/?$/, 'form'],
        [/^\/accounts\/audit-log\/?$/, 'list'],
        [/^\/notifications\/?$/, 'list'],
        [/^\/pocketmoney\/\d+\/?$/, 'list'],
        [/^\/lostitems\/student\/\d+\/report\/?$/, 'list'],
        [/^\/lostitems\//, 'form'],
        [/^\/pocketmoney\//, 'form']
    ];

    // ---------------------------------------------------------------- shapes
    function d(cls, style) {
        return '<div class="sk ' + cls + '"' + (style ? ' style="' + style + '"' : '') + '></div>';
    }
    function times(n, fn) {
        var out = '';
        for (var i = 0; i < n; i++) { out += fn(i); }
        return out;
    }
    function tableRow() {
        return '<div class="sk-tr">' + d('sk-thumb') + d('sk-cell', 'width:12%') + d('sk-cell', 'width:28%') +
               d('sk-cell', 'width:14%') + d('sk-cell', 'width:10%') + d('sk-btn') + '</div>';
    }
    function tableHtml(rows) {
        return '<div class="sk-table" aria-hidden="true">' + times(rows || 7, tableRow) + '</div>';
    }
    function formBox() {
        return '<div class="sk-box">' + d('sk-line', 'width:22%;height:16px') +
               '<div class="sk-fields">' + times(4, function () { return d('sk-field'); }) + '</div></div>';
    }

    var SHAPES = {
        students: function () {
            return d('sk-title') +
                   '<div class="sk-stats">' + times(7, function () { return d('sk-stat'); }) + '</div>' +
                   d('sk-input') + tableHtml(8);
        },
        form: function () {
            return d('sk-title') + times(3, formBox);
        },
        detail: function () {
            return '<div class="sk-head">' + d('sk-avatar big') +
                   '<div style="flex:1">' + d('sk-line', 'width:40%;height:20px') + d('sk-line', 'width:25%') + '</div></div>' +
                   '<div class="sk-grid cards">' +
                   times(4, function () {
                       return '<div class="sk-box">' + d('sk-line', 'width:30%;height:16px') +
                              times(4, function () { return d('sk-line'); }) + '</div>';
                   }) + '</div>';
        },
        cards: function () {
            return d('sk-title') +
                   '<div class="sk-stats">' + times(4, function () { return d('sk-stat'); }) + '</div>' +
                   d('sk-input') +
                   '<div class="sk-grid cards">' +
                   times(6, function () {
                       return '<div class="sk-box"><div class="sk-head">' + d('sk-avatar') +
                              '<div style="flex:1">' + d('sk-line', 'width:60%;height:16px') + d('sk-line', 'width:35%') + '</div></div>' +
                              times(5, function () { return d('sk-line'); }) + '</div>';
                   }) + '</div>';
        },
        qr: function () {
            return d('sk-title') +
                   '<div class="sk-toolbar">' + times(3, function () { return d('sk-pill'); }) + '</div>' +
                   '<div class="sk-grid tiles">' +
                   times(14, function () {
                       return '<div>' + d('sk-square') + d('sk-line', 'width:60%;margin:8px auto 4px') + d('sk-line', 'width:80%;margin:4px auto') + '</div>';
                   }) + '</div>';
        },
        idcards: function () {
            return d('sk-title') +
                   '<div class="sk-toolbar">' + times(3, function () { return d('sk-pill'); }) + '</div>' +
                   '<div class="sk-grid idc">' +
                   times(6, function () {
                       return '<div class="sk-box sk-center">' + d('sk-strip') + d('sk-avatar') +
                              d('sk-line', 'width:70%;margin-top:12px') + d('sk-line', 'width:50%') +
                              d('sk-square', 'width:78px;margin-top:10px') + '</div>';
                   }) + '</div>';
        },
        list: function () {
            return d('sk-title') +
                   '<div class="sk-table">' +
                   times(7, function () {
                       return '<div class="sk-tr">' + d('sk-cell', 'width:16%') + d('sk-cell', 'width:12%') +
                              d('sk-cell', 'width:34%') + d('sk-cell', 'width:16%') + '</div>';
                   }) + '</div>';
        },
        generic: function () {
            return d('sk-title') +
                   times(2, function () {
                       return '<div class="sk-box">' + d('sk-line', 'width:30%;height:16px') +
                              times(4, function () { return d('sk-line'); }) + '</div>';
                   });
        }
    };

    function variantFor(pathname) {
        for (var i = 0; i < ROUTES.length; i++) {
            if (ROUTES[i][0].test(pathname)) { return ROUTES[i][1]; }
        }
        return 'generic';
    }

    // ------------------------------------------------------- show / hide
    function show(variant) {
        if (document.getElementById('sk-overlay')) { return; }
        var main = document.querySelector('main.container') || document.querySelector('.container');
        if (!main) { return; }
        var wrap = document.createElement('div');
        wrap.id = 'sk-overlay';
        wrap.setAttribute('aria-hidden', 'true');
        wrap.innerHTML = (SHAPES[variant] || SHAPES.generic)();
        main.appendChild(wrap);
        document.body.classList.add('sk-active');
        document.documentElement.setAttribute('aria-busy', 'true');
        clearTimeout(safetyTimer);
        safetyTimer = setTimeout(hide, SAFETY_MS);
    }

    function hide() {
        clearTimeout(showTimer);
        clearTimeout(safetyTimer);
        var overlay = document.getElementById('sk-overlay');
        if (overlay && overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
        document.body.classList.remove('sk-active');
        document.documentElement.removeAttribute('aria-busy');
    }

    function schedule(variant) {
        clearTimeout(showTimer);
        showTimer = setTimeout(function () { show(variant); }, SHOW_DELAY_MS);
    }

    // ------------------------------------------------- links and forms
    function linkTarget(a, e) {
        if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) { return null; }
        if ((a.target && a.target !== '_self') || a.hasAttribute('download') || a.hasAttribute('data-no-skeleton')) { return null; }
        var raw = a.getAttribute('href') || '';
        if (!raw || raw.charAt(0) === '#' || /^(javascript|mailto|tel):/i.test(raw)) { return null; }
        var url;
        try { url = new URL(a.href, window.location.href); } catch (err) { return null; }
        if (url.origin !== window.location.origin) { return null; }
        if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) { return null; }
        if (DOWNLOAD_LIKE.test(url.pathname + url.search)) { return null; }
        return url;
    }

    document.addEventListener('click', function (e) {
        var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
        var url = a ? linkTarget(a, e) : null;
        if (url) { schedule(variantFor(url.pathname)); }
    });

    document.addEventListener('submit', function (e) {
        var form = e.target;
        // defaultPrevented = a confirm() said no, or the page handles this form with fetch()
        if (!form || e.defaultPrevented || form.target === '_blank' || form.hasAttribute('data-no-skeleton')) { return; }
        var url;
        try { url = new URL(form.getAttribute('action') || window.location.href, window.location.href); } catch (err) { return; }
        if (url.origin !== window.location.origin || DOWNLOAD_LIKE.test(url.pathname + url.search)) { return; }
        var isGet = (form.getAttribute('method') || 'get').toLowerCase() === 'get';
        // after a POST we do not know where the redirect lands, so use the neutral shape
        schedule(isGet ? variantFor(url.pathname) : 'generic');
    });

    // Back/forward cache can restore a page with the skeleton still on it; Esc cancels it.
    window.addEventListener('pageshow', function (e) { if (e.persisted) { hide(); } });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { hide(); } });

    // ------------------------------------------------------------ images
    function watchImages(root) {
        var images = (root || document).querySelectorAll('img');
        for (var i = 0; i < images.length; i++) {
            (function (img) {
                if (img.complete || !img.getAttribute('src')) { return; }   // already loaded / nothing to load
                img.classList.add('sk-img');
                function done() { img.classList.remove('sk-img'); }
                img.addEventListener('load', done, { once: true });
                img.addEventListener('error', done, { once: true });
            })(images[i]);
        }
    }

    document.addEventListener('DOMContentLoaded', function () { watchImages(document); });

    window.Skeleton = {
        show: show,
        hide: hide,
        tableHtml: tableHtml,
        watchImages: watchImages,
        variantFor: variantFor,
        isDownloadLike: function (s) { return DOWNLOAD_LIKE.test(s); }
    };
})();
