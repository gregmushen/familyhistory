/* Mushen Family History — interaction layer (frontend-spec.md §6, §9).
   No dependencies, no build step. */
(function () {
  'use strict';

  var props = {
    dividerStyle: 'dark',   // 'dark' | 'light'
    revealOnScroll: true
  };

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* — §9 dividerStyle, applied imperatively — */
  function applyDividers() {
    document.documentElement.setAttribute('data-dividers', props.dividerStyle);
  }

  /* — §6 index active state — */
  function initIndex() {
    var targets = document.querySelectorAll('[data-colophon], [data-era], [data-anchor]');
    var links = {};
    Array.prototype.forEach.call(document.querySelectorAll('[data-navlink]'), function (a) {
      links[a.getAttribute('href').slice(1)] = a;
    });
    if (!targets.length || !('IntersectionObserver' in window)) return;

    function clearAll() {
      Object.keys(links).forEach(function (id) {
        links[id].style.color = 'var(--color-text)';
        links[id].style.borderLeftColor = 'transparent';
      });
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var link = links[entry.target.id];
        if (!link) return;
        clearAll();
        link.style.color = 'var(--color-accent)';
        link.style.borderLeftColor = 'var(--color-accent)';
      });
    }, { rootMargin: '-40% 0px -55% 0px' });

    Array.prototype.forEach.call(targets, function (t) { io.observe(t); });

    /* — §6 index hover (non-active links only) — */
    Object.keys(links).forEach(function (id) {
      var a = links[id];
      a.addEventListener('mouseenter', function () {
        if (a.style.color === 'var(--color-accent)') return;
        a.style.background = 'color-mix(in srgb, var(--color-accent) 8%, transparent)';
      });
      a.addEventListener('mouseleave', function () { a.style.background = ''; });
    });
  }

  /* — §6 read progress — */
  function initProgress() {
    var bar = document.querySelector('[data-progress-bar]');
    var label = document.querySelector('[data-progress-label]');
    if (!bar) return;
    function update() {
      var el = document.documentElement;
      var max = el.scrollHeight - el.clientHeight;
      var pct = max > 0 ? Math.min(1, Math.max(0, el.scrollTop / max)) : 0;
      bar.style.width = (pct * 100).toFixed(1) + '%';
      if (label) label.textContent = Math.round(pct * 100) + '% read';
    }
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
  }

  /* — §6 scroll reveal —
     The hidden state already lives in CSS under .reveal-enabled (set by the head
     script). Here we only reveal, or stand the whole thing down. */
  function initReveal() {
    var root = document.documentElement;
    if (!props.revealOnScroll || reduceMotion || !('IntersectionObserver' in window)) {
      root.classList.remove('reveal-enabled');
      return;
    }
    var kids = document.querySelectorAll('[data-main] > section, [data-main] > [data-colophon], [data-main] > header');
    var io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('reveal-on');
        obs.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -10% 0px' });
    Array.prototype.forEach.call(kids, function (el) { io.observe(el); });
  }

  function init() {
    applyDividers();
    initIndex();
    initProgress();
    initReveal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
