const API_BASE = "http://localhost:8000";

export type EpicSummary = {
  connected: boolean;
  message?: string;
  source?: string;
  patient?: {
    id?: string;
    name?: string;
    birthDate?: string;
    gender?: string;
  };
  labs?: ClinicalRow[];
  vitals?: ClinicalRow[];
  conditions?: Record<string, unknown>[];
  medications?: Record<string, unknown>[];
  allergies?: Record<string, unknown>[];
  encounters?: Record<string, unknown>[];
  diagnosticReports?: Record<string, unknown>[];
  documents?: Record<string, unknown>[];
  metadata?: {
    retrievedAt?: string;
    scopes?: string;
    note?: string;
  };
};

export type ClinicalRow = {
  id?: string;
  name?: string;
  value?: string | number | null;
  unit?: string | null;
  date?: string | null;
  status?: string | null;
  code?: string | null;
  codeSystem?: string | null;
  flag?: string | null;
};

export async function getEpicSummary(): Promise<EpicSummary> {
  const res = await fetch(`${API_BASE}/api/epic/summary`);
  if (!res.ok) throw new Error("Failed to fetch Epic summary");
  return res.json();
}

export async function getEpicRaw(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/epic/raw`);
  if (res.status === 404) {
    return {
      connected: false,
      message: "No Epic/MyChart sandbox data connected yet.",
    };
  }
  if (!res.ok) throw new Error("Failed to fetch raw Epic data");
  return res.json();
}

export async function logoutEpic(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/epic/logout`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear Epic session");
}
