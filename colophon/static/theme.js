// Colophon: apply the saved theme before first paint; the ◐ button cycles auto → light → dark.
(function () {
  var d = document.documentElement, t = 'auto';
  try { t = localStorage.getItem('colophon.theme') || 'auto'; } catch (e) {}
  d.dataset.theme = t;
  document.addEventListener('DOMContentLoaded', function () {
    var b = document.getElementById('theme');
    if (!b) return;
    b.title = 'Theme: ' + d.dataset.theme;
    b.addEventListener('click', function () {
      var order = ['auto', 'light', 'dark'], n = order[(order.indexOf(d.dataset.theme) + 1) % 3];
      d.dataset.theme = n; b.title = 'Theme: ' + n;
      try { localStorage.setItem('colophon.theme', n); } catch (e) {}
    });
  });
})();
