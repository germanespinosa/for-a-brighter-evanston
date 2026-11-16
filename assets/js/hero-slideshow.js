/* Decorative home-page photographs; each later image is fetched on demand. */
(() => {
  const hero = document.querySelector('.release-home [data-hero-slideshow]');
  if (!hero) return;
  const slides = Array.from(hero.querySelectorAll('[data-hero-slide]'));
  const button = hero.querySelector('[data-hero-pause]');
  if (slides.length < 2 || !button) return;

  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let current = 0;
  let candidate = 1;
  let timer;
  let cancelPending = () => {};
  let paused = false;
  let generation = 0;
  const running = () => !paused && !document.hidden && !motion.matches;

  function schedule() {
    clearTimeout(timer);
    cancelPending();
    generation += 1;
    button.hidden = motion.matches;
    button.textContent = paused ? button.dataset.play : button.dataset.pause;
    if (!running()) return;
    const token = generation;
    timer = setTimeout(() => {
      const next = candidate;
      const image = slides[next];
      const show = () => {
        if (token !== generation || !running()) return;
        slides[current].removeAttribute('data-active');
        image.dataset.active = 'true';
        current = next;
        candidate = (next + 1) % slides.length;
        schedule();
      };
      const failed = () => {
        if (token !== generation) return;
        candidate = (next + 1) % slides.length;
        schedule();
      };
      image.addEventListener('load', show);
      image.addEventListener('error', failed);
      cancelPending = () => {
        image.removeEventListener('load', show);
        image.removeEventListener('error', failed);
        cancelPending = () => {};
      };
      if (!image.getAttribute('src')) image.src = image.dataset.src;
      if (image.complete) {
        if (image.naturalWidth) show(); else failed();
      } else {
        timer = setTimeout(failed, 4000);
      }
    }, 8000);
  }

  button.addEventListener('click', () => { paused = !paused; schedule(); });
  document.addEventListener('visibilitychange', schedule);
  motion.addEventListener('change', schedule);
  schedule();
})();
