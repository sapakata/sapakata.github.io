// Navbar scroll
const nav = document.querySelector('nav');
window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 60);
});

// Mobile nav
const burger = document.getElementById('nav-burger');
const mobileNav = document.getElementById('mobile-nav');
const mobileClose = document.getElementById('mobile-close');

burger.addEventListener('click', () => {
  mobileNav.classList.add('open');
  document.body.style.overflow = 'hidden';
});

mobileClose.addEventListener('click', () => {
  mobileNav.classList.remove('open');
  document.body.style.overflow = '';
});

mobileNav.querySelectorAll('a').forEach(a => {
  a.addEventListener('click', () => {
    mobileNav.classList.remove('open');
    document.body.style.overflow = '';
  });
});

// Scroll reveal
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// Contact form
const form = document.getElementById('contact-form');
if (form) {
  form.addEventListener('submit', e => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.textContent = 'Pesan Terkirim!';
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = 'Kirim Pesan';
      btn.disabled = false;
      form.reset();
    }, 3000);
  });
}

// ===== INSTAGRAM FEED via Behold =====
const BEHOLD_URL = 'https://feeds.behold.so/JI0dypackcxlUtk4dTHd';
const MAX_PHOTOS = 9;

async function loadInstagramFeed() {
  const grid = document.getElementById('instagram-grid');
  const loader = document.getElementById('ig-loading');

  try {
    const res = await fetch(BEHOLD_URL);
    if (!res.ok) throw new Error('Feed fetch failed');
    const data = await res.json();

    const posts = (data.posts || [])
      .filter(p => p.visibility === 'visible' && p.mediaType === 'IMAGE')
      .slice(0, MAX_PHOTOS);

    if (loader) loader.remove();

    if (posts.length === 0) {
      grid.innerHTML = '<p class="ig-empty">Belum ada foto di Instagram.</p>';
      return;
    }

    posts.forEach(post => {
      const imgUrl = post.sizes?.medium?.mediaUrl || post.mediaUrl;
      const caption = post.prunedCaption || post.caption || '';
      const link = post.permalink || '#';

      const item = document.createElement('a');
      item.className = 'photo-item';
      item.href = link;
      item.target = '_blank';
      item.rel = 'noopener noreferrer';
      item.setAttribute('aria-label', caption || 'Instagram post');

      const img = document.createElement('img');
      img.src = imgUrl;
      img.alt = caption;
      img.loading = 'lazy';

      const overlay = document.createElement('div');
      overlay.className = 'photo-overlay';
      if (caption) {
        overlay.innerHTML = `<span class="photo-caption">${caption}</span>`;
      }

      item.appendChild(img);
      item.appendChild(overlay);
      grid.appendChild(item);
    });

    // Re-run reveal observer on newly added items
    grid.querySelectorAll('.photo-item').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(16px)';
      el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
      setTimeout(() => {
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      }, 50 * Array.from(grid.children).indexOf(el));
    });

  } catch (err) {
    if (loader) loader.remove();
    grid.innerHTML = '<p class="ig-empty">Gagal memuat foto. Coba refresh halaman.</p>';
    console.error('Instagram feed error:', err);
  }
}

loadInstagramFeed();
