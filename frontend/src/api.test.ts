import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearAuditLogs,
  clearEpicData,
  disconnectWearableProvider,
  getAuditLogs,
  sendAiChat,
  sendAiChatStream,
} from "./api";

describe("sendAiChat", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts prompt, selected data, documents, and image data to backend AI chat", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "Backend answer",
        model: "nvidia/nemotron-3-super-120b-a12b:free",
        generatedAt: "2026-05-03T12:00:00Z",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await sendAiChat({
      prompt: "What matters?",
      selectedCategoryIds: ["epic.patient"],
      selectedDocuments: [{ categoryId: "epic.documents_labs", documentId: "doc-1" }],
      imageDataUrl: "data:image/png;base64,abc",
      selectedSkillIds: ["data_with_rerank", "open_wearables_health_ai", "translation"],
      translationLanguage: "es-US",
    });

    expect(response.answer).toBe("Backend answer");
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: expect.any(String),
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      prompt: "What matters?",
      selectedCategoryIds: ["epic.patient"],
      selectedDocuments: [{ categoryId: "epic.documents_labs", documentId: "doc-1" }],
      imageDataUrl: "data:image/png;base64,abc",
      selectedSkillIds: ["data_with_rerank", "open_wearables_health_ai", "translation"],
      translationLanguage: "es-US",
    });
  });

  it("surfaces backend AI errors from string or object detail payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ detail: { message: "OpenRouter rejected the request" } }),
      })
    );

    await expect(sendAiChat({ prompt: "hello" })).rejects.toThrow(
      "OpenRouter rejected the request"
    );
  });

  it("parses streaming progress and complete events", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: streamFromText(
        [
          'event: progress\ndata: {"stage":"waiting_for_model","message":"Waiting for model"}\n\n',
          'event: progress\ndata: {"stage":"using_tool","message":"Using mychart_data","toolName":"mychart_data"}\n\n',
          'event: complete\ndata: {"stage":"complete","response":{"answer":"Streamed answer","model":"model-1","generatedAt":"2026-05-03T12:00:00Z"}}\n\n',
        ].join("")
      ),
    });
    vi.stubGlobal("fetch", fetchMock);
    const progress: string[] = [];

    const response = await sendAiChatStream(
      { prompt: "What matters?", selectedCategoryIds: ["epic.patient"] },
      {
        onProgress: (event) => {
          progress.push(event.message || event.stage);
        },
      }
    );

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/ai/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: expect.any(String),
    });
    expect(progress).toEqual(["Waiting for model", "Using mychart_data"]);
    expect(response.answer).toBe("Streamed answer");
  });

  it("throws streaming backend error events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: streamFromText(
          'event: error\ndata: {"stage":"error","message":"OpenRouter failed"}\n\n'
        ),
      })
    );

    await expect(sendAiChatStream({ prompt: "hello" })).rejects.toThrow("OpenRouter failed");
  });
});

function streamFromText(value: string) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(value));
      controller.close();
    },
  });
}

describe("connection management API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clears MyChart data without disconnecting other services", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await clearEpicData();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/epic/data", {
      method: "DELETE",
    });
  });

  it("disconnects a single wearable provider", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "disconnected", provider: "oura" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await disconnectWearableProvider("oura");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/wearables/connections/oura",
      { method: "DELETE" }
    );
  });
});

describe("audit logs API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads backend audit logs", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        logs: [
          {
            id: "log_1",
            timestamp: "2026-05-03T12:00:00Z",
            system: "ai",
            action: "llm_tool_call",
            status: "succeeded",
            summary: "Nemotron called mychart_data.",
            dataAccessed: [{ source: "epic", categoryId: "epic.patient" }],
            details: { toolName: "mychart_data" },
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await getAuditLogs();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/logs");
    expect(response.logs[0].details.toolName).toBe("mychart_data");
  });

  it("clears backend audit logs", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cleared: 2 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await clearAuditLogs();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/logs", {
      method: "DELETE",
    });
    expect(response.cleared).toBe(2);
  });
});
