import axios from "axios";

const api = axios.create({
 baseURL: "/api/v1",
 timeout: 30000,
});

// 自动附带 JWT token
api.interceptors.request.use((config) => {
 const token = localStorage.getItem("token");
 if (token) {
   config.headers.Authorization = `Bearer ${token}`;
 }
 return config;
});

// 401 时自动跳转登录
api.interceptors.response.use(
 (res) => res,
 (err) => {
   if (err.response?.status === 401) {
     localStorage.removeItem("token");
     localStorage.removeItem("user");
     window.location.href = "/login";
   }
   return Promise.reject(err);
 }
);

export default api;
export * from "./auth";
