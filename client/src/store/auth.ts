// 登录态管理（zustand）：Access Token + Refresh Token
import { create } from "zustand";
import { logoutRemote } from "../api/auth";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  email: string | null;
  setAuth: (accessToken: string, refreshToken: string | null | undefined, email?: string) => void;
  logout: () => void;
}

function readEmail(): string | null {
  try {
    return localStorage.getItem("email");
  } catch {
    return null;
  }
}

export const useAuth = create<AuthState>((set, get) => ({
  token: localStorage.getItem("token"),
  refreshToken: localStorage.getItem("refresh_token"),
  email: readEmail(),
  setAuth: (accessToken, refreshToken, email) => {
    localStorage.setItem("token", accessToken);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
    if (email) localStorage.setItem("email", email);
    set({ token: accessToken, refreshToken: refreshToken ?? get().refreshToken, email: email ?? readEmail() });
  },
  logout: () => {
    // 通知后端吊销 Refresh Token（失败也继续本地登出）
    const rt = get().refreshToken;
    if (rt) logoutRemote(rt).catch(() => {});
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("email");
    set({ token: null, refreshToken: null, email: null });
  },
}));
