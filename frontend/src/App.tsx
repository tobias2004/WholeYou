import { useEffect, useState } from "react";
import { getEpicRaw } from "./api";
import { ConnectMyChart } from "./components/ConnectMyChart";
import { Header } from "./components/Header";

function App() {
  const path = window.location.pathname;

  if (path === "/dashboard") {
    return <DashboardPage />;
  }

  if (path === "/error") {
    const message = new URLSearchParams(window.location.search).get("message");
    return <ErrorPage message={message ?? "epic_connection_failed"} />;
  }

  return <LandingPage />;
}

function LandingPage() {
  return (
    <main>
      <Header />
      <section className="hero">
        <div className="heroContent">
          <p className="eyebrow">Epic/MyChart sandbox</p>
          <h1>WholeYou</h1>
          <p className="slogan">
            WholeYou connects your health records, wearable data, and daily
            patterns into private, personalized wellness guidance.
          </p>
          <ConnectMyChart />
          <p className="supporting">
            Currently supports Epic/MyChart sandbox data only. Wearables and
            local AI guidance will be added later.
          </p>
        </div>
      </section>
    </main>
  );
}

function DashboardPage() {
  const [rawData, setRawData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    getEpicRaw()
      .then((data) => {
        if (!ignore) {
          setRawData(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Unable to load summary");
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
          <h1>Raw Epic/MyChart sandbox FHIR response</h1>
        </div>
        <ConnectMyChart label={rawData ? "Reconnect MyChart" : "Connect MyChart"} />
      </section>

      {loading && <StatePanel title="Loading Epic sandbox data" />}
      {error && <StatePanel title="Could not load Epic data" detail={error} />}
      {!loading && !error && rawData?.connected === false && (
        <StatePanel
          title="No Epic/MyChart sandbox data connected yet."
          detail={String(rawData.message ?? "")}
        />
      )}

      {rawData && rawData.connected !== false && (
        <section className="jsonPanel">
          <div className="jsonToolbar">
            <button
              className="secondaryButton"
              type="button"
              onClick={() => copyRawJson(rawData, setCopyStatus)}
            >
              Copy raw JSON
            </button>
            {copyStatus && <span>{copyStatus}</span>}
          </div>
          <JsonTree name="mychart" value={rawData} defaultOpen />
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

function JsonTree({
  name,
  value,
  defaultOpen = false,
}: {
  name: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  if (Array.isArray(value)) {
    return (
      <details className="jsonNode" open={defaultOpen}>
        <summary>
          <span className="jsonKey">{name}</span>
          <span className="jsonMeta">Array({value.length})</span>
        </summary>
        <div className="jsonChildren">
          {value.map((item, index) => (
            <JsonTree key={index} name={String(index)} value={item} />
          ))}
        </div>
      </details>
    );
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <details className="jsonNode" open={defaultOpen}>
        <summary>
          <span className="jsonKey">{name}</span>
          <span className="jsonMeta">Object({entries.length})</span>
        </summary>
        <div className="jsonChildren">
          {entries.map(([key, child]) => (
            <JsonTree key={key} name={key} value={child} />
          ))}
        </div>
      </details>
    );
  }

  return (
    <div className="jsonLeaf">
      <span className="jsonKey">{name}</span>
      <span className={`jsonValue jsonValue-${typeof value}`}>{formatJsonValue(value)}</span>
    </div>
  );
}

function formatJsonValue(value: unknown) {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "undefined") return "undefined";
  return String(value);
}

async function copyRawJson(
  rawData: Record<string, unknown>,
  setCopyStatus: (status: string | null) => void
) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(rawData));
    setCopyStatus("Copied");
    window.setTimeout(() => setCopyStatus(null), 1800);
  } catch {
    setCopyStatus("Copy failed");
  }
}

export default App;
