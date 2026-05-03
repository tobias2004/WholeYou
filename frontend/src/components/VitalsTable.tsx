import { ClinicalRow } from "../api";
import { ClinicalTable } from "./LabsTable";
import { Section } from "./ui";

export function VitalsTable({ vitals }: { vitals: ClinicalRow[] }) {
  return (
    <Section title="Vitals">
      <ClinicalTable rows={vitals} />
    </Section>
  );
}
