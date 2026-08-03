import { message } from "antd";

export function getApiError(e: unknown): string {
  if (e && typeof e === "object" && "response" in e) {
    const response = (e as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) return response.data.detail;
  }
  if (e instanceof Error) return e.message;
  return "操作失败，请稍后重试";
}

export function showApiError(e: unknown): void {
  message.error(getApiError(e));
}
