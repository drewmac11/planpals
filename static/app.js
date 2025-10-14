// Particle header (no external libs)
(function(){
  const canvas = document.getElementById('particles');
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, particles=[], mouse={x:0,y:0};

  function resize(){
    W = canvas.width = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  const N = 80;
  for(let i=0;i<N;i++){
    particles.push({
      x: Math.random()*W,
      y: Math.random()*H,
      vx: (Math.random()-0.5)*0.6,
      vy: (Math.random()-0.5)*0.6,
      r: 1.2+Math.random()*2.2
    });
  }

  canvas.addEventListener('mousemove', (e)=>{
    const rect = canvas.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
  });

  function step(){
    ctx.clearRect(0,0,W,H);
    const g = ctx.createRadialGradient(mouse.x, mouse.y, 20, mouse.x, mouse.y, 240);
    g.addColorStop(0, 'rgba(124,58,237,0.25)');
    g.addColorStop(1, 'rgba(16,185,129,0.05)');
    ctx.fillStyle = g;
    ctx.fillRect(0,0,W,H);

    for(const p of particles){
      p.x += p.vx; p.y += p.vy;
      if(p.x<0||p.x>W) p.vx*=-1;
      if(p.y<0||p.y>H) p.vy*=-1;

      const dx = mouse.x - p.x, dy = mouse.y - p.y;
      const d2 = dx*dx + dy*dy;
      if(d2 < 160*160){
        p.vx += dx*0.00002;
        p.vy += dy*0.00002;
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx.fillStyle = 'rgba(255,255,255,0.8)';
      ctx.fill();
    }

    ctx.lineWidth = 0.6;
    for(let i=0;i<N;i++){
      for(let j=i+1;j<N;j++){
        const a=particles[i], b=particles[j];
        const dx=a.x-b.x, dy=a.y-b.y;
        const d = Math.hypot(dx,dy);
        if(d<110){
          const alpha = 1 - d/110;
          ctx.strokeStyle = 'rgba(124,58,237,'+ (0.15*alpha) +')';
          ctx.beginPath();
          ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
        }
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
})();

// Potential attendees on create page
(function(){
  const dateInput = document.getElementById('event-date');
  const potAvail = document.getElementById('pot-available');
  const potBusy = document.getElementById('pot-busy');
  if(!dateInput || !potAvail || !potBusy) return;

  async function refresh(){
    const v = dateInput.value;
    if(!v){ potAvail.textContent = '—'; potBusy.textContent = '—'; return; }
    try{
      const r = await fetch('/who_can_attend?date=' + encodeURIComponent(v));
      const j = await r.json();
      potAvail.textContent = j.available && j.available.length ? j.available.join(', ') : '—';
      potBusy.textContent = j.busy && j.busy.length ? j.busy.join(', ') : '—';
    }catch(e){
      potAvail.textContent = '—';
      potBusy.textContent = '—';
    }
  }
  dateInput.addEventListener('change', refresh);
  if(dateInput.value) refresh();
})();
