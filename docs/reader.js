/* ══════════════════════════════════════════════
   MangaStudio Reader — JavaScript
   Lazy loading · Progress bar · Keyboard nav
   ══════════════════════════════════════════════ */

(function () {
  'use strict';

  // ── Progress Bar ──
  const progressBar = document.querySelector('.progress-bar');
  if (progressBar) {
    window.addEventListener('scroll', () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
      progressBar.style.width = pct + '%';
    }, { passive: true });
  }

  // ── Lazy Loading (IntersectionObserver) ──
  const lazyImages = document.querySelectorAll('.reader__page[data-src]');
  if (lazyImages.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const container = entry.target;
          const src = container.getAttribute('data-src');
          const skeleton = container.querySelector('.skeleton');
          const img = new Image();
          img.onload = function () {
            if (skeleton) skeleton.remove();
            container.appendChild(img);
            container.classList.add('loaded');
          };
          img.onerror = function () {
            if (skeleton) skeleton.textContent = '圖片載入失敗';
          };
          img.src = src;
          img.alt = container.getAttribute('data-alt') || '漫畫頁';
          observer.unobserve(container);
        }
      });
    }, {
      rootMargin: '600px 0px',   // 提前 600px 開始載入
      threshold: 0.01
    });

    lazyImages.forEach((el) => observer.observe(el));
  }

  // ── FAB: Back to Top ──
  const fab = document.querySelector('.fab-top');
  if (fab) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 600) {
        fab.classList.add('visible');
      } else {
        fab.classList.remove('visible');
      }
    }, { passive: true });

    fab.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ── Nav auto-hide on reader pages ──
  const nav = document.querySelector('.nav');
  if (nav && document.querySelector('.reader')) {
    let lastY = 0;
    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const curY = window.scrollY;
          if (curY > lastY && curY > 200) {
            nav.classList.add('hidden');
          } else {
            nav.classList.remove('hidden');
          }
          lastY = curY;
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  // ── Keyboard Navigation (reader pages) ──
  const readerNav = document.querySelector('.reader-nav');
  if (readerNav) {
    document.addEventListener('keydown', (e) => {
      // ArrowLeft / ArrowRight for prev/next chapter
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const links = readerNav.querySelectorAll('a.reader-nav__btn');
        links.forEach((link) => {
          const rel = link.getAttribute('data-rel');
          if (e.key === 'ArrowLeft' && rel === 'prev') {
            window.location.href = link.href;
          }
          if (e.key === 'ArrowRight' && rel === 'next') {
            window.location.href = link.href;
          }
        });
      }
      // Home key → top
      if (e.key === 'Home') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  // ── Card expand/collapse (index page) ──
  document.querySelectorAll('.card[data-expandable]').forEach((card) => {
    const header = card.querySelector('.card__body');
    if (header) {
      header.addEventListener('click', (e) => {
        e.preventDefault();
        card.classList.toggle('expanded');
      });
    }
  });

})();
