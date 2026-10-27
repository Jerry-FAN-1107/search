// 认证 API：登录/注册返回 Access + Refresh Token；刷新与注销
import client from "./client";

export interface TokenPair {
  access_token: string;
  refresh_token?: string | null;
}

export async function register(email: string, password: string): Promise<TokenPair> {
  const { data } = await client.post<TokenPair>("/auth/register", { email, password });
  return data;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const { data } = await client.post<TokenPair>("/auth/login", { email, password });
  return data;
}

export async function logoutRemote(refreshToken: string): Promise<void> {
  await client.post("/auth/logout", { refresh_token: refreshToken });
}
