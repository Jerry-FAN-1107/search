// axios 实例：自动注入 JWT，401 时用 Refresh Token 自动换新并重试一次
import axios from "axios";

export const API_BASE = "/api";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 刷新令牌：单例 Promise，并发 401 只刷新一次
let refreshing: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  const rt = localStorage.getItem("refresh_token");
  if (!rt) return null;
  try {
    // 用裸 axios，避免走本实例的拦截器造成递归
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: rt });
    localStorage.setItem("token", data.access_token);
    if (data.refresh_token) localStorage.setItem("refresh_token", data.refresh_token);
    return data.access_token as string;
  } catch {
    return null;
  }
}

function clearAuthAndRedirect() {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  window.location.href = "/login";
}

client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err?.config;
    const url: string = original?.url ?? "";
    // 认证接口自身的 401（登录失败/刷新失败）不做刷新重试
    if (err?.response?.status === 401 && original && !original._retried && !url.includes("/auth/")) {
      original._retried = true;
      refreshing = refreshing ?? doRefresh();
      const token = await refreshing;
      refreshing = null;
      if (token) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${token}`;
        return client(original);
      }
      clearAuthAndRedirect();
    }
    return Promise.reject(err);
  }
);

export default client;
