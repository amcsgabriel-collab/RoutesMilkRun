export function escapeHtml(s = "") {
  return (s+"").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

export function delay(ms){
    return new Promise(r=>setTimeout(r, ms));
}

export async function loadHtml(url){
    const r = await fetch(url); 
    if(!r.ok) throw new Error(url+" load failed"); 
    return r.text();
}