export function setAppBusy(isBusy){
  const overlay = document.getElementById("ui-overlay");
  if (!overlay) return;
  overlay.classList.toggle("hidden", !isBusy);
  const ids = ["menu-new","menu-open","menu-save","menu-saveas"];
  ids.forEach(id => { const el = document.getElementById(id); if(el) el.disabled = !!isBusy; });
}