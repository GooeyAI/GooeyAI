import "./CostBreakdown.css";

import type {
  CostBreakdownProps,
  CostLineProps,
  RunCostProps,
} from "@gooey-types/run_cost_props";
import { useEffect, useState } from "react";
import { formatCount, formatUsd } from "./ecoScale";
import { HelpTip } from "./RunCostTip";

/** A run that is not simply done: the cost card's line and the Cost tab's
 * pill. A finished, billed run has none. */
export const RUN_STATUS: Partial<
  Record<RunCostProps["status"], { sub?: string; pill: string }>
> = {
  running: { pill: "Running" },
  failed: { sub: "Not charged · the run failed", pill: "Failed" },
  cancelled: { sub: "Not charged · cancelled", pill: "Cancelled" },
};

/** The run cost modal's Cost tab: what the run was billed, line by line. A
 * run with no lines (failed, cancelled, or its settings edited since) has its
 * total on the card above. */
export function CostBreakdown({
  run_cost,
  runs,
}: {
  run_cost: RunCostProps;
  runs: number;
}) {
  const status = RUN_STATUS[run_cost.status];
  const running = run_cost.status === "running";
  return (
    <div
      role="tabpanel"
      id="gooey-run-cost-panel-cost"
      aria-labelledby="gooey-run-cost-tab-cost"
      className="gooey-run-cost-panel"
    >
      {status && (
        <span
          className={`gooey-cost-status gooey-cost-status-${run_cost.status}`}
        >
          {status.pill}
          {running && <Elapsed since={run_cost.created_at} />}
        </span>
      )}
      {run_cost.cost_breakdown && (
        <CostTable
          breakdown={run_cost.cost_breakdown}
          runs={runs}
          running={running}
        />
      )}
      <RunTime
        // while running, the pill counts the time up instead
        run_time_s={running ? null : run_cost.run_time_s}
        created_at={run_cost.created_at}
      />
    </div>
  );
}

/** " · 14s" since the run started, ticking each second. The page re-renders
 * on every run update anyway; this keeps the clock moving between them. */
function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.round((now - Date.parse(since)) / 1000));
  return <> · {seconds}s</>;
}

/** Each model's lines under its logo, name and subtotal, then the run's own
 * charges, then the total, all scaled to the slider's runs. While the run is
 * going the total is a floor: more rounds may still come. */
function CostTable({
  breakdown,
  runs,
  running,
}: {
  breakdown: CostBreakdownProps;
  runs: number;
  running: boolean;
}) {
  // one precision for every amount in the table: cents once the total reaches
  // a dollar, three places below it
  const digits = breakdown.total_usd * runs >= 1 ? 2 : 3;
  const usd = (amount: number) => formatUsd(amount * runs, digits);
  const linesUsd = breakdown.sections
    .flatMap((section) => section.lines)
    .reduce((sum, line) => sum + line.usd, 0);
  // explained for one run only: a running total is still a floor, and at
  // scale the rounding is per run, not on the scaled lines
  const rounded =
    runs === 1 && !running && breakdown.total_usd - linesUsd > 1e-9;
  // what the viewer folded or opened, by heading: sections arrive and move
  // while the run is going, so their place in the list is not stable
  const [toggled, setToggled] = useState(() => new Set<string>());
  const toggle = (label: string) =>
    setToggled((prev) => {
      const next = new Set(prev);
      if (!next.delete(label)) next.add(label);
      return next;
    });
  return (
    <div className="gooey-cost-table">
      {breakdown.sections.map((section, i) => {
        if (!section.lines.length) return null;
        const open = section.collapsed === toggled.has(section.label ?? "");
        const head = (
          <>
            <span title={section.label ?? undefined}>
              {section.icon_url && (
                <img
                  src={section.icon_url}
                  alt=""
                  className="gooey-cost-logo"
                />
              )}
              {section.label}
            </span>
            {section.usd != null && (
              <span className="gooey-cost-amount">{usd(section.usd)}</span>
            )}
          </>
        );
        return (
          <div key={i} className="gooey-cost-section">
            {/* a model's or the tool calls' heading folds its lines */}
            {section.label && (
              <button
                type="button"
                className="gooey-cost-row gooey-cost-head gooey-cost-fold"
                aria-expanded={open}
                onClick={() => toggle(section.label!)}
              >
                {head}
                <i
                  className={`fa-regular fa-angle-${open ? "up" : "down"}`}
                  aria-hidden="true"
                />
              </button>
            )}
            {open &&
              section.lines.map((line, j) => (
                <CostLine key={j} line={line} runs={runs} usd={usd} />
              ))}
          </div>
        );
      })}
      <div className="gooey-cost-row gooey-cost-total">
        <span>
          Total
          {rounded && (
            <HelpTip
              content={`Rounded up from ${formatUsd(linesUsd * runs, 4)}: runs are billed in whole cents.`}
              label="Why the total is higher than its lines"
            />
          )}
        </span>
        <span className="gooey-cost-amount">
          {running && "≥ "}
          {usd(breakdown.total_usd)}
        </span>
      </div>
    </div>
  );
}

function CostLine({
  line,
  runs,
  usd,
}: {
  line: CostLineProps;
  runs: number;
  usd: (amount: number) => string;
}) {
  const note =
    line.quantity != null && line.unit_price
      ? `${formatCount(line.quantity * runs)} × ${line.unit_price}`
      : line.note;
  return (
    <div className="gooey-cost-row">
      <span className="gooey-cost-text">
        {line.url ? (
          <a
            href={line.url}
            target="_blank"
            rel="noreferrer"
            title={line.label}
          >
            {line.label}
          </a>
        ) : (
          <span title={line.label}>{line.label}</span>
        )}
        {note && <span className="gooey-cost-sub">{note}</span>}
      </span>
      <span className="gooey-cost-amount">{usd(line.usd)}</span>
    </div>
  );
}

/** "39s · 8:02 PM", as under a chat message, with the date when it is not
 * today, in the viewer's time zone. A running run has no duration yet: its
 * pill counts up. The modal only mounts on a click, so this never renders on
 * the server. */
function RunTime({
  run_time_s,
  created_at,
}: {
  run_time_s: number | null;
  created_at: string;
}) {
  const date = new Date(created_at);
  const today = date.toDateString() === new Date().toDateString();
  const time = date.toLocaleString("en-US", {
    ...(today ? {} : { month: "short", day: "numeric" }),
    hour: "numeric",
    minute: "2-digit",
  });
  return (
    <div className="gooey-cost-generated">
      <i className="fa-regular fa-clock" aria-hidden="true" />
      {run_time_s ? `${Math.round(run_time_s)}s · ${time}` : time}
    </div>
  );
}
