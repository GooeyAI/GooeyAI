import type { ArtifactGridProps } from "@gooey-types/artifact_props";
import type { CustomComponentProps } from "~/components";

const TONE_CLASS = {
  live: "text-bg-success",
  draft: "text-bg-warning",
  muted: "text-bg-secondary",
} as const;

export function ArtifactGrid({
  workspace_name,
  cards,
  empty_message,
}: CustomComponentProps & ArtifactGridProps) {
  return (
    <div className="d-flex flex-column gap-3 py-3">
      <div>
        <h1 className="h3 mb-1">Artifacts</h1>
        <div className="text-muted small">
          Websites made with Ask Gooey and functions in {workspace_name}
        </div>
      </div>
      {cards.length ? (
        <div
          className="d-grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
        >
          {cards.map((card) => (
            <a
              key={card.href}
              href={card.href}
              className="card text-decoration-none text-reset h-100"
            >
              <div
                className="card-img-top d-flex align-items-center justify-content-center"
                style={{
                  aspectRatio: "16 / 9",
                  background:
                    "linear-gradient(135deg, var(--bs-secondary-bg, #eef0f4), var(--bs-tertiary-bg, #f7f8fa))",
                }}
              >
                <i
                  className="fa-regular fa-window-maximize fa-2x text-muted"
                  aria-hidden="true"
                />
              </div>
              <div className="card-body d-flex flex-column gap-1">
                <div className="d-flex align-items-start justify-content-between gap-2">
                  <span className="fw-semibold text-truncate">{card.title}</span>
                  <span className={`badge ${TONE_CLASS[card.status_tone ?? "muted"]}`}>
                    {card.status}
                  </span>
                </div>
                <div className="small text-muted text-truncate">
                  {card.author} · {card.updated_at_label}
                </div>
                {card.note && (
                  <div className="small text-primary">{card.note}</div>
                )}
              </div>
            </a>
          ))}
        </div>
      ) : (
        <div className="text-muted">{empty_message}</div>
      )}
    </div>
  );
}
