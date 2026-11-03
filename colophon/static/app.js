// Colophon search page. State lives in the URL hash so results can be shared and the back button works:
//   #q=<text>&kind=&artist=&book=     search (empty q = browse the filtered set)
//   #works                            works reproduced in 2+ catalogues
//   #work?artist=&title=              one work across catalogues
//   #books                            the catalogues read so far
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var state = { q: '', kind: '', artist: '', book: '' };
  var lastHits = [], seq = 0;

  function getJSON(url) { return fetch(url).then(function (r) { return r.json(); }); }

  function card(h) {
    var title = h.title ? esc(h.title) : esc((h.depicts || 'Untitled').slice(0, 70));
    var meta = [h.year, h.medium].filter(Boolean).map(esc).join(' · ');
    return '<a class="card" href="' + esc(h.view) + '">' +
      '<div class="im"><img loading="lazy" src="' + esc(h.thumb_url || h.crop_url) + '" alt="' + esc(h.depicts || '') + '"></div>' +
      '<div class="t' + (h.title ? '' : ' untitled') + '">' + title + '</div>' +
      (h.artist ? '<div class="a">' + esc(h.artist) + '</div>' : '') +
      (meta ? '<div class="m">' + meta + '</div>' : '') +
      '<div class="b">' + esc(h.book_title || ('Book ' + h.book)) + (h.book_year ? ', ' + esc(h.book_year) : '') +
      ' · p. ' + h.page + '</div></a>';
  }

  function facetList(name, counts, active) {
    var keys = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); });
    if (active && keys.indexOf(active) < 0) keys.unshift(active);
    if (!keys.length) return '';
    return '<div><h3>' + name + '</h3><ul>' + keys.slice(0, 15).map(function (k) {
      return '<li><button data-facet="' + name.toLowerCase() + '" data-v="' + esc(k) + '"' +
        (k === active ? ' class="on"' : '') + '><span>' + esc(k) + '</span><span class="n">' +
        (counts[k] || '') + '</span></button></li>';
    }).join('') + '</ul></div>';
  }

  function renderFacets() {
    var kinds = {}, artists = {}, books = {};
    lastHits.forEach(function (h) {
      if (h.kind) kinds[h.kind] = (kinds[h.kind] || 0) + 1;
      if (h.artist) artists[h.artist] = (artists[h.artist] || 0) + 1;
    });
    var html = facetList('Kind', kinds, state.kind) + facetList('Artist', artists, state.artist);
    if (state.book) html += '<div><h3>Catalogue</h3><ul><li><button data-facet="book" data-v="' + esc(state.book) +
      '" class="on"><span>Book ' + esc(state.book) + '</span></button></li></ul></div>';
    $('facets').innerHTML = html;
  }

  function hashFor(s) {
    var p = new URLSearchParams();
    ['q', 'kind', 'artist', 'book'].forEach(function (k) { if (s[k]) p.set(k, s[k]); });
    return '#' + p.toString();
  }

  function search() {
    var my = ++seq, p = new URLSearchParams({ limit: 60 });
    ['q', 'kind', 'artist', 'book'].forEach(function (k) { if (state[k]) p.set(k, state[k]); });
    $('status').textContent = 'Searching…';
    getJSON('/api/search?' + p.toString()).then(function (r) {
      if (my !== seq) return;
      if (r.error) { $('status').textContent = 'Error: ' + r.error; return; }
      lastHits = r.hits || [];
      var filt = ['kind', 'artist', 'book'].filter(function (k) { return state[k]; })
        .map(function (k) { return k + ': ' + state[k]; }).join(', ');
      $('status').textContent = lastHits.length + ' figures' + (state.q ? ' for “' + state.q + '”' : '') +
        (filt ? ' (' + filt + ')' : '') + (r.ms && r.ms.total != null ? ' · ' + r.ms.total + ' ms' : '');
      $('grid').innerHTML = lastHits.map(card).join('');
      renderFacets();
    }).catch(function (e) { $('status').textContent = 'Search failed: ' + e; });
  }

  function showTab(name) {
    ['search', 'works', 'books'].forEach(function (t) {
      $('tab-' + t).hidden = t !== name;
      document.querySelector('[data-tab="' + t + '"]').classList.toggle('on', t === name);
    });
  }

  function workBlock(w) {
    var books = {};
    w.figures.forEach(function (f) { books[f.book] = 1; });
    return '<div class="work"><h2>' + esc(w.title || 'Untitled') + '</h2><div class="sub">' + esc(w.artist) +
      ' · reproduced in ' + Object.keys(books).length + ' catalogues, ' + w.figures.length + ' figures</div>' +
      '<div class="strip">' + w.figures.map(card).join('') + '</div></div>';
  }

  function loadWorks() {
    $('works-status').textContent = 'Loading…';
    getJSON('/api/works?min_books=2').then(function (r) {
      var ws = r.works || [];
      $('works-status').textContent = ws.length + ' works appear in more than one catalogue (matched on artist ' +
        'surname + title, so generic titles like “Landscape” can join different works).';
      $('works').innerHTML = ws.map(workBlock).join('');
    });
  }

  function loadWork(artist, title) {
    $('works-status').textContent = 'Loading…';
    getJSON('/api/work?' + new URLSearchParams({ artist: artist, title: title })).then(function (r) {
      if (r.error) { $('works-status').textContent = r.error; return; }
      $('works-status').innerHTML = '<a href="#works">← all works</a>';
      $('works').innerHTML = workBlock({ title: title, artist: artist, figures: r.figures || [] });
    });
  }

  function loadBooks() {
    $('books-status').textContent = 'Loading…';
    getJSON('/api/books').then(function (bs) {
      $('books-status').textContent = bs.length + ' catalogues read so far (the reading runs continuously).';
      $('books').innerHTML = bs.map(function (b) {
        var kinds = Object.keys(b.kinds || {}).slice(0, 3).join(', ');
        return '<a class="book" href="#book=' + b.id + '">' +
          (b.cover_crop ? '<img loading="lazy" src="/thumbs/' + esc(b.cover_crop.replace(/^crops\//, '')) + '" alt="">' : '<img alt="">') +
          '<div><div class="t">' + esc(b.title) + '</div><div class="m">' + esc(b.year) + ' · ' + b.figures +
          ' figures on ' + b.pages_read + (b.pages ? ' / ' + b.pages : '') + ' pages' +
          (kinds ? '<br>' + esc(kinds) : '') + '</div></div></a>';
      }).join('');
    });
  }

  function route() {
    var h = location.hash.slice(1);
    if (h === 'works') { showTab('works'); return loadWorks(); }
    if (h.indexOf('work?') === 0) {
      var wp = new URLSearchParams(h.slice(5)); showTab('works');
      return loadWork(wp.get('artist') || '', wp.get('title') || '');
    }
    if (h === 'books') { showTab('books'); return loadBooks(); }
    showTab('search');
    var p = new URLSearchParams(h);
    state = { q: p.get('q') || '', kind: p.get('kind') || '', artist: p.get('artist') || '', book: p.get('book') || '' };
    $('q').value = state.q;
    if (state.q || state.kind || state.artist || state.book) search();
    else { $('grid').innerHTML = ''; $('facets').innerHTML = ''; $('status').textContent = ''; }
  }

  $('form').addEventListener('submit', function (e) {
    e.preventDefault();
    var s = { q: $('q').value.trim(), kind: '', artist: '', book: state.book };
    location.hash = hashFor(s);
  });
  $('facets').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-facet]');
    if (!b) return;
    var f = b.dataset.facet, v = b.dataset.v, s = Object.assign({}, state);
    s[f] = s[f] === v ? '' : v;
    location.hash = hashFor(s);
  });
  document.querySelector('.tabs').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-tab]');
    if (!b) return;
    location.hash = b.dataset.tab === 'search' ? hashFor(state) : b.dataset.tab;
  });
  window.addEventListener('hashchange', route);

  getJSON('/api/stats').then(function (s) {
    $('stats').innerHTML = s.figures + ' figures from ' + s.pages + ' pages of ' + s.books +
      ' MoMA catalogues so far · try <a href="#q=a+woman+reading+a+letter">a woman reading a letter</a>, ' +
      '<a href="#q=water+tower">water tower</a>, <a href="#q=model+of+a+building">model of a building</a>';
  }).catch(function () {});
  route();
})();
