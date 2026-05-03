import { Section, SimpleList } from "./ui";

export function EncountersList({
  encounters,
}: {
  encounters: Record<string, unknown>[];
}) {
  return (
    <Section title="Encounters">
      <SimpleList rows={encounters} primary="type" fields={["status", "start", "end"]} />
    </Section>
  );
}
