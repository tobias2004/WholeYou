import { Section, SimpleList } from "./ui";

export function MedicationsList({
  medications,
}: {
  medications: Record<string, unknown>[];
}) {
  return (
    <Section title="Medications">
      <SimpleList
        rows={medications}
        primary="name"
        fields={["status", "intent", "authoredOn", "dosageText"]}
      />
    </Section>
  );
}
