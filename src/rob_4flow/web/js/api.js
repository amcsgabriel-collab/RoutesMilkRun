// Configures how each type of request is handled.
// Requests are sent to the python backend via Flask

async function apiRequest(path, { method, body, headers = {} } = {}) {
    const opts = {
        method,
        credentials: "same-origin",
        headers: { ...headers }
    };

    if (body !== undefined) {
        if (body instanceof FormData) {
          opts.body = body;
        } else {
          opts.headers["Content-Type"] = "application/json";
          opts.body = JSON.stringify(body);
        }
    }

    const res = await fetch(path, opts);

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    let data = null;

    if (isJson) {
        data = await res.json().catch(() => null);
    } else {
        const text = await res.text().catch(() => "");
        data = text ? { text } : null;
    }

    if (!res.ok) {
        const message =
            data?.error ||
            data?.message ||
            data?.text ||
            `HTTP ${res.status} ${res.statusText}`;

        const err = new Error(message);
        err.status = res.status;
        err.data = data;
        err.type = data?.type;
        err.code = data?.code;
        throw err;
  }

  return data?.data;
}

export function apiGet(path) {
  return apiRequest(path, { method: "GET" });
}

export function apiPost(path, body) {
  return apiRequest(path, { method: "POST", body });
}

export function apiPut(path, body) {
  return apiRequest(path, { method: "PUT", body });
}

export function apiPatch(path, body) {
  return apiRequest(path, { method: "PATCH", body });
}

export function apiDelete(path, body) {
  return apiRequest(path, { method: "DELETE", body });
}
