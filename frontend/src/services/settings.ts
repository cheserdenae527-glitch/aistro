import api from "./api";

export interface ApiKeyStatus {
 configured: boolean;
 preview?: string | null;
 base_url: string;
 model: string;
}

export interface SettingsResponse {
 storage: { current_dir: string; dirs: string[]; default_dir: string };
 text: ApiKeyStatus;
 image: ApiKeyStatus;
 video: ApiKeyStatus;
}

export interface ApiKeyUpdate {
 api_key?: string;
 base_url?: string;
 model?: string;
}

export interface SettingsUpdate {
 storage_dir?: string;
 text?: ApiKeyUpdate;
 image?: ApiKeyUpdate;
 video?: ApiKeyUpdate;
}

export async function getSettings() {
 const res = await api.get<SettingsResponse>("/settings");
 return res.data;
}

export async function updateSettings(body: SettingsUpdate) {
 const res = await api.put<SettingsResponse>("/settings", body);
 return res.data;
}