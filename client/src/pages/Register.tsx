// 注册页
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../api/auth";
import { useAuth } from "../store/auth";

export function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const setAuth = useAuth((s) => s.setAuth);
  const nav = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const tokens = await register(email, password);
      setAuth(tokens.access_token, tokens.refresh_token, email);
      nav("/chat");
    } catch {
      setErr("注册失败，邮箱可能已存在，或密码需包含字母与数字");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-xl font-semibold">注册账号</h1>
        <p className="mb-5 text-sm text-gray-500">创建你的企业信息咨询空间</p>
        <label className="mb-1 block text-sm text-gray-600">邮箱</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required
          className="mb-3 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
        <label className="mb-1 block text-sm text-gray-600">密码（≥8位，含字母与数字）</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required minLength={8}
          className="mb-4 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
        {err && <p className="mb-2 text-xs text-red-600">{err}</p>}
        <button className="w-full rounded-md bg-brand-700 py-2 text-sm text-white hover:bg-brand-800">注册</button>
        <p className="mt-4 text-center text-sm text-gray-500">
          已有账号？<Link to="/login" className="text-brand-700 hover:underline">登录</Link>
        </p>
      </form>
    </div>
  );
}