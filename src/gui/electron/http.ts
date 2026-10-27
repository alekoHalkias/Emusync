// Tiny GET-JSON helper over Node's http.request.
//
// The browser `fetch()` API does not work reliably in Electron's main process
// (it is Node, not a browser), so main-process HTTP that needs to be robust
// uses this wrapper instead.
import { request as httpRequest } from "http";
import { URL } from "url";

export function httpGetJSON(urlStr: string, headers: Record<string, string>): Promise<{ status: number; body?: any; error?: string }> {
  return new Promise((resolve) => {
    try {
      const urlObj = new URL(urlStr);

      const req = httpRequest({
        hostname: urlObj.hostname,
        port: urlObj.port || 80,
        path: urlObj.pathname + urlObj.search,
        method: "GET",
        headers,
      }, (res) => {
        let data = "";
        res.on("data", (chunk) => { data += chunk; });
        res.on("end", () => {
          try {
            const body = data ? JSON.parse(data) : undefined;
            resolve({ status: res.statusCode || 500, body });
          } catch (e) {
            resolve({ status: res.statusCode || 500, error: data });
          }
        });
      });

      req.on("error", (e) => {
        resolve({ status: 0, error: (e as Error).message });
      });

      req.setTimeout(5000, () => {
        req.destroy();
        resolve({ status: 0, error: "Timeout" });
      });

      req.end();
    } catch (e) {
      resolve({ status: 0, error: (e as Error).message });
    }
  });
}
