// Configures basic starting window with 2 actions (create / load).

import { loadHtml } from "../utils.js";
import { openCreateModal } from "../ui/create_modal.js"
import { openLoadProjectWindow } from "../app.js"


export async function showStartPage(){
  const html = await loadHtml("/views_html/start.html");
  document.getElementById("content").innerHTML = html;
  document.getElementById("btn-create").addEventListener("click", openCreateModal);
  document.getElementById("btn-load").addEventListener("click", openLoadProjectWindow)
}