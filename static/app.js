(function() {
  const root = document.documentElement;
  const header = document.querySelector('.site-header');
  if (!header) return;

  function update(e){
    const rect = header.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // clamp a bit within header
    const clampedX = Math.max(0, Math.min(rect.width, x));
    const clampedY = Math.max(0, Math.min(rect.height, y));
    root.style.setProperty('--mx', clampedX + 'px');
    root.style.setProperty('--my', clampedY + 'px');
  }

  header.addEventListener('mousemove', update, { passive: true });
  // center-ish on load
  const initX = header.clientWidth * 0.3;
  const initY = header.clientHeight * 0.2;
  root.style.setProperty('--mx', initX + 'px');
  root.style.setProperty('--my', initY + 'px');
})();
