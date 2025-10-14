document.addEventListener('mousemove', (e)=>{
  document.body.style.setProperty('--mx', (e.clientX/window.innerWidth*100)+'%')
  document.body.style.setProperty('--my', (e.clientY/window.innerHeight*100)+'%')
});
