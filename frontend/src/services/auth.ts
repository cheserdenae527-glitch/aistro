import api from "./api";

export interface User {
 id: string;
 email: string;
 name: string;
 role: string;
 created_at: string;
}

export interface LoginResponse {
 access_token: string;
 token_type: string;
 user: User;
}

export async function login(email: string, password: string) {
 const res = await api.post<LoginResponse>("/auth/login", { email, password });
 return res.data;
}

export async function register(email: string, password: string, name: string) {
 const res = await api.post<LoginResponse>("/auth/register", {
   email,
   password,
   name,
 });
 return res.data;
}

export async function getMe() {
 const res = await api.get<User>("/auth/me");
 return res.data;
}

export async function localLogin() {
  const res = await api.post<LoginResponse>("/auth/local-login");
  return res.data;
}

export async function updateUser(name: string, newPassword?: string) {
  const res = await api.put<User>("/auth/me", { name, new_password: newPassword || undefined });
  return res.data;
}
