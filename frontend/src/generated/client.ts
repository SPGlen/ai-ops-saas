import createClient from "openapi-fetch";
import type { paths } from "./api";
/** Generated-contract client for integrations; same-origin cookies and CSRF mirror the UI client. */
export const client = createClient<paths>();
client.use({
  onRequest({ request }) {
    const token = document.cookie
      .split("; ")
      .find((v) => v.startsWith("ops_csrf="))
      ?.split("=")
      .slice(1)
      .join("=");
    if (token && !["GET", "HEAD", "OPTIONS"].includes(request.method))
      request.headers.set("X-CSRF-Token", decodeURIComponent(token));
    return request;
  },
});
