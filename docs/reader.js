/* ══════════════════════════════════════════════
   MangaStudio Reader — JavaScript
   翻頁模式（按一下跳一頁）＋ 捲動模式，可切換
   ══════════════════════════════════════════════ */

(function () {
  'use strict';

  var MODE_KEY = 'ms-reader-mode';   // 'paged' | 'scroll'

  // ── 共用：載入某頁的圖片（懶載入用） ──
  function loadPageImage(container) {
    if (!container || container.dataset.loaded) return;
    var src = container.getAttribute('data-src');
    if (!src) return;
    container.dataset.loaded = '1';
    var skeleton = container.querySelector('.skeleton');
    var img = new Image();
    img.onload = function () {
      if (skeleton) skeleton.remove();
      container.appendChild(img);
      container.classList.add('loaded');
    };
    img.onerror = function () {
      container.dataset.loaded = '';
      if (skeleton) skeleton.textContent = '圖片載入失敗';
    };
    img.src = src;
    img.alt = container.getAttribute('data-alt') || '漫畫頁';
  }

  // ══════════════════════════════════════════════
  //  翻頁模式
  // ══════════════════════════════════════════════
  function initPaged(reader) {
    var pages = Array.prototype.slice.call(reader.querySelectorAll('.reader__page'));
    if (!pages.length) return;

    document.body.classList.add('paged');
    reader.classList.add('paged');

    var counter = document.createElement('div');
    counter.className = 'page-counter';
    document.body.appendChild(counter);

    var larr = document.createElement('button');
    larr.className = 'pager-arrow pager-arrow--left';
    larr.setAttribute('aria-label', '上一頁');
    larr.textContent = '‹';
    var rarr = document.createElement('button');
    rarr.className = 'pager-arrow pager-arrow--right';
    rarr.setAttribute('aria-label', '下一頁');
    rarr.textContent = '›';
    document.body.appendChild(larr);
    document.body.appendChild(rarr);

    var progressBar = document.querySelector('.progress-bar');
    var nextChap = document.querySelector('.reader-nav__btn[data-rel="next"]');
    var prevChap = document.querySelector('.reader-nav__btn[data-rel="prev"]');
    var idx = 0;

    function show(n) {
      idx = Math.max(0, Math.min(pages.length - 1, n));
      for (var i = 0; i < pages.length; i++) {
        pages[i].classList.toggle('active', i === idx);
      }
      [idx - 1, idx, idx + 1].forEach(function (i) {
        if (pages[i]) loadPageImage(pages[i]);
      });
      counter.textContent = (idx + 1) + ' / ' + pages.length;
      if (progressBar) progressBar.style.width = ((idx + 1) / pages.length * 100) + '%';
      larr.style.visibility = (idx === 0 && !prevChap) ? 'hidden' : 'visible';
      rarr.style.visibility = (idx === pages.length - 1 && !nextChap) ? 'hidden' : 'visible';
      reader.scrollTop = 0;
      if (history.replaceState) history.replaceState(null, '', '#p' + (idx + 1));
    }

    function next() {
      if (idx < pages.length - 1) show(idx + 1);
      else if (nextChap) window.location.href = nextChap.href;
    }
    function prev() {
      if (idx > 0) show(idx - 1);
      else if (prevChap) window.location.href = prevChap.href;
    }

    reader.addEventListener('click', function (e) {
      if (e.target.closest('a, button')) return;   // 別攔到連結/按鈕
      if (e.clientX > window.innerWidth * 0.5) next();
      else prev();
    });
    rarr.addEventListener('click', function (e) { e.stopPropagation(); next(); });
    larr.addEventListener('click', function (e) { e.stopPropagation(); prev(); });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
        e.preventDefault(); next();
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault(); prev();
      }
    });

    var m = (window.location.hash || '').match(/#p(\d+)/);
    show(m ? parseInt(m[1], 10) - 1 : 0);
  }

  // ══════════════════════════════════════════════
  //  捲動模式（原本的行為）
  // ══════════════════════════════════════════════
  function initScroll(reader) {
    // 懶載入
    var lazyImages = reader.querySelectorAll('.reader__page[data-src]');
    if (lazyImages.length && 'IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            loadPageImage(entry.target);
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '600px 0px', threshold: 0.01 });
      Array.prototype.forEach.call(lazyImages, function (el) { observer.observe(el); });
    } else {
      Array.prototype.forEach.call(lazyImages, loadPageImage);
    }

    // 進度條
    var progressBar = document.querySelector('.progress-bar');
    if (progressBar) {
      window.addEventListener('scroll', function () {
        var docH = document.documentElement.scrollHeight - window.innerHeight;
        progressBar.style.width = (docH > 0 ? (window.scrollY / docH) * 100 : 0) + '%';
      }, { passive: true });
    }

    // 導覽列自動隱藏
    var nav = document.querySelector('.nav');
    if (nav) {
      var lastY = 0, ticking = false;
      window.addEventListener('scroll', function () {
        if (!ticking) {
          window.requestAnimationFrame(function () {
            var curY = window.scrollY;
            if (curY > lastY && curY > 200) nav.classList.add('hidden');
            else nav.classList.remove('hidden');
            lastY = curY;
            ticking = false;
          });
          ticking = true;
        }
      }, { passive: true });
    }

    // 章節鍵盤（左右鍵跳上下一話）
    var readerNav = document.querySelector('.reader-nav');
    if (readerNav) {
      document.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          readerNav.querySelectorAll('a.reader-nav__btn').forEach(function (link) {
            var rel = link.getAttribute('data-rel');
            if (e.key === 'ArrowLeft' && rel === 'prev') window.location.href = link.href;
            if (e.key === 'ArrowRight' && rel === 'next') window.location.href = link.href;
          });
        }
        if (e.key === 'Home') { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
      });
    }

    // 回到頂部
    var fab = document.querySelector('.fab-top');
    if (fab) {
      window.addEventListener('scroll', function () {
        fab.classList.toggle('visible', window.scrollY > 600);
      }, { passive: true });
      fab.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
  }

  // ── 模式切換按鈕（塞進導覽列） ──
  function injectToggle(mode) {
    var links = document.querySelector('.nav__links');
    if (!links) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nav__link mode-toggle';
    btn.textContent = (mode === 'paged') ? '捲動模式' : '翻頁模式';
    btn.title = '切換閱讀方式';
    btn.addEventListener('click', function () {
      localStorage.setItem(MODE_KEY, mode === 'paged' ? 'scroll' : 'paged');
      window.location.reload();
    });
    links.insertBefore(btn, links.firstChild);
  }

  // ══════════════════════════════════════════════
  //  啟動
  // ══════════════════════════════════════════════
  var reader = document.querySelector('.reader');
  if (reader) {
    var mode = localStorage.getItem(MODE_KEY) || 'paged';   // 預設翻頁
    injectToggle(mode);
    if (mode === 'paged') initPaged(reader);
    else initScroll(reader);
  }

  // 首頁：多話卡片「整張」都能點來展開各話（點到某一話連結則正常跳轉）
  document.querySelectorAll('.card[data-expandable]').forEach(function (card) {
    card.addEventListener('click', function (e) {
      if (e.target.closest('a')) return;   // 點到話數連結 → 讓它跳轉
      e.preventDefault();
      card.classList.toggle('expanded');
    });
  });

})();
