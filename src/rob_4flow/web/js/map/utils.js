// utils.js

export function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function deepMerge(target, source) {
  if (!source || typeof source !== "object") return target;

  Object.entries(source).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      target[key] = value;
    } else if (value && typeof value === "object") {
      const current =
        target[key] &&
        typeof target[key] === "object" &&
        !Array.isArray(target[key])
          ? target[key]
          : {};

      target[key] = deepMerge(current, value);
    } else {
      target[key] = value;
    }
  });

  return target;
}

export function setsIntersect(a, b) {
  for (const value of a) {
    if (b.has(value)) return true;
  }

  return false;
}