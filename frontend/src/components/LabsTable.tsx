import { ClinicalRow } from "../api";
import { display, EmptyState, Section } from "./ui";

export function LabsTable({ labs }: { labs: ClinicalRow[] }) {
  return (
    <Section title="Lab Results">
      <ClinicalTable rows={labs} includeFlag />
    </Section>
  );
}

export function ClinicalTable({
  rows,
  includeFlag = false,
}: {
  rows: ClinicalRow[];
  includeFlag?: boolean;
}) {
  if (rows.length === 0) return <EmptyState />;

  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Value</th>
            <th>Date</th>
            <th>Status</th>
            {includeFlag && <th>Flag</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id ?? index}>
              <td>{display(row.name)}</td>
              <td>
                {display(row.value)} {row.unit ? row.unit : ""}
              </td>
              <td>{display(row.date)}</td>
              <td>{display(row.status)}</td>
              {includeFlag && <td>{display(row.flag)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
