import "./RunCostModal.css";

import type { RunCostProps } from "@gooey-types/run_cost_props";
import { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom";
import { CostBreakdown, RUN_STATUS } from "./CostBreakdown";
import { EcoImpact } from "./EcoImpact";
import {
  RUN_STEPS,
  RUN_TICKS,
  formatGrams,
  formatRuns,
  formatUsd,
} from "./ecoScale";
import { HelpTip } from "./RunCostTip";
import { Author } from "./RunDebugInfo";

type Tab = "cost" | "eco";

/**
 * A bar's cost readout: the cost (`children`), then its CO2e, as one button
 * that opens the run cost modal. Shared by the top bar and the editor run bar,
 * which differ only in styling and cost markup.
 */
export function RunCostButton({
  run_cost,
  tooltip,
  className,
  children,
}: {
  run_cost: RunCostProps;
  tooltip: string;
  className: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  // no CO2e yet before a run's first model call
  const co2e = run_cost.eco && formatGrams(run_cost.eco.co2e_grams);
  return (
    <>
      <button
        type="button"
        className={className}
        title="Run cost and environment impact"
        aria-label={`${tooltip}${co2e ? `, ${co2e} CO2e` : ""}. Open cost and environment impact`}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        {children}
        {co2e && (
          <span className="gooey-eco-co2e">
            {co2e} CO<sub>2</sub>e
          </span>
        )}
      </button>
      {open && (
        <RunCostModal run_cost={run_cost} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

/**
 * "Run Cost & Environment Impact": two cards, Total cost and Eco cost, that
 * pick the tab below them, and a slider that scales every figure from one run
 * to a million. Mounted under <body> like the other overlays.
 */
function RunCostModal({
  run_cost,
  onClose,
}: {
  run_cost: RunCostProps;
  onClose: () => void;
}) {
  const [stepIdx, setStepIdx] = useState(0);
  const [tab, setTab] = useState<Tab>("cost");
  const runs = RUN_STEPS[stepIdx];
  const contentRef = useRef<HTMLDivElement>(null);
  useSwipeDownToClose(contentRef, onClose);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const status = RUN_STATUS[run_cost.status];

  const modal = (
    <div
      className="modal show d-block gooey-run-cost-modal"
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-labelledby="gooey-run-cost-modal-title"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-lg">
        <div
          ref={contentRef}
          className="modal-content gooey-run-cost-modal-content"
        >
          {/* the action sheet's grab handle; shown only while this is a sheet */}
          <div
            className="gooey-sheet-handle-wrap gooey-run-cost-sheet-handle"
            aria-hidden="true"
          >
            <div className="gooey-sheet-handle" />
          </div>
          <div className="gooey-run-cost-modal-head">
            <div>
              <h2
                id="gooey-run-cost-modal-title"
                className="gooey-run-cost-modal-title"
              >
                Run Cost &amp; Environment Impact
              </h2>
              <div className="gooey-run-cost-modal-sub">
                {run_cost.run_by && (
                  <span>
                    Run by <Author author={run_cost.run_by} fallback="" />
                  </span>
                )}
                {run_cost.run_by && run_cost.charged_to && (
                  <span className="gooey-run-cost-dot" />
                )}
                {run_cost.charged_to && (
                  // the balance is the charged workspace's, so it stays on
                  // this line, dot and all, even where the other dots hide;
                  // a long name is cut with an ellipsis instead
                  <span>
                    Charged to{" "}
                    <Author author={run_cost.charged_to} fallback="" />
                    {run_cost.balance && run_cost.balance_url && (
                      <>
                        <span className="gooey-run-cost-dot" />
                        <a
                          href={run_cost.balance_url}
                          target="_blank"
                          rel="noreferrer"
                          className="gooey-run-cost-balance"
                        >
                          Balance: {run_cost.balance}{" "}
                          <i className="fa-regular fa-arrow-up-right" />
                        </a>
                      </>
                    )}
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              className="btn-close"
              aria-label="Close"
              onClick={onClose}
            />
          </div>

          <div className="gooey-run-cost-modal-body">
            <div
              className="gooey-run-cost-tabs"
              role="tablist"
              aria-label="Show the run's"
            >
              <TabCard
                id="cost"
                selected={tab === "cost"}
                onSelect={setTab}
                icon="fa-regular fa-coin"
                label="Total cost"
              >
                <div className="gooey-run-cost-tab-value">
                  {run_cost.status === "running" && "≥ "}
                  {formatUsd(run_cost.run_cost_usd * runs)}
                </div>
                {status?.sub && (
                  <div className="gooey-run-cost-tab-sub">{status.sub}</div>
                )}
              </TabCard>
              <TabCard
                id="eco"
                selected={tab === "eco"}
                onSelect={setTab}
                disabled={!run_cost.eco}
                icon="fa-regular fa-leaf"
                label="Eco cost"
              >
                {run_cost.eco ? (
                  <>
                    <div className="gooey-run-cost-tab-value gooey-eco-green">
                      {formatGrams(run_cost.eco.co2e_grams * runs)}{" "}
                      <span className="gooey-eco-unit">
                        CO<sub>2</sub>e
                      </span>
                    </div>
                    <div className="gooey-run-cost-tab-sub">
                      range {formatGrams(run_cost.eco.co2e_min * runs)} –{" "}
                      {formatGrams(run_cost.eco.co2e_max * runs)}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="gooey-run-cost-tab-value">—</div>
                    {/* a running run gets its figures with the first model
                        call; a finished one without them recorded no model
                        usage, or used a model ecocost has no data for */}
                    {run_cost.status !== "running" && (
                      <div className="gooey-run-cost-tab-sub">
                        Not available for this run
                      </div>
                    )}
                  </>
                )}
              </TabCard>
            </div>

            <div className="gooey-run-cost-slider">
              <label htmlFor="gooey-run-cost-runs">
                <span className="gooey-run-cost-slider-unit">
                  Conversation turns
                </span>
                <HelpTip
                  content={<ScaleTable runs={runs} />}
                  label="What the scale counts"
                />
              </label>
              <div className="gooey-run-cost-slider-track">
                <input
                  id="gooey-run-cost-runs"
                  type="range"
                  min={0}
                  max={RUN_STEPS.length - 1}
                  step={1}
                  value={stepIdx}
                  onChange={(e) => setStepIdx(Number(e.target.value))}
                  aria-valuetext={`${formatRuns(runs)} conversation turns`}
                  // the page form re-submits on any change that bubbles to it
                  data-submit-disabled=""
                  style={
                    {
                      "--pct": `${stepFraction(runs) * 100}%`,
                    } as React.CSSProperties
                  }
                />
                <div className="gooey-run-cost-slider-ticks" aria-hidden="true">
                  {RUN_TICKS.map((n) => (
                    <span
                      key={n}
                      // centred under the thumb, which is 18px wide
                      style={{
                        left: `calc(9px + ${stepFraction(n) * 100}% - ${stepFraction(n) * 18}px)`,
                      }}
                    >
                      {formatRuns(n)}
                    </span>
                  ))}
                </div>
              </div>
              {/* Sized to the widest count so the track never resizes mid-drag. */}
              <output
                htmlFor="gooey-run-cost-runs"
                className="gooey-run-cost-slider-value"
              >
                <span
                  aria-hidden="true"
                  className="gooey-run-cost-slider-sizer"
                >
                  500k
                </span>
                <span>{formatRuns(runs)}</span>
              </output>
            </div>

            {tab === "cost" && (
              <CostBreakdown run_cost={run_cost} runs={runs} />
            )}
            {tab === "eco" && run_cost.eco && (
              <EcoImpact
                eco={run_cost.eco}
                methodology_url={run_cost.methodology_url}
                runs={runs}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return null;
  return ReactDOM.createPortal(modal, document.body);
}

/** One of the two cards above the slider. Each is a tab: picking it shows its
 * panel below. */
function TabCard({
  id,
  selected,
  onSelect,
  disabled,
  icon,
  label,
  children,
}: {
  id: Tab;
  selected: boolean;
  onSelect: (tab: Tab) => void;
  disabled?: boolean;
  icon: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={`gooey-run-cost-tab-${id}`}
      aria-selected={selected}
      aria-controls={`gooey-run-cost-panel-${id}`}
      className={`gooey-run-cost-tab${selected ? " gooey-run-cost-tab-selected" : ""}`}
      disabled={disabled}
      onClick={() => onSelect(id)}
    >
      <span className="gooey-run-cost-tab-label">
        <span>
          <i className={icon} aria-hidden="true" />
          {label}
        </span>
        <span className="gooey-run-cost-radio" aria-hidden="true" />
      </span>
      {children}
    </button>
  );
}

const SWIPE_MS = 200;

/**
 * The sheet follows a finger pulling it down and closes past a quarter of its
 * height. A pull only starts with the sheet's content scrolled to the top, so
 * it never takes over scrolling back up.
 */
function useSwipeDownToClose(
  contentRef: React.RefObject<HTMLDivElement>,
  onClose: () => void
) {
  useEffect(() => {
    const content = contentRef.current;
    const sheet = content?.closest<HTMLElement>(".modal-dialog");
    const handle = content?.querySelector<HTMLElement>(
      ".gooey-run-cost-sheet-handle"
    );
    if (!content || !sheet || !handle) return;

    let startX = 0;
    let startY: number | null = null;
    let dy = 0;
    let closing = false;

    const onStart = (e: TouchEvent) => {
      // a touch during the slide down would pull the sheet back up
      if (closing) return;
      // only while the modal is a sheet, which is when its grab handle shows
      if (getComputedStyle(handle).display === "none") return;
      if (content.scrollTop > 0) return;
      // the runs slider is dragged sideways and must keep its touches
      if ((e.target as Element).closest("input[type=range]")) return;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dy = 0;
    };
    const onMove = (e: TouchEvent) => {
      if (startY === null) return;
      const { clientX, clientY } = e.touches[0];
      // a gesture that starts sideways is not a pull
      if (!dy && Math.abs(clientX - startX) > Math.abs(clientY - startY)) {
        startY = null;
        return;
      }
      dy = Math.max(0, clientY - startY);
      if (!dy) {
        sheet.style.transform = "";
        return;
      }
      // the pull moves the sheet, not the content under the finger
      e.preventDefault();
      sheet.style.transition = "none";
      sheet.style.transform = `translateY(${dy}px)`;
    };
    const onEnd = (e: TouchEvent) => {
      if (startY === null) return;
      startY = null;
      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      sheet.style.transition = reduceMotion
        ? "none"
        : `transform ${SWIPE_MS}ms ease-out`;
      // an interrupted touch is not a release, so it never closes the sheet
      if (e.type === "touchcancel" || dy < sheet.offsetHeight / 4) {
        sheet.style.transform = "";
        return;
      }
      closing = true;
      if (reduceMotion) {
        onClose();
        return;
      }
      sheet.style.transform = "translateY(100%)";
      window.setTimeout(onClose, SWIPE_MS);
    };

    content.addEventListener("touchstart", onStart);
    // not passive, so a pull can stop the content scrolling
    content.addEventListener("touchmove", onMove, { passive: false });
    content.addEventListener("touchend", onEnd);
    content.addEventListener("touchcancel", onEnd);
    return () => {
      content.removeEventListener("touchstart", onStart);
      content.removeEventListener("touchmove", onMove);
      content.removeEventListener("touchend", onEnd);
      content.removeEventListener("touchcancel", onEnd);
    };
  }, [contentRef, onClose]);
}

/** Where a count sits along the slider, 0..1. */
function stepFraction(n: number): number {
  return (
    RUN_STEPS.indexOf(n as (typeof RUN_STEPS)[number]) / (RUN_STEPS.length - 1)
  );
}

const DAYS_PER_MONTH = 30;
const MESSAGES_PER_USER_PER_MONTH = 8;

/** The slider's tooltip: the count read as a month of traffic, assuming each
 * user sends about 8 messages a month. The modal only shows on the Agent page
 * (the one layout-v2 recipe), where a run is one conversation turn. */
function ScaleTable({ runs }: { runs: number }) {
  const approx = (n: number) =>
    n < 1 ? "< 1" : `≈ ${Number(n.toPrecision(2)).toLocaleString("en-US")}`;
  const rows: [string, string][] = [
    ["Messages / month", runs.toLocaleString("en-US")],
    ["Daily messages", approx(runs / DAYS_PER_MONTH)],
    ["Users / month", approx(runs / MESSAGES_PER_USER_PER_MONTH)],
  ];
  return (
    <>
      <dl className="gooey-run-cost-help-table">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="gooey-run-cost-help-note">
        Assumes {MESSAGES_PER_USER_PER_MONTH} messages a month per user.
      </p>
    </>
  );
}
