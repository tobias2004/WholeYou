import { useEffect, useRef, useState } from "react";
import {
  AiChatProgressEvent,
  AuditLogEntry,
  LocalAiDocument,
  LocalAiContextAvailability,
  LocalAiContextSource,
  WearableDataMode,
  WearableConnection,
  WearableProvider,
  clearAuditLogs,
  clearEpicData,
  clearWearableConnections,
  computeWearableHealthScores,
  connectWearableProvider,
  disconnectWearableProvider,
  getLocalAiContextAvailability,
  getLocalAiDocuments,
  getAuditLogs,
  getWearableConnections,
  getWearableProviders,
  logoutEpic,
  sendAiChatStream,
  uploadAppleHealthXml,
} from "./api";
import { ConnectMyChart } from "./components/ConnectMyChart";
import { Header } from "./components/Header";
import { formatResponseBlocks } from "./responseFormatting";

const AI_SKILLS = [
  {
    id: "data_with_rerank",
    label: "Data with rerank",
    description: "Find relevant facts across selected MyChart and wearable data.",
  },
  {
    id: "rag_with_rerank",
    label: "RAG with rerank",
    description: "Use the medical RAG corpus for general medical context.",
  },
  {
    id: "mychart_data",
    label: "MyChart data",
    description: "Fetch specific MyChart categories or list what is available.",
  },
  {
    id: "wearables_data",
    label: "Wearables data",
    description: "Fetch specific device categories or list what is available.",
  },
  {
    id: "open_wearables_health_ai",
    label: "Health AI engine",
    description: "Use Open Wearables-style activity, sleep, workout, trend, and anomaly reasoning.",
  },
  {
    id: "translation",
    label: "Translation",
    description: "Ask in a supported language and receive the final answer in that language.",
  },
] as const;

const TRANSLATION_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "German" },
  { code: "es-ES", label: "European Spanish" },
  { code: "es-US", label: "Latin American Spanish" },
  { code: "fr", label: "French" },
  { code: "pt-BR", label: "Brazilian Portuguese" },
  { code: "ru", label: "Russian" },
  { code: "zh-CN", label: "Simplified Chinese" },
  { code: "zh-TW", label: "Traditional Chinese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "ar", label: "Arabic" },
] as const;

function App() {
  const path = window.location.pathname;

  if (path === "/dashboard") {
    return <DashboardPage />;
  }

  if (path === "/wearables") {
    return <WearablesPage />;
  }

  if (path === "/logs") {
    return <LogsPage />;
  }

  if (path === "/error") {
    const message = new URLSearchParams(window.location.search).get("message");
    return <ErrorPage message={message ?? "epic_connection_failed"} />;
  }

  return <UnifiedHomePage />;
}

function UnifiedHomePage() {
  const [availability, setAvailability] = useState<LocalAiContextAvailability | null>(null);
  const [documents, setDocuments] = useState<LocalAiDocument[]>([]);
  const [providers, setProviders] = useState<WearableProvider[]>([]);
  const [wearableConnections, setWearableConnections] = useState<WearableConnection[]>([]);
  const [dataMode, setDataMode] = useState<WearableDataMode>("synthetic");
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<Set<string>>(new Set());
  const [selectedDocumentKeys, setSelectedDocumentKeys] = useState<Set<string>>(new Set());
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(new Set());
  const [translationLanguage, setTranslationLanguage] = useState("es-US");
  const [prompt, setPrompt] = useState("");
  const [imageName, setImageName] = useState<string | null>(null);
  const [imageDataUrl, setImageDataUrl] = useState<string | null>(null);
  const [attachmentPanel, setAttachmentPanel] = useState<"data" | "document" | "skills" | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [response, setResponse] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [submittedPrompt, setSubmittedPrompt] = useState("");
  const [progressTrail, setProgressTrail] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const aiProgressMessageRef = useRef<string | null>(null);

  useEffect(() => {
    let ignore = false;

    loadUnifiedMetadata()
      .then(({ availability, documents, providers, wearableConnections }) => {
        if (ignore) return;
        setAvailability(availability);
        setDocuments(documents.documents);
        setProviders(providers);
        setWearableConnections(wearableConnections);
        setStatus(null);
      })
      .catch((error: unknown) => {
        if (!ignore) {
          setStatus(error instanceof Error ? error.message : "Unable to load WholeYou data.");
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!generating) return;
    let dotCount = 0;

    function updateStatus() {
      dotCount = (dotCount % 3) + 1;
      const base = aiProgressMessageRef.current ?? "Waiting for model";
      setStatus(`${base}${".".repeat(dotCount)}`);
    }

    updateStatus();
    const interval = window.setInterval(updateStatus, 1000);
    return () => window.clearInterval(interval);
  }, [generating]);

  async function refreshMetadata() {
    const metadata = await loadUnifiedMetadata();
    setAvailability(metadata.availability);
    setDocuments(metadata.documents.documents);
    setProviders(metadata.providers);
    setWearableConnections(metadata.wearableConnections);
  }

  async function handleDisconnectEpic() {
    try {
      setStatus("Disconnecting MyChart.");
      await logoutEpic();
      removeEpicAttachments();
      await refreshMetadata();
      setStatus("MyChart disconnected.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "MyChart disconnect failed.");
    }
  }

  async function handleClearEpicData() {
    try {
      setStatus("Clearing MyChart data.");
      await clearEpicData();
      removeEpicAttachments();
      await refreshMetadata();
      setStatus("MyChart data cleared.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "MyChart data clear failed.");
    }
  }

  function removeEpicAttachments() {
    setSelectedCategoryIds((current) => new Set([...current].filter((id) => !id.startsWith("epic."))));
    setSelectedDocumentKeys(
      (current) => new Set([...current].filter((id) => !id.startsWith("epic.")))
    );
  }

  async function handleConnectProvider(provider: string) {
    try {
      setStatus(
        dataMode === "synthetic"
          ? `Generating synthetic ${provider} data.`
          : `Starting ${provider} OAuth.`
      );
      const result = await connectWearableProvider(provider, dataMode);
      if (result.authorizationUrl) {
        window.location.href = result.authorizationUrl;
        return;
      }
      await refreshMetadata();
      setStatus(`${provider} connected.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Device connection failed.");
    }
  }

  async function handleDisconnectWearables() {
    if (wearableConnections.length === 0) return;
    try {
      setStatus("Disconnecting Open Wearables providers.");
      await Promise.all(
        wearableConnections.map((connection) => disconnectWearableProvider(connection.provider))
      );
      removeWearableAttachments();
      await refreshMetadata();
      setStatus("Open Wearables disconnected.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Open Wearables disconnect failed.");
    }
  }

  async function handleClearWearableData() {
    try {
      setStatus("Clearing Open Wearables data.");
      await clearWearableConnections();
      removeWearableAttachments();
      await refreshMetadata();
      setStatus("Open Wearables data cleared.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Open Wearables data clear failed.");
    }
  }

  function removeWearableAttachments() {
    setSelectedCategoryIds((current) => new Set([...current].filter((id) => !id.startsWith("wearables."))));
  }

  async function handleImageChange(file: File | undefined) {
    if (!file) return;
    setImageName(file.name);
    setImageDataUrl(await fileToDataUrl(file));
    setAttachmentPanel(null);
  }

  async function handleSend() {
    if (!prompt.trim() || generating) return;
    try {
      setGenerating(true);
      setResponse("");
      setSubmittedPrompt(prompt.trim());
      setProgressTrail(["Preparing request"]);
      aiProgressMessageRef.current = "Preparing request";
      setStatus("Preparing request.");
      const output = await sendAiChatStream(
        {
          prompt,
          selectedCategoryIds: [...selectedCategoryIds],
          selectedDocuments: [...selectedDocumentKeys]
            .map(parseDocumentSelectionKey)
            .filter(isDocumentSelection),
          selectedSkillIds: [...selectedSkillIds],
          translationLanguage: selectedSkillIds.has("translation") ? translationLanguage : undefined,
          imageDataUrl,
        },
        {
          onProgress: (event) => {
            const label = aiProgressLabel(event);
            aiProgressMessageRef.current = label;
            setProgressTrail((current) => [...current.slice(-4), label]);
          },
        }
      );
      setResponse(output.answer || "Nemotron returned an empty answer.");
      setModel(output.model);
      setStatus("Response generated.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Generation failed.";
      setStatus(message);
      setResponse(message);
    } finally {
      aiProgressMessageRef.current = null;
      setGenerating(false);
    }
  }

  function toggleCategory(categoryId: string) {
    setSelectedCategoryIds((current) => toggleSetValue(current, categoryId));
  }

  function toggleDocument(key: string) {
    setSelectedDocumentKeys((current) => toggleSetValue(current, key));
  }

  function toggleSkill(skillId: string) {
    setSelectedSkillIds((current) => toggleSetValue(current, skillId));
  }

  const epic = findAvailabilitySource(availability, "epic");
  const openWearables = findAvailabilitySource(availability, "openWearables");
  const connectedWearableLabels = wearableConnections
    .map((connection) => providerLabel(connection.provider, providers))
    .join(", ");
  const selectedCategoryLabels = selectedLabelsForCategories(
    availability,
    selectedCategoryIds
  ).map((chip) => ({ ...chip, onRemove: () => toggleCategory(chip.id) }));
  const selectedDocumentLabels = selectedLabelsForDocuments(documents, selectedDocumentKeys).map(
    (chip) => ({ ...chip, onRemove: () => toggleDocument(chip.id) })
  );
  const visibleSkillIds = new Set([...selectedSkillIds].filter((id) => id !== "translation"));
  const selectedSkillLabels = selectedLabelsForSkills(visibleSkillIds).map((chip) => ({
    ...chip,
    onRemove: () => toggleSkill(chip.id),
  }));
  const selectedContextCount =
    selectedCategoryLabels.length +
    selectedDocumentLabels.length +
    selectedSkillLabels.length +
    (imageName ? 1 : 0) +
    (selectedSkillIds.has("translation") ? 1 : 0);

  return (
    <main>
      <Header />
      <section className="unifiedShell">
        <section className="connectionBar" aria-label="Connections">
          <article className={`connectionCard ${epic?.connected ? "connectedCard" : "disconnectedCard"}`}>
            <div>
              <p className="eyebrow">MyChart</p>
              <h2>
                <span className="connectionDot" aria-hidden="true" />
                {epic?.connected ? "Connected" : "Not connected"}
              </h2>
              <p className="note">
                {epic?.connected
                  ? `${epic.categories.length} categories available`
                  : "Connect Epic sandbox data."}
              </p>
            </div>
            <div className="connectionActions">
              <ConnectMyChart label={epic?.connected ? "Reconnect" : "Connect"} />
              <button
                className="secondaryButton"
                disabled={!epic?.connected}
                type="button"
                onClick={handleDisconnectEpic}
              >
                Disconnect
              </button>
              <button
                className="secondaryButton dangerButton"
                disabled={!epic?.connected}
                type="button"
                onClick={handleClearEpicData}
              >
                Clear data
              </button>
            </div>
          </article>

          <article
            className={`connectionCard ${openWearables?.connected ? "connectedCard" : "disconnectedCard"}`}
          >
            <div className="deviceHeader">
              <div>
                <p className="eyebrow">Devices</p>
                <h2>
                  <span className="connectionDot" aria-hidden="true" />
                  Open Wearables
                </h2>
              </div>
              <div className="modeToggle" role="group" aria-label="Device data mode">
                <button
                  className={dataMode === "synthetic" ? "activeToggle" : ""}
                  type="button"
                  onClick={() => setDataMode("synthetic")}
                >
                  Synthetic
                </button>
                <button
                  className={dataMode === "real" ? "activeToggle" : ""}
                  type="button"
                  onClick={() => setDataMode("real")}
                >
                  Real
                </button>
              </div>
            </div>
            <div className="deviceProviderRow">
              {providers.map((provider) => (
                <button
                  className="secondaryButton"
                  disabled={!provider.enabled || !provider.supportsOAuth}
                  key={provider.id}
                  type="button"
                  onClick={() => handleConnectProvider(provider.id)}
                >
                  {provider.name}
                </button>
              ))}
            </div>
            <p className="note">
              {openWearables?.connected
                ? `${openWearables.categories.length} data types available${
                    connectedWearableLabels ? ` from ${connectedWearableLabels}` : ""
                  }`
                : "Device metadata is loading."}
            </p>
            <div className="connectionActions">
              <button
                className="secondaryButton"
                disabled={wearableConnections.length === 0}
                type="button"
                onClick={handleDisconnectWearables}
              >
                Disconnect
              </button>
              <button
                className="secondaryButton dangerButton"
                disabled={!openWearables?.connected}
                type="button"
                onClick={handleClearWearableData}
              >
                Clear data
              </button>
            </div>
          </article>
        </section>

        <section className="composerSection chatComposerSection" aria-label="WholeYou AI">
          <div className="composerHeader">
            <div>
              <p className="eyebrow">Nemotron AI</p>
              <h1>Health conversation</h1>
              <p className="supporting">
                Ask, attach the right context, and review the answer with evidence in one place.
              </p>
            </div>
            {loading && <span className="statusPill idle">Loading data</span>}
          </div>

          <section className="chatThread" aria-label="Conversation">
            {!submittedPrompt && !response && !generating ? (
              <div className="chatEmptyState">
                <p className="eyebrow">Ready when you are</p>
                <h2>Start with a question, then add context only when it helps.</h2>
                <div className="starterGrid" aria-label="Example prompts">
                  {[
                    "Why did my recovery dip this week?",
                    "Explain this lab result in plain language.",
                    "Could sleep or medication side effects explain fatigue?",
                  ].map((example) => (
                    <button
                      className="starterPrompt"
                      key={example}
                      type="button"
                      onClick={() => setPrompt(example)}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {submittedPrompt && (
                  <article className="chatBubble userBubble">
                    <p className="bubbleLabel">You</p>
                    <p>{submittedPrompt}</p>
                  </article>
                )}
                {(generating || response) && (
                  <article className="chatBubble assistantBubble">
                    <div className="assistantBubbleHeader">
                      <p className="bubbleLabel">WholeYou</p>
                      {model && <span className="statusPill ready">{model}</span>}
                    </div>
                    {generating && (
                      <div className="progressRail" aria-label="Generation progress">
                        {progressTrail.map((item, index) => (
                          <span
                            className={index === progressTrail.length - 1 ? "activeProgressStep" : ""}
                            key={`${item}-${index}`}
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                    {response ? <FormattedResponse text={response} /> : <p className="empty">Thinking through the evidence.</p>}
                  </article>
                )}
              </>
            )}
          </section>

          <div className="contextSummaryBar">
            <div>
              <p className="eyebrow">Context</p>
              <p className="note">
                {selectedContextCount > 0
                  ? `${selectedContextCount} item${selectedContextCount === 1 ? "" : "s"} attached`
                  : "No context attached yet"}
              </p>
            </div>
            <div className="attachmentChips" aria-label="Attached context">
              {[...selectedCategoryLabels, ...selectedDocumentLabels, ...selectedSkillLabels].map((chip) => (
                <button
                  className="attachmentChip"
                  key={chip.id}
                  type="button"
                  onClick={chip.onRemove}
                  title="Remove attachment"
                >
                  {chip.label} ×
                </button>
              ))}
              {imageName && (
                <button
                  className="attachmentChip"
                  type="button"
                  onClick={() => {
                    setImageDataUrl(null);
                    setImageName(null);
                  }}
                  title="Remove image"
                >
                  {imageName} ×
                </button>
              )}
              {selectedSkillIds.has("translation") && (
                <span className="attachmentChip staticChip translationChip">
                  <span>To:</span>
                  <select
                    aria-label="Translation target language"
                    value={translationLanguage}
                    onChange={(event) => setTranslationLanguage(event.target.value)}
                  >
                    {TRANSLATION_LANGUAGES.filter((language) => language.code !== "en").map(
                      (language) => (
                        <option key={language.code} value={language.code}>
                          {language.label}
                        </option>
                      )
                    )}
                  </select>
                </span>
              )}
            </div>
          </div>

          <div className="minimalComposer">
            <button
              aria-expanded={attachmentPanel !== null}
              aria-label="Add context"
              className={attachmentPanel ? "plusButton plusButtonActive" : "plusButton"}
              type="button"
              onClick={() => setAttachmentPanel((current) => (current ? null : "data"))}
            >
              +
            </button>
            <textarea
              aria-label="Message"
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  void handleSend();
                }
              }}
              placeholder="Ask WholeYou..."
              rows={3}
              value={prompt}
            />
            <button
              className="primaryButton"
              disabled={!prompt.trim() || generating}
              type="button"
              onClick={handleSend}
            >
              {generating ? "Sending" : "Send"}
            </button>
          </div>

          {attachmentPanel && (
            <div className="attachmentPanel dynamicContextPanel">
              <div className="attachmentTabs" role="tablist" aria-label="Attachment type">
                <button
                  className={attachmentPanel === "data" ? "activeToggle" : ""}
                  type="button"
                  onClick={() => setAttachmentPanel("data")}
                >
                  Data
                </button>
                <button
                  className={attachmentPanel === "document" ? "activeToggle" : ""}
                  type="button"
                  onClick={() => setAttachmentPanel("document")}
                >
                  Document
                </button>
                <button
                  className={attachmentPanel === "skills" ? "activeToggle" : ""}
                  type="button"
                  onClick={() => setAttachmentPanel("skills")}
                >
                  Skills
                </button>
                <label className="imageAttachButton">
                  Image
                  <input
                    accept="image/*"
                    type="file"
                    onChange={(event) => void handleImageChange(event.currentTarget.files?.[0])}
                  />
                </label>
              </div>

              {attachmentPanel === "data" && (
                <div className="contextCategoryGrid compactContextGrid">
                  {availability?.sources.map((source) => (
                    <div className="contextCategoryPanel" key={source.id}>
                      <div className="contextCategorySourceHeader">
                        <h3>{source.label}</h3>
                        <span className={source.connected ? "statusPill ready" : "statusPill idle"}>
                          {source.connected ? "Available" : "Unavailable"}
                        </span>
                      </div>
                      {source.categories.length > 0 ? (
                        <div className="contextCategoryList">
                          {source.categories.map((category) => (
                            <label className="contextCategoryOption" key={category.id}>
                              <input
                                checked={selectedCategoryIds.has(category.id)}
                                disabled={!category.available}
                                type="checkbox"
                                onChange={() => toggleCategory(category.id)}
                              />
                              <span>
                                <strong>{category.label}</strong>
                                <small>
                                  {typeof category.recordCount === "number"
                                    ? `${category.recordCount} records`
                                    : category.key}
                                </small>
                              </span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <p className="empty">No data available.</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {attachmentPanel === "document" && (
                <div className="documentAttachList">
                  {documents.length > 0 ? (
                    documents.map((document) => {
                      const key = documentSelectionKey(document.categoryId, document.id);
                      return (
                        <label className="contextCategoryOption" key={key}>
                          <input
                            checked={selectedDocumentKeys.has(key)}
                            type="checkbox"
                            onChange={() => toggleDocument(key)}
                          />
                          <span>
                            <strong>{documentOptionLabel(document)}</strong>
                            <small>{document.contentType ?? document.categoryId}</small>
                          </span>
                        </label>
                      );
                    })
                  ) : (
                    <p className="empty">No documents available yet.</p>
                  )}
                </div>
              )}

              {attachmentPanel === "skills" && (
                <div
                  className="skillDropZone"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    const skillId = event.dataTransfer.getData("text/plain");
                    if (AI_SKILLS.some((skill) => skill.id === skillId)) {
                      setSelectedSkillIds((current) => {
                        const next = new Set(current);
                        next.add(skillId);
                        return next;
                      });
                    }
                  }}
                >
                  <p className="note">Drag skills here or click a skill to add it.</p>
                  <div className="skillGrid">
                    {AI_SKILLS.map((skill) => (
                      <button
                        className={selectedSkillIds.has(skill.id) ? "skillCard selected" : "skillCard"}
                        draggable
                        key={skill.id}
                        type="button"
                        onClick={() => toggleSkill(skill.id)}
                        onDragStart={(event) => {
                          event.dataTransfer.setData("text/plain", skill.id);
                          event.dataTransfer.effectAllowed = "copy";
                        }}
                      >
                        <strong>{skill.label}</strong>
                        <span>{skill.description}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {status && <p className={generating ? "note generationStatus" : "note"}>{status}</p>}
        </section>
      </section>
    </main>
  );
}

function WearablesPage() {
  const [availability, setAvailability] = useState<LocalAiContextAvailability | null>(null);
  const [providers, setProviders] = useState<WearableProvider[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [dataMode, setDataMode] = useState<WearableDataMode>("synthetic");
  const [appleXmlFile, setAppleXmlFile] = useState<File | null>(null);

  useEffect(() => {
    let ignore = false;

    loadWearablesMetadata()
      .then(({ availability, providers }) => {
        if (!ignore) {
          setAvailability(availability);
          setProviders(providers);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Unable to load wearable data");
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  async function refreshWearablesPage() {
    const { availability, providers } = await loadWearablesMetadata();
    setAvailability(availability);
    setProviders(providers);
    setError(null);
  }

  async function handleConnect(provider: string) {
    try {
      setActionStatus(
        dataMode === "synthetic"
          ? `Generating synthetic ${provider} data`
          : `Starting ${provider} OAuth`
      );
      const response = await connectWearableProvider(provider, dataMode);
      if (response.authorizationUrl) {
        window.location.href = response.authorizationUrl;
        return;
      }
      await refreshWearablesPage();
      setActionStatus(`${provider} connected in synthetic mode`);
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Connection failed");
    }
  }

  async function handleClearConnections() {
    try {
      setActionStatus("Clearing wearable connections");
      await clearWearableConnections();
      await refreshWearablesPage();
      setActionStatus("Wearable connections cleared");
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Clear connections failed");
    }
  }

  async function handleAppleXmlUpload() {
    if (!appleXmlFile) {
      setActionStatus("Choose an Apple Health export.xml file first");
      return;
    }

    try {
      setActionStatus("Importing Apple Health XML");
      const result = await uploadAppleHealthXml(appleXmlFile);
      await refreshWearablesPage();
      setActionStatus(
        `Apple Health import ${result.status ?? "completed"}: ${result.timeseriesImported ?? 0} records, ${result.workoutsImported ?? 0} workouts, ${result.sleepImported ?? 0} sleep sessions`
      );
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Apple Health XML import failed");
    }
  }

  async function handleComputeHealthScores() {
    try {
      setActionStatus("Computing health scores");
      const result = await computeWearableHealthScores();
      await refreshWearablesPage();
      setActionStatus(`Computed ${result.scoresComputed ?? 0} health scores`);
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Health score computation failed");
    }
  }

  return (
    <main>
      <Header />
      <section className="dashboardHeader">
        <div>
          <p className="eyebrow">Wearables</p>
          <h1>Open Wearables data through WholeYou backend</h1>
        </div>
        <div className="headerActions">
          <div className="modeToggle" role="group" aria-label="Wearable data mode">
            <button
              className={dataMode === "synthetic" ? "activeToggle" : ""}
              type="button"
              onClick={() => setDataMode("synthetic")}
            >
              Synthetic
            </button>
            <button
              className={dataMode === "real" ? "activeToggle" : ""}
              type="button"
              onClick={() => setDataMode("real")}
            >
              Real
            </button>
          </div>
          <button className="secondaryButton" type="button" onClick={handleClearConnections}>
            Clear connections
          </button>
          <button className="primaryButton" type="button" onClick={handleComputeHealthScores}>
            Compute health scores
          </button>
        </div>
      </section>

      {loading && <StatePanel title="Loading wearable data" />}
      {error && <StatePanel title="Could not load wearable data" detail={error} />}
      {actionStatus && <StatePanel title={actionStatus} />}

      {availability && (
        <section className="wearablesGrid">
          <section className="section wideSection">
            <h2>Providers</h2>
            <p className="note">
              {dataMode === "synthetic"
                ? "Synthetic mode creates local demo data only for the provider you connect."
                : "Real mode redirects to provider OAuth. Strava is available first; other providers are not wired yet."}
            </p>
            <div className="providerGrid">
              {providers.map((provider) => (
                <div className="item providerItem" key={provider.id}>
                  <div>
                    <h3>{provider.name}</h3>
                    <p className="note">
                      {provider.supportsImport ? "Import" : "OAuth"} ·{" "}
                      {provider.enabled ? "Enabled" : "Unavailable"}
                    </p>
                  </div>
                  {provider.supportsOAuth && (
                    <button
                      className="secondaryButton"
                      type="button"
                      onClick={() => handleConnect(provider.id)}
                    >
                      {dataMode === "synthetic" ? "Use synthetic data" : "Connect"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="section wideSection">
            <h2>Apple Health XML Import</h2>
            <p className="note">
              Upload an Apple Health export XML file. WholeYou validates and parses it on the backend,
              then adds standardized timeseries, workout, and sleep records to this dashboard.
            </p>
            <div className="uploadControls">
              <input
                accept=".xml,application/xml,text/xml"
                type="file"
                onChange={(event) => setAppleXmlFile(event.target.files?.[0] ?? null)}
              />
              <button className="secondaryButton" type="button" onClick={handleAppleXmlUpload}>
                Import Apple Health XML
              </button>
            </div>
          </section>

          <section className="section wideSection">
            <h2>Available Wearable Data</h2>
            <CategoryAvailabilityList
              emptyMessage="No wearable data categories are available."
              source={findAvailabilitySource(availability, "openWearables")}
            />
          </section>
        </section>
      )}
    </main>
  );
}

function DashboardPage() {
  const [availability, setAvailability] = useState<LocalAiContextAvailability | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;

    getLocalAiContextAvailability()
      .then((data) => {
        if (!ignore) {
          setAvailability(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Unable to load Epic data availability");
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  return (
    <main>
      <Header />
      <section className="dashboardHeader">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>Epic MyChart data availability</h1>
        </div>
        <ConnectMyChart
          label={findAvailabilitySource(availability, "epic")?.connected ? "Reconnect MyChart" : "Connect MyChart"}
        />
      </section>

      {loading && <StatePanel title="Loading Epic data availability" />}
      {error && <StatePanel title="Could not load Epic data availability" detail={error} />}

      {availability && (
        <section className="dashboardGrid">
          <section className="section wideSection">
            <h2>Available Epic Data</h2>
            <CategoryAvailabilityList
              emptyMessage="No Epic/MyChart data is connected yet."
              source={findAvailabilitySource(availability, "epic")}
            />
          </section>
        </section>
      )}
    </main>
  );
}

function ErrorPage({ message }: { message: string }) {
  const error = getErrorDetail(message);

  return (
    <main>
      <Header />
      <StatePanel title={error.title} detail={error.detail} />
    </main>
  );
}

function LogsPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [systemFilter, setSystemFilter] = useState("all");

  useEffect(() => {
    let ignore = false;

    loadLogs()
      .then((entries) => {
        if (!ignore) {
          setLogs(entries);
          setStatus(null);
        }
      })
      .catch((error: unknown) => {
        if (!ignore) {
          setStatus(error instanceof Error ? error.message : "Unable to load logs");
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  async function handleRefresh() {
    try {
      setStatus("Refreshing logs");
      setLogs(await loadLogs());
      setStatus(null);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to refresh logs");
    }
  }

  async function handleClear() {
    try {
      const result = await clearAuditLogs();
      setLogs([]);
      setStatus(`Cleared ${result.cleared} log entries`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to clear logs");
    }
  }

  const systems = ["all", ...Array.from(new Set(logs.map((log) => log.system))).sort()];
  const filteredLogs =
    systemFilter === "all" ? logs : logs.filter((log) => log.system === systemFilter);

  return (
    <main>
      <Header />
      <section className="dashboardHeader">
        <div>
          <p className="eyebrow">Logs</p>
          <h1>Backend activity and data access</h1>
        </div>
        <div className="headerActions">
          <select
            aria-label="Filter logs by system"
            className="filterSelect"
            value={systemFilter}
            onChange={(event) => setSystemFilter(event.target.value)}
          >
            {systems.map((system) => (
              <option key={system} value={system}>
                {system === "all" ? "All systems" : system}
              </option>
            ))}
          </select>
          <button className="secondaryButton" type="button" onClick={handleRefresh}>
            Refresh
          </button>
          <button className="secondaryButton dangerButton" type="button" onClick={handleClear}>
            Clear logs
          </button>
        </div>
      </section>

      {status && <StatePanel title={status} />}
      {loading && <StatePanel title="Loading logs" />}

      {!loading && (
        <section className="logsShell">
          {filteredLogs.length === 0 ? (
            <p className="empty">No backend activity has been logged yet.</p>
          ) : (
            <div className="logsList">
              {filteredLogs.map((log) => (
                <article className="logEntry" key={log.id}>
                  <div className="logEntryHeader">
                    <div>
                      <p className="logMeta">
                        {formatLogTimestamp(log.timestamp)} · {log.system} · {log.action}
                      </p>
                      <h2>{log.summary}</h2>
                    </div>
                    <span className={`statusPill ${log.status === "succeeded" ? "ready" : "idle"}`}>
                      {log.status}
                    </span>
                  </div>

                  {log.dataAccessed.length > 0 && (
                    <div className="logAccessList" aria-label="Data accessed">
                      {log.dataAccessed.map((item, index) => (
                        <span className="logAccessChip" key={`${log.id}-${index}`}>
                          {formatDataAccess(item)}
                        </span>
                      ))}
                    </div>
                  )}

                  {Object.keys(log.details).length > 0 && (
                    <details className="logDetails">
                      <summary>Details</summary>
                      <pre>{JSON.stringify(log.details, null, 2)}</pre>
                    </details>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}

async function loadLogs() {
  const response = await getAuditLogs();
  return [...response.logs].reverse();
}

async function loadWearablesMetadata() {
  const [availability, providers] = await Promise.all([
    getLocalAiContextAvailability(),
    getWearableProviders(),
  ]);
  return { availability, providers };
}

async function loadUnifiedMetadata() {
  const [availability, documents, providers, wearableConnections] = await Promise.all([
    getLocalAiContextAvailability(),
    getLocalAiDocuments(),
    getWearableProviders(),
    getWearableConnections(),
  ]);
  return { availability, documents, providers, wearableConnections };
}

function findAvailabilitySource(
  availability: LocalAiContextAvailability | null,
  sourceId: "epic" | "openWearables"
) {
  return availability?.sources.find((source) => source.id === sourceId) ?? null;
}

function providerLabel(providerId: string, providers: WearableProvider[]) {
  return providers.find((provider) => provider.id === providerId)?.name ?? providerId;
}

function CategoryAvailabilityList({
  source,
  emptyMessage,
}: {
  source: LocalAiContextSource | null;
  emptyMessage: string;
}) {
  if (!source?.connected || source.categories.length === 0) {
    return <p className="empty">{emptyMessage}</p>;
  }

  return (
    <div className="providerGrid">
      {source.categories.map((category) => (
        <div className="item" key={category.id}>
          <h3>{category.label}</h3>
          <p className="note">
            {category.available ? "Available" : "Unavailable"}
            {typeof category.recordCount === "number"
              ? ` · ${category.recordCount} records`
              : ""}
          </p>
        </div>
      ))}
    </div>
  );
}

function toggleSetValue(current: Set<string>, value: string) {
  const next = new Set(current);
  if (next.has(value)) {
    next.delete(value);
  } else {
    next.add(value);
  }
  return next;
}

function selectedLabelsForCategories(
  availability: LocalAiContextAvailability | null,
  selected: Set<string>
) {
  const labels = new Map<string, string>();
  for (const source of availability?.sources ?? []) {
    for (const category of source.categories) {
      labels.set(category.id, category.label);
    }
  }
  return [...selected].map((id) => ({
    id,
    label: labels.get(id) ?? id,
    onRemove: () => undefined,
  }));
}

function selectedLabelsForDocuments(documents: LocalAiDocument[], selected: Set<string>) {
  const labels = new Map(
    documents.map((document) => [
      documentSelectionKey(document.categoryId, document.id),
      documentOptionLabel(document),
    ])
  );
  return [...selected].map((id) => ({
    id,
    label: labels.get(id) ?? id,
    onRemove: () => undefined,
  }));
}

function selectedLabelsForSkills(selected: Set<string>) {
  const labels: Map<string, string> = new Map(
    AI_SKILLS.map((skill) => [skill.id, skill.label])
  );
  return [...selected].map((id) => ({
    id,
    label: labels.get(id) ?? id,
    onRemove: () => undefined,
  }));
}

function documentSelectionKey(categoryId: string, documentId: string) {
  return `${categoryId}:${documentId}`;
}

function parseDocumentSelectionKey(value: string) {
  const separatorIndex = value.indexOf(":");
  if (separatorIndex < 0) return null;
  return {
    categoryId: value.slice(0, separatorIndex),
    documentId: value.slice(separatorIndex + 1),
  };
}

function isDocumentSelection(
  selection: ReturnType<typeof parseDocumentSelectionKey>
): selection is { categoryId: string; documentId: string } {
  return selection !== null;
}

function aiProgressLabel(event: AiChatProgressEvent) {
  if (event.message) {
    return event.message;
  }
  if (event.stage === "using_tool" && event.toolName) {
    return `Using ${event.toolName}`;
  }
  if (event.stage === "waiting_for_tool" && event.toolName) {
    return `Waiting for ${event.toolName}`;
  }
  if (event.stage === "waiting_for_model") {
    return "Waiting for model";
  }
  if (event.stage === "thinking") {
    return "Thinking";
  }
  if (event.stage === "error") {
    return "Generation failed";
  }
  return "Generating";
}

function FormattedResponse({ text }: { text: string }) {
  return (
    <div className="formattedResponse">
      {formatResponseBlocks(text).map((block, index) => {
        if (block.type === "paragraph") {
          return <p key={index}>{block.text}</p>;
        }
        if (block.type === "tool") {
          return (
            <aside className="toolDisclosure" key={index}>
              <strong>{block.title}</strong>
              <ul>
                {block.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </aside>
          );
        }
        return (
          <ul className="responseList" key={index}>
            {block.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        );
      })}
    </div>
  );
}

function documentOptionLabel(document: LocalAiDocument) {
  return [
    document.documentType || "Document",
    document.details || document.contentType,
    document.date,
  ]
    .filter(Boolean)
    .join(" - ");
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Could not read image file."));
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("Could not read image file."));
    reader.readAsDataURL(file);
  });
}

function formatLogTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDataAccess(item: AuditLogEntry["dataAccessed"][number]) {
  const label = item.categoryLabel || item.categoryId || item.source || "Data";
  const parts = [item.source, label, item.accessType]
    .filter(Boolean)
    .map((value) => String(value));
  if (typeof item.recordCount === "number") {
    parts.push(`${item.recordCount} records`);
  }
  if (item.documentId) {
    parts.push(`document ${item.documentId}`);
  }
  if (item.contentType) {
    parts.push(item.contentType);
  }
  return parts.join(" · ");
}

function getErrorDetail(message: string) {
  const details: Record<string, { title: string; detail: string }> = {
    missing_authorization_code: {
      title: "Epic authorization was not completed",
      detail:
        "The callback URL was reached without an OAuth authorization code. Start from Connect MyChart instead of opening the callback URL directly. If this happened after logging in to Epic, confirm the sandbox app redirect URI is exactly http://localhost:8000/auth/epic/callback and that the app is ready for sandbox use.",
    },
    state_mismatch: {
      title: "Epic authorization session expired",
      detail:
        "The OAuth state did not match the current local session. Start the connection again from Connect MyChart.",
    },
    epic_authorization_failed: {
      title: "Epic authorization was declined",
      detail:
        "Epic returned an authorization error before WholeYou received a code. Start the connection again and complete the sandbox login flow.",
    },
    epic_token_exchange_or_fhir_fetch_failed: {
      title: "Epic data request failed",
      detail:
        "WholeYou received an authorization response but could not exchange it for a token or fetch FHIR data. Check the Epic sandbox app scopes, redirect URI, and readiness status.",
    },
    missing_patient_id: {
      title: "Epic did not return a patient ID",
      detail:
        "The token response did not include the SMART patient context needed to fetch patient FHIR data. Confirm the app has launch/patient and patient read scopes enabled.",
    },
  };

  return (
    details[message] ?? {
      title: "Epic connection failed",
      detail: message.replaceAll("_", " "),
    }
  );
}

function StatePanel({ title, detail }: { title: string; detail?: string | null }) {
  return (
    <section className="statePanel">
      <h2>{title}</h2>
      {detail && <p>{detail}</p>}
    </section>
  );
}

export default App;
