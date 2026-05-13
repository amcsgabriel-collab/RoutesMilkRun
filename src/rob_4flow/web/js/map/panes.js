export function ensurePanes(map) {
  const panes = [
    ["routePane", 410],
    ["markerPane", 610],
    ["iconPane", 650],
  ];

  panes.forEach(([name, zIndex]) => {
    if (!map.getPane(name)) {
      map.createPane(name);
    }

    map.getPane(name).style.zIndex = String(zIndex);
  });
}