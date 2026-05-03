export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function EmptyState() {
  return <p className="empty">No data returned from the Epic sandbox.</p>;
}

export function SimpleList({
  rows,
  primary,
  fields,
}: {
  rows: Record<string, unknown>[];
  primary: string;
  fields: string[];
}) {
  if (rows.length === 0) return <EmptyState />;

  return (
    <div className="list">
      {rows.map((row, index) => (
        <article className="item" key={String(row.id ?? index)}>
          <h3>{display(row[primary])}</h3>
          <dl>
            {fields.map((field) => (
              <div key={field}>
                <dt>{label(field)}</dt>
                <dd>{display(row[field])}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  );
}

export function display(value: unknown) {
  return value === null || value === undefined || value === ""
    ? "Not provided"
    : String(value);
}

export function label(value: string) {
  return value
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (char) => char.toUpperCase());
}
