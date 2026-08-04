import { notification } from "antd";
import { create } from "zustand";
import { designService } from "../services/designs";
import { getApiError } from "../utils/errors";

export type BackgroundJobStatus = "running" | "success" | "error";

export interface BackgroundJob {
  key: string;
  label: string;
  status: BackgroundJobStatus;
  result?: unknown;
  error?: string;
  finishedAt?: string;
}

export interface TrackResult {
  ok: boolean;
  result?: unknown;
  error?: string;
}

interface DesignJobState {
  jobs: Record<string, BackgroundJob>;
  track: (key: string, label: string, promise: Promise<unknown>) => Promise<TrackResult>;
  trackJob: (projectId: string, jobId: string, label: string) => Promise<TrackResult>;
  clear: (key: string) => void;
}

export const useDesignJobs = create<DesignJobState>((set) => ({
  jobs: {},

  track: (key, label, promise) => {
    set((state) => ({
      jobs: { ...state.jobs, [key]: { key, label, status: "running" } },
    }));

    return promise
      .then((result) => {
        set((state) => ({
          jobs: {
            ...state.jobs,
            [key]: {
              key,
              label,
              status: "success",
              result,
              finishedAt: new Date().toISOString(),
            },
          },
        }));
        notification.success({
          key: `design-job-${key}`,
          message: `${label} 完成`,
          description: "4 张候选已生成，返回编辑器即可查看",
        });
        return { ok: true, result };
      })
      .catch((error) => {
        const message = getApiError(error);
        set((state) => ({
          jobs: {
            ...state.jobs,
            [key]: {
              key,
              label,
              status: "error",
              error: message,
              finishedAt: new Date().toISOString(),
            },
          },
        }));
        notification.error({
          key: `design-job-${key}`,
          message: `${label} 失败`,
          description: message,
        });
        return { ok: false, error: message };
      });
  },

  trackJob: (projectId, jobId, label) => {
    const key = `job:${jobId}`;
    set((state) => ({
      jobs: { ...state.jobs, [key]: { key, label, status: "running" } },
    }));

    return new Promise<TrackResult>((resolve) => {
      const startedAt = Date.now();
      const timer = setInterval(async () => {
        if (Date.now() - startedAt > 10 * 60 * 1000) {
          clearInterval(timer);
          const message = "生成超时，请稍后重试";
          set((state) => ({
            jobs: {
              ...state.jobs,
              [key]: { key, label, status: "error", error: message, finishedAt: new Date().toISOString() },
            },
          }));
          notification.error({ key: `design-job-${key}`, message: `${label} 失败`, description: message });
          resolve({ ok: false, error: message });
          return;
        }
        try {
          const res = await designService.getDesignJob(projectId, jobId);
          const data = res.data;
          if (data.status === "success") {
            clearInterval(timer);
            const result = data.result;
            set((state) => ({
              jobs: {
                ...state.jobs,
                [key]: {
                  key,
                  label,
                  status: "success",
                  result,
                  finishedAt: new Date().toISOString(),
                },
                [`project:${projectId}`]: {
                  key: `project:${projectId}`,
                  label,
                  status: "success",
                  result,
                  finishedAt: new Date().toISOString(),
                },
              },
            }));
            notification.success({
              key: `design-job-${key}`,
              message: `${label} 完成`,
              description: "4 张候选已生成，返回编辑器即可查看",
            });
            resolve({ ok: true, result });
          } else if (data.status === "failed") {
            clearInterval(timer);
            const message = data.error || "生成失败";
            set((state) => ({
              jobs: {
                ...state.jobs,
                [key]: { key, label, status: "error", error: message, finishedAt: new Date().toISOString() },
              },
            }));
            notification.error({ key: `design-job-${key}`, message: `${label} 失败`, description: message });
            resolve({ ok: false, error: message });
          }
        } catch {
          // 轮询瞬时错误继续等待
        }
      }, 2000);
    });
  },

  clear: (key) =>
    set((state) => {
      const jobs = { ...state.jobs };
      delete jobs[key];
      return { jobs };
    }),
}));