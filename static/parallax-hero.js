
// Parallax Glow - gentle gradient following cursor
(function(){
  const hero = document.getElementById('hero');
  if(!hero) return;

  // create canvas overlay
  const c = document.createElement('canvas');
  c.id = 'hero-canvas';
  c.style.position = 'absolute';
  c.style.inset = '0';
  c.style.width = '100%';
  c.style.height = '100%';
  c.style.pointerEvents = 'none';
  hero.style.position = 'relative';
  hero.prepend(c);

  const ctx = c.getContext('2d');
  let w=0,h=0, dpr=1;
  function resize(){
    dpr = Math.max(1, window.devicePixelRatio || 1);
    w = hero.clientWidth;
    h = hero.clientHeight;
    c.width = Math.floor(w*dpr);
    c.height = Math.floor(h*dpr);
  }
  resize();
  window.addEventListener('resize', resize, {passive:true});

  let mx = 0.5, my = 0.5; // normalized cursor position
  let tx = 0.5, ty = 0.5; // target for easing
  hero.addEventListener('mousemove', (e)=>{
    const r = hero.getBoundingClientRect();
    tx = (e.clientX - r.left) / Math.max(1, r.width);
    ty = (e.clientY - r.top) / Math.max(1, r.height);
  }, {passive:true});

  // For touch / idle, slowly drift center
  let t0 = performance.now();
  function loop(t){
    const dt = Math.min(33, t - t0); t0 = t;

    // ease
    const ease = 0.06;
    mx += (tx - mx) * ease;
    my += (ty - my) * ease;

    // Draw smooth radial glows (two colors) with parallax offset
    ctx.clearRect(0,0,c.width,c.height);
    ctx.save();
    ctx.scale(dpr,dpr);

    const cx = w * mx;
    const cy = h * my;

    // background subtle vignette
    const gbg = ctx.createRadialGradient(w*0.5, h*0.5, Math.min(w,h)*0.2, w*0.5, h*0.5, Math.max(w,h)*0.75);
    gbg.addColorStop(0, 'rgba(10,12,20,0.05)');
    gbg.addColorStop(1, 'rgba(10,12,20,0.35)');
    ctx.fillStyle = gbg;
    ctx.fillRect(0,0,w,h);

    // cyan glow
    const g1 = ctx.createRadialGradient(cx - w*0.08, cy, 0, cx - w*0.08, cy, Math.max(w,h)*0.45);
    g1.addColorStop(0, 'rgba(0,255,220,0.55)');
    g1.addColorStop(1, 'rgba(0,255,220,0.0)');
    ctx.fillStyle = g1;
    ctx.fillRect(0,0,w,h);

    // purple glow
    const g2 = ctx.createRadialGradient(cx + w*0.06, cy, 0, cx + w*0.06, cy, Math.max(w,h)*0.40);
    g2.addColorStop(0, 'rgba(155, 80, 255, 0.45)');
    g2.addColorStop(1, 'rgba(155, 80, 255, 0.0)');
    ctx.fillStyle = g2;
    ctx.fillRect(0,0,w,h);

    ctx.restore();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
