// ===== EduVision AI — shared interactions =====

// Scroll-triggered reveal
document.addEventListener('DOMContentLoaded', () => {
  const revealEls = document.querySelectorAll('.reveal');
  if (revealEls.length) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.2 });
    revealEls.forEach(el => io.observe(el));
  }

  // Generic toggle switches
  document.querySelectorAll('.toggle').forEach(t => {
    t.addEventListener('click', () => t.classList.toggle('on'));
  });

  // Generic tab sets: [data-tabset] wraps .tab-item[data-tab] + [data-panel]
  document.querySelectorAll('[data-tabset]').forEach(set => {
    const items = set.querySelectorAll('.tab-item');
    items.forEach(item => {
      item.addEventListener('click', () => {
        items.forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        const target = item.getAttribute('data-tab');
        const scope = document.querySelector(set.getAttribute('data-tabset'));
        if (scope) {
          scope.querySelectorAll('[data-panel]').forEach(p => {
            p.style.display = (p.getAttribute('data-panel') === target) ? '' : 'none';
          });
        }
      });
    });
  });
});
