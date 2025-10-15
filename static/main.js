
(function(){
  const canvas = document.getElementById('hero-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w, h, particles=[], mouse={x:0,y:0};

  function resize(){
    w = canvas.width = canvas.parentElement.clientWidth;
    h = canvas.height = 260; // match hero height-ish
  }
  window.addEventListener('resize', resize);
  resize();

  const COUNT = 60;
  function rand(min,max){ return Math.random()*(max-min)+min; }
  function spawn(){
    particles = [];
    for(let i=0;i<COUNT;i++){
      particles.push({
        x: rand(0,w),
        y: rand(0,h),
        vx: rand(-0.3,0.3),
        vy: rand(-0.3,0.3),
        r: rand(1.2,3.2),
      });
    }
  }
  spawn();

  canvas.addEventListener('mousemove', e=>{
    const rect = canvas.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
  });
  canvas.addEventListener('mouseleave', ()=>{ mouse.x = -9999; mouse.y = -9999; });

  function step(){
    ctx.clearRect(0,0,w,h);
    for (const p of particles){
      // gentle attraction to mouse
      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const d2 = dx*dx + dy*dy;
      const force = Math.min(0.002, 60/(d2+10000));
      p.vx += dx*force;
      p.vy += dy*force;

      // motion + boundary
      p.x += p.vx;
      p.y += p.vy;
      if (p.x<0||p.x>w) p.vx*=-1;
      if (p.y<0||p.y>h) p.vy*=-1;

      // draw
      ctx.beginPath();
      ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle = 'rgba(80,180,200,0.7)';
      ctx.fill();
    }
    // draw connecting lines
    for (let i=0;i<particles.length;i++){
      for (let j=i+1;j<particles.length;j++){
        const a = particles[i], b = particles[j];
        const dx = a.x-b.x, dy=a.y-b.y;
        const d = Math.hypot(dx,dy);
        if (d<90){
          ctx.globalAlpha = 1 - (d/90);
          ctx.beginPath();
          ctx.moveTo(a.x,a.y);
          ctx.lineTo(b.x,b.y);
          ctx.strokeStyle = 'rgba(140, 100, 220, 0.8)';
          ctx.lineWidth = 0.6;
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }
    }
    requestAnimationFrame(step);
  }
  step();
})();
