(function(){
  const c = document.getElementById('mousefx');
  if(!c) return;
  const ctx = c.getContext('2d');
  const DPR = window.devicePixelRatio || 1;
  let w, h, t=0;
  function resize(){
    w = c.clientWidth = c.parentElement.clientWidth;
    h = c.clientHeight = 260;
    c.width = w*DPR; c.height = h*DPR;
    ctx.setTransform(DPR,0,0,DPR,0,0);
  }
  window.addEventListener('resize', resize); resize();

  const mouse = {x: w/2, y: h/2, vx:0, vy:0};
  c.addEventListener('mousemove', e=>{
    const r = c.getBoundingClientRect();
    const nx = e.clientX - r.left, ny = e.clientY - r.top;
    mouse.vx += (nx - mouse.x)*0.15;
    mouse.vy += (ny - mouse.y)*0.15;
  });

  function step(){
    t += 1/60;
    mouse.x += mouse.vx*0.08; mouse.vx *= 0.85;
    mouse.y += mouse.vy*0.08; mouse.vy *= 0.85;

    ctx.clearRect(0,0,w,h);

    // Parallax glow grid
    ctx.save();
    ctx.globalAlpha = 0.12;
    ctx.strokeStyle = '#7c3aed';
    const gap = 36;
    const ox = -((mouse.x/w)-0.5)*20;
    const oy = -((mouse.y/h)-0.5)*14;
    for(let x=ox; x<w; x+=gap){
      ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,h); ctx.stroke();
    }
    ctx.strokeStyle = '#14b8a6';
    for(let y=oy; y<h; y+=gap){
      ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();
    }
    ctx.restore();

    // Soft blob following cursor
    const r = 48 + Math.sin(t*1.5)*6;
    const grad = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, r*2.2);
    grad.addColorStop(0, 'rgba(20,184,166,0.50)');
    grad.addColorStop(1, 'rgba(20,184,166,0)');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(mouse.x, mouse.y, r*2.2, 0, Math.PI*2); ctx.fill();

    const grad2 = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, r);
    grad2.addColorStop(0, 'rgba(124,58,237,0.55)');
    grad2.addColorStop(1, 'rgba(124,58,237,0)');
    ctx.fillStyle = grad2;
    ctx.beginPath(); ctx.arc(mouse.x, mouse.y, r, 0, Math.PI*2); ctx.fill();

    requestAnimationFrame(step);
  }
  step();
})();
