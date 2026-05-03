import { EpicSummary } from "../api";
import { display, Section } from "./ui";

export function PatientSummary({
  patient,
  metadata,
}: {
  patient: EpicSummary["patient"];
  metadata: EpicSummary["metadata"];
}) {
  return (
    <Section title="Patient Profile">
      <div className="profileGrid">
        <Metric label="Name" value={patient?.name} />
        <Metric label="FHIR ID" value={patient?.id} />
        <Metric label="Birth date" value={patient?.birthDate} />
        <Metric label="Gender" value={patient?.gender} />
        <Metric label="Retrieved" value={metadata?.retrievedAt} />
      </div>
      {metadata?.note && <p className="note">{metadata.note}</p>}
    </Section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{display(value)}</strong>
    </div>
  );
}
