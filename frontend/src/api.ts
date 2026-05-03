const API_BASE = "http://localhost:8000";

export type PatientProfile = {
  id?: string | null;
  name?: string | null;
  birthDate?: string | null;
  gender?: string | null;
};

export type ClinicalSummary = {
  connected: boolean;
  message?: string | null;
  patient?: PatientProfile | null;
  conditions: Record<string, unknown>[];
  medications: Record<string, unknown>[];
  labs: Record<string, unknown>[];
  vitals: Record<string, unknown>[];
  encounters: Record<string, unknown>[];
  generatedAt?: string | null;
};

export type ClinicalRow = {
  id?: string | null;
  name?: string | null;
  code?: string | null;
  value?: string | number | null;
  unit?: string | null;
  referenceRange?: string | null;
  interpretation?: string | null;
  effectiveDateTime?: string | null;
  date?: string | null;
  status?: string | null;
  flag?: string | null;
  source?: string | null;
};

export type EpicSummary = ClinicalSummary & {
  metadata?: {
    retrievedAt?: string;
    scopes?: string;
    note?: string;
  };
};

export type WearableProvider = {
  id: string;
  name: string;
  type?: string | null;
  supportsOAuth: boolean;
  supportsImport: boolean;
  requiresMobile: boolean;
  logoUrl?: string | null;
  enabled: boolean;
};

export type WearableConnection = {
  provider: string;
  status?: string | null;
  providerUserId?: string | null;
  scopes: string[];
  connectedAt?: string | null;
  lastSyncedAt?: string | null;
  source: string;
};

export type WearableSource = {
  provider?: string | null;
  device?: string | null;
  deviceType?: string | null;
};

export type WearableTimeseriesPoint = {
  timestamp?: string | null;
  type?: string | null;
  value?: string | number | null;
  unit?: string | null;
  zoneOffset?: string | null;
  source: WearableSource;
};

export type WearableWorkout = {
  id?: string | null;
  type?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  durationMinutes?: number | null;
  calories?: number | null;
  distance?: number | null;
  averageHeartRate?: number | null;
  source: WearableSource;
};

export type WearableSleepEvent = {
  id?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  durationMinutes?: number | null;
  efficiencyPercent?: number | null;
  stages: Record<string, unknown>[];
  interruptions?: number | null;
  source: WearableSource;
};

export type HealthScoreComponent = {
  value?: string | number | null;
  qualifier?: string | null;
};

export type HealthScore = {
  id?: string | null;
  dataSourceId?: string | null;
  provider?: string | null;
  category: string;
  value?: string | number | null;
  qualifier?: string | null;
  recordedAt?: string | null;
  zoneOffset?: string | null;
  components: Record<string, HealthScoreComponent>;
};

export type WearablesPageData = {
  providers: WearableProvider[];
  connections: WearableConnection[];
  activitySummary: Record<string, unknown>;
  sleepSummary: Record<string, unknown>;
  bodySummary: Record<string, unknown>;
  dataSummary: Record<string, unknown>;
  dataSources: Record<string, unknown>;
  heartRate: WearableTimeseriesPoint[];
  steps: WearableTimeseriesPoint[];
  workouts: WearableWorkout[];
  sleepEvents: WearableSleepEvent[];
  healthScores: HealthScore[];
};

export type WearableDataMode = "synthetic" | "real";

export type LocalAiContextCategory = {
  id: string;
  source: "epic" | "openWearables" | string;
  key: string;
  label: string;
  available: boolean;
  recordCount?: number | null;
};

export type LocalAiContextSource = {
  id: "epic" | "openWearables" | string;
  label: string;
  connected: boolean;
  categories: LocalAiContextCategory[];
};

export type LocalAiContextAvailability = {
  sources: LocalAiContextSource[];
};

export type LocalAiSelectedRawContext = {
  selectedRawContext: {
    epic?: unknown;
    openWearables?: unknown;
  };
  generatedAt: string;
};

export type LocalAiDocument = {
  id: string;
  categoryId: string;
  documentType?: string | null;
  details?: string | null;
  date?: string | null;
  contentType?: string | null;
};

export type LocalAiDocumentsResponse = {
  documents: LocalAiDocument[];
};

export type AiChatDocumentSelection = {
  categoryId: string;
  documentId: string;
};

export type AiChatRequest = {
  prompt: string;
  selectedCategoryIds?: string[];
  selectedDocuments?: AiChatDocumentSelection[];
  selectedSkillIds?: string[];
  translationLanguage?: string | null;
  imageDataUrl?: string | null;
};

export type AiChatResponse = {
  answer: string;
  model: string;
  generatedAt: string;
  reasoningDetails?: unknown;
};

export type AiChatProgressStage =
  | "thinking"
  | "using_tool"
  | "waiting_for_tool"
  | "waiting_for_model"
  | "complete"
  | "error";

export type AiChatProgressEvent = {
  stage: AiChatProgressStage;
  message?: string;
  toolName?: string;
  statusCode?: number;
};

export type SendAiChatStreamOptions = {
  onProgress?: (event: AiChatProgressEvent) => void;
};

export type AuditDataAccess = {
  source?: string | null;
  categoryId?: string | null;
  categoryLabel?: string | null;
  documentId?: string | null;
  contentType?: string | null;
  recordCount?: number | null;
  accessType?: string | null;
};

export type AuditLogEntry = {
  id: string;
  timestamp: string;
  system: string;
  action: string;
  status: string;
  summary: string;
  dataAccessed: AuditDataAccess[];
  details: Record<string, unknown>;
};

export type AuditLogsResponse = {
  logs: AuditLogEntry[];
};

export type ClearAuditLogsResponse = {
  cleared: number;
};

export async function getClinicalSummary(): Promise<ClinicalSummary> {
  const res = await fetch(`${API_BASE}/api/clinical/summary`);
  if (!res.ok) throw new Error("Failed to fetch clinical summary");
  return res.json();
}

export async function logoutEpic(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/epic/logout`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear Epic session");
}

export async function clearEpicData(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/epic/data`, { method: "DELETE" });
  if (!res.ok) throw new Error(await responseErrorMessage(res, "Failed to clear MyChart data"));
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await responseErrorMessage(res, `Failed to fetch ${path}`));
  return res.json();
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await responseErrorMessage(res, `Failed to post ${path}`));
  return res.json();
}

async function responseErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const payload = await res.json();
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload && payload.detail && typeof payload.detail.message === "string") {
      return payload.detail.message;
    }
    if (payload && typeof payload.error === "string") {
      return payload.error;
    }
    if (payload && payload.error && typeof payload.error.message === "string") {
      return payload.error.message;
    }
  } catch {
    // Keep the original fallback when the backend returned non-JSON content.
  }
  return fallback;
}

export async function getWearableProviders(): Promise<WearableProvider[]> {
  return getJson<WearableProvider[]>("/api/wearables/providers");
}

export async function getWearableConnections(): Promise<WearableConnection[]> {
  return getJson<WearableConnection[]>("/api/wearables/connections");
}

export async function getAuditLogs(): Promise<AuditLogsResponse> {
  return getJson<AuditLogsResponse>("/api/logs");
}

export async function clearAuditLogs(): Promise<ClearAuditLogsResponse> {
  const res = await fetch(`${API_BASE}/api/logs`, { method: "DELETE" });
  if (!res.ok) throw new Error(await responseErrorMessage(res, "Failed to clear audit logs"));
  return res.json();
}

export async function getLocalAiContextAvailability(): Promise<LocalAiContextAvailability> {
  return getJson<LocalAiContextAvailability>("/api/local-ai/context/available");
}

export async function getLocalAiSelectedRawContext(
  categoryIds: string[]
): Promise<LocalAiSelectedRawContext> {
  return postJson<LocalAiSelectedRawContext>("/api/local-ai/context/raw", { categoryIds });
}

export async function getLocalAiDocuments(): Promise<LocalAiDocumentsResponse> {
  return getJson<LocalAiDocumentsResponse>("/api/local-ai/context/documents");
}

export async function getLocalAiSelectedRawDocument(
  categoryId: string,
  documentId: string
): Promise<LocalAiSelectedRawContext> {
  return postJson<LocalAiSelectedRawContext>("/api/local-ai/context/document/raw", {
    categoryId,
    documentId,
  });
}

export async function sendAiChat(request: AiChatRequest): Promise<AiChatResponse> {
  return postJson<AiChatResponse>("/api/ai/chat", {
    prompt: request.prompt,
    selectedCategoryIds: request.selectedCategoryIds ?? [],
    selectedDocuments: request.selectedDocuments ?? [],
    selectedSkillIds: request.selectedSkillIds ?? [],
    translationLanguage: request.translationLanguage || undefined,
    imageDataUrl: request.imageDataUrl || undefined,
  });
}

export async function sendAiChatStream(
  request: AiChatRequest,
  options: SendAiChatStreamOptions = {}
): Promise<AiChatResponse> {
  const res = await fetch(`${API_BASE}/api/ai/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: request.prompt,
      selectedCategoryIds: request.selectedCategoryIds ?? [],
      selectedDocuments: request.selectedDocuments ?? [],
      selectedSkillIds: request.selectedSkillIds ?? [],
      translationLanguage: request.translationLanguage || undefined,
      imageDataUrl: request.imageDataUrl || undefined,
    }),
  });
  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "Failed to start AI chat stream"));
  }
  if (!res.body) {
    throw new Error("AI chat stream did not return a response body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: AiChatResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) continue;
      if (event.event === "progress") {
        options.onProgress?.(event.data as AiChatProgressEvent);
      }
      if (event.event === "error") {
        const payload = event.data as AiChatProgressEvent;
        options.onProgress?.(payload);
        throw new Error(payload.message || "AI generation failed");
      }
      if (event.event === "complete") {
        const payload = event.data as { response?: AiChatResponse };
        if (!payload.response) {
          throw new Error("AI chat stream completed without a response");
        }
        finalResponse = payload.response;
      }
    }
    if (done) break;
  }

  if (!finalResponse) {
    throw new Error("AI chat stream ended before completion");
  }
  return finalResponse;
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const lines = block.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLines = lines.filter((line) => line.startsWith("data:"));
  if (!eventLine || dataLines.length === 0) return null;
  const event = eventLine.slice("event:".length).trim();
  const dataText = dataLines.map((line) => line.slice("data:".length).trimStart()).join("\n");
  try {
    return { event, data: JSON.parse(dataText) };
  } catch {
    return null;
  }
}

export async function connectWearableProvider(
  provider: string,
  mode: WearableDataMode
): Promise<{ authorizationUrl?: string | null; mode?: string | null }> {
  return postJson(`/api/wearables/connect/${encodeURIComponent(provider)}`, { mode });
}

export async function clearWearableConnections(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/wearables/connections`, { method: "DELETE" });
  if (!res.ok) throw new Error(await responseErrorMessage(res, "Failed to clear wearable connections"));
  return res.json();
}

export async function disconnectWearableProvider(provider: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/wearables/connections/${encodeURIComponent(provider)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await responseErrorMessage(res, `Failed to disconnect ${provider}`));
  return res.json();
}

export async function computeWearableHealthScores(): Promise<Record<string, unknown>> {
  return postJson("/api/wearables/health-scores/compute");
}

export async function uploadAppleHealthXml(file: File): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/wearables/import/apple-health/xml/direct`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await responseErrorMessage(res, "Failed to import Apple Health XML"));
  return res.json();
}
