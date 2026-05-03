import { Section, SimpleList } from "./ui";

export function ConditionsList({
  conditions,
}: {
  conditions: Record<string, unknown>[];
}) {
  return (
    <Section title="Conditions / Diagnoses">
      <SimpleList
        rows={conditions}
        primary="name"
        fields={["clinicalStatus", "verificationStatus", "onsetDate"]}
      />
    </Section>
  );
}
