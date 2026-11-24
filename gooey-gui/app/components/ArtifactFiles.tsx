import { useState } from "react";
import type { ArtifactFilesProps } from "@gooey-types/artifact_props";
import type { CustomComponentProps } from "~/components";

export function ArtifactFiles({
  summary,
  entries,
  selected,
}: CustomComponentProps & ArtifactFilesProps) {
  const files = entries.filter((entry) => !entry.is_folder);
  const [path, setPath] = useState(selected ?? files[0]?.path);
  const [copied, setCopied] = useState(false);
  const file = files.find((entry) => entry.path === path) ?? files[0];
  const lines = file?.content?.split("\n") ?? [];

  const copy = () => {
    if (!file?.content) return;
    navigator.clipboard?.writeText(file.content).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {}
    );
  };

  return (
    <div
      className="d-flex border rounded-3 bg-body overflow-hidden h-100 mx-2 mx-lg-0"
      style={{ minHeight: 0 }}
    >
      <div
        className="border-end bg-body-tertiary p-2 overflow-auto flex-shrink-0"
        style={{ width: 220 }}
      >
        <div className="small text-muted px-2 py-1">{summary}</div>
        {entries.map((entry) =>
          entry.is_folder ? (
            <div
              key={entry.path}
              className="d-flex align-items-center gap-2 px-2 py-1 small"
              style={{ paddingLeft: 8 + (entry.depth ?? 0) * 16 }}
            >
              <i className="fa-regular fa-folder" aria-hidden="true" />
              {entry.name}
            </div>
          ) : (
            <button
              key={entry.path}
              type="button"
              onClick={() => setPath(entry.path)}
              className={`btn btn-sm w-100 d-flex align-items-center gap-2 text-start rounded-2 border-0 ${
                entry.path === file?.path ? "bg-body-secondary" : ""
              }`}
              style={{ paddingLeft: 8 + (entry.depth ?? 0) * 16 }}
            >
              <i className="fa-regular fa-file-lines" aria-hidden="true" />
              <span className="flex-grow-1 text-truncate">{entry.name}</span>
              <span className="text-muted small">{entry.size_label}</span>
            </button>
          )
        )}
      </div>
      <div className="d-flex flex-column flex-grow-1" style={{ minWidth: 0 }}>
        {file && (
          <div className="d-flex align-items-center gap-3 border-bottom px-3 py-2 small">
            <span className="fw-semibold flex-grow-1 text-truncate">{file.path}</span>
            <span className="text-muted">
              {file.type_label} · {file.size_label}
            </span>
            {file.content != null && (
              <button
                type="button"
                className="btn btn-sm btn-link text-reset p-0"
                onClick={copy}
              >
                <i className="fa-regular fa-copy me-1" />
                {copied ? "Copied" : "Copy"}
              </button>
            )}
            {file.download_url && (
              <a href={file.download_url} className="text-reset text-decoration-none">
                <i className="fa-regular fa-download me-1" />
                Download
              </a>
            )}
          </div>
        )}
        <div className="flex-grow-1 overflow-auto" style={{ minHeight: 0 }}>
          {file?.content != null ? (
            <table className="font-monospace small mb-0" style={{ borderSpacing: 0 }}>
              <tbody>
                {lines.map((line, i) => (
                  <tr key={i}>
                    <td
                      className="text-muted text-end user-select-none px-3"
                      style={{ verticalAlign: "top" }}
                    >
                      {i + 1}
                    </td>
                    <td className="pe-3" style={{ whiteSpace: "pre" }}>
                      {line}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="text-muted p-4">
              {file ? "This file can't be shown here; download it to look at it." : ""}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
