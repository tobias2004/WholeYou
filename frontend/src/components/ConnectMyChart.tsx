export function ConnectMyChart({ label = "Connect MyChart" }: { label?: string }) {
  return (
    <button
      className="primaryButton"
      type="button"
      onClick={() => {
        window.location.href = "http://localhost:8000/connect/epic";
      }}
    >
      {label}
    </button>
  );
}
