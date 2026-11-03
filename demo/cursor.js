
(() => { const c = document.createElement('div'); c.id='__cur';
c.style.cssText='position:fixed;left:-50px;top:-50px;width:22px;height:30px;z-index:2147483647;pointer-events:none;transition:none';
c.innerHTML='<svg width="22" height="30" viewBox="0 0 22 30"><path d="M2 2 L2 24 L8 18 L12 28 L16 26 L12 17 L20 17 Z" fill="#fff" stroke="#000" stroke-width="1.5"/></svg>';
const add=()=>document.body&&document.body.appendChild(c); if(document.body) add(); else document.addEventListener('DOMContentLoaded',add);
window.addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px'},true); })();
