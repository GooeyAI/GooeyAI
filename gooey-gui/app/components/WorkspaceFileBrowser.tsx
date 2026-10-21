import type {
  WorkspaceFileBrowserProps,
  WorkspaceFileEntry,
} from "@gooey-types/workspace_files_props";
import type { CustomComponentProps } from "~/components";

export function WorkspaceFileBrowser({
  description,
  entries,
  next_page_url,
}: CustomComponentProps & WorkspaceFileBrowserProps) {
  return (
    <div>
      <h2 className="mb-3">
        <i className="fa-regular fa-folder-open me-2" aria-hidden="true" />
        Files
      </h2>

      <p className="text-muted">{description}</p>

      {entries.length === 0 ? (
        <p className="text-muted small">
          No files yet. They appear here when a Python or Bash function writes
          to its working directory.
        </p>
      ) : (
        <div className="border rounded-3">
          {entries.map((entry, i) => (
            <WorkspaceFileRow
              key={entry.path}
              entry={entry}
              isFirst={i === 0}
            />
          ))}
        </div>
      )}

      {next_page_url ? (
        <div className="text-center my-4">
          <a href={next_page_url} className="btn btn-theme btn-secondary">
            Load more
          </a>
        </div>
      ) : null}
    </div>
  );
}

function WorkspaceFileRow({
  entry,
  isFirst,
}: {
  entry: WorkspaceFileEntry;
  isFirst: boolean;
}) {
  return (
    <div
      className={`d-flex align-items-center gap-3 px-3 py-2 ${
        isFirst ? "" : "border-top"
      }`}
    >
      <i className="fa-regular fa-file text-muted" aria-hidden="true" />
      <a
        // the server generates a presigned url on click and redirects to it
        href={entry.href}
        target="_blank"
        rel="noreferrer"
        className="font-monospace text-break flex-grow-1"
      >
        {entry.path}
      </a>
      <span className="small text-muted text-nowrap">{entry.size_label}</span>
      <span
        className="small text-muted text-nowrap d-none d-md-inline"
        style={{ minWidth: "8rem", textAlign: "right" }}
      >
        {entry.updated_at_label}
      </span>
    </div>
  );
}
