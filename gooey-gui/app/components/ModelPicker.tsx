import "./ModelPicker.css";

import type {
  ModelPickerOption,
  ModelPickerProps,
} from "@gooey-types/model_picker_props";
import clsx from "clsx";
import type { KeyboardEvent } from "react";
import { useLayoutEffect, useRef, useState } from "react";
import ReactDOM from "react-dom";
import type { CustomComponentProps } from "~/components";
import { formatTokens } from "./ecoScale";

type Modality = ModelPickerOption["inputs"][number];

const INPUT_MODALITIES: Array<[Modality, string, string]> = [
  ["text", "fa-text", "Text"],
  ["audio", "fa-microphone", "Audio"],
  ["image", "fa-image", "Image"],
];
const OUTPUT_MODALITIES: Array<[Modality, string, string]> = [
  ["text", "fa-text", "Text"],
  ["audio", "fa-volume", "Audio"],
];

/**
 * The selected model as a trigger that opens "Choose a model". The pick and its effort
 * stay staged in the dialog until "Use model" writes them to the form state.
 */
export function ModelPicker({
  name,
  effort_name,
  efforts,
  options,
  co2e_methodology_url,
  state,
  onChange,
}: CustomComponentProps & ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = options.find((o) => o.name === state[name]) ?? options[0];
  if (!selected) return null;

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };
  const confirm = (model: ModelPickerOption, effort: string | null) => {
    close();
    // effort only applies to reasoning models; others leave it as it was
    const nextEffort = model.reasoning && effort ? effort : state[effort_name];
    if (model.name === state[name] && nextEffort === state[effort_name]) return;
    state[name] = model.name;
    state[effort_name] = nextEffort;
    onChange();
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="gooey-model-trigger"
        aria-haspopup="dialog"
        aria-label={`Model: ${selected.label}. Change model`}
        onClick={() => setOpen(true)}
      >
        <ModelIcon option={selected} size={20} />
        <span className="gooey-model-trigger-label">{selected.label}</span>
        {selected.price && (
          <span className="gooey-model-trigger-price">
            <span className="gooey-model-divider" />
            <Price price={selected.price} />
          </span>
        )}
        <span className="gooey-model-trigger-end">
          {selected.co2e && <EcoChip co2e={selected.co2e} />}
          <span className="gooey-model-divider" />
          <i className="fa-regular fa-chevron-down" aria-hidden="true" />
        </span>
      </button>
      {open && (
        <ModelPickerDialog
          options={options}
          efforts={efforts}
          co2eMethodologyUrl={co2e_methodology_url}
          initialModel={selected.name}
          initialEffort={state[effort_name] ?? null}
          onCancel={close}
          onConfirm={confirm}
        />
      )}
    </>
  );
}

function ModelPickerDialog({
  options,
  efforts,
  co2eMethodologyUrl,
  initialModel,
  initialEffort,
  onCancel,
  onConfirm,
}: {
  options: ModelPickerOption[];
  efforts: ModelPickerProps["efforts"];
  co2eMethodologyUrl: string;
  initialModel: string;
  initialEffort: string | null;
  onCancel: () => void;
  onConfirm: (model: ModelPickerOption, effort: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(initialModel);
  const [effort, setEffort] = useState(initialEffort);
  // below 768px the two panes take turns: picking a row opens its detail
  const [narrowView, setNarrowView] = useState<"list" | "detail">("list");
  const dialogRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const matches = filterOptions(options, query);
  const current = options.find((o) => o.name === highlighted) ?? options[0];
  const currentListed = matches.includes(current);

  // before paint, so the list never shows its top and then jumps to the pick
  useLayoutEffect(() => {
    document
      .getElementById(optionId(initialModel))
      ?.scrollIntoView({ block: "center" });
    // a phone would raise its keyboard over the list
    if (window.matchMedia("(min-width: 768px)").matches) {
      searchRef.current?.focus();
    } else {
      dialogRef.current?.focus();
    }
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [initialModel]);

  const search = (value: string) => {
    setQuery(value);
    const next = filterOptions(options, value);
    if (next.length && !next.some((o) => o.name === highlighted)) {
      setHighlighted(next[0].name);
    }
  };

  const move = (delta: number) => {
    if (!matches.length) return;
    const index = matches.findIndex((o) => o.name === highlighted);
    const next =
      matches[Math.min(matches.length - 1, Math.max(0, index + delta))];
    setHighlighted(next.name);
    document
      .getElementById(optionId(next.name))
      ?.scrollIntoView({ block: "nearest" });
  };

  const onSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      move(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      onConfirm(current, effort);
    }
  };

  const onDialogKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    } else if (e.key === "Tab") {
      trapFocus(e);
    }
  };

  return ReactDOM.createPortal(
    <div
      className="gooey-model-picker-scrim"
      onMouseDown={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        ref={dialogRef}
        className="gooey-model-picker"
        role="dialog"
        aria-modal="true"
        aria-labelledby="gooey-model-picker-title"
        tabIndex={-1}
        onKeyDown={onDialogKeyDown}
      >
        <div className="gooey-model-picker-header">
          <i className="fa-regular fa-robot" aria-hidden="true" />
          <h2 id="gooey-model-picker-title">Choose a model</h2>
          <button
            type="button"
            className="gooey-model-icon-btn ms-auto"
            aria-label="Close"
            onClick={onCancel}
          >
            <i className="fa-regular fa-xmark" aria-hidden="true" />
          </button>
        </div>

        <div className="gooey-model-picker-body" data-view={narrowView}>
          <div className="gooey-model-list-pane">
            <label className="gooey-model-search">
              <i
                className="fa-regular fa-magnifying-glass"
                aria-hidden="true"
              />
              <input
                ref={searchRef}
                type="search"
                placeholder="Search..."
                aria-label="Search models"
                role="combobox"
                aria-expanded="true"
                aria-controls="gooey-model-list"
                aria-activedescendant={
                  currentListed ? optionId(current.name) : undefined
                }
                autoComplete="off"
                // the dialog is portaled out of the form, but React still bubbles its
                // events to the form's onChange - this keeps typing from posting it
                data-submit-disabled
                value={query}
                onChange={(e) => search(e.target.value)}
                onKeyDown={onSearchKeyDown}
              />
            </label>
            <div className="gooey-model-list-count" aria-live="polite">
              {query
                ? `${matches.length} of ${options.length} models match “${query}”`
                : `${options.length} models`}
            </div>
            <div className="gooey-model-list gooey-thin-scroll">
              {matches.length ? (
                <div id="gooey-model-list" role="listbox" aria-label="Models">
                  {groupByCreator(matches).map(([creator, group]) => (
                    <div key={creator} role="group" aria-label={creator}>
                      <div
                        className="gooey-model-list-overline"
                        aria-hidden="true"
                      >
                        {creator}
                      </div>
                      {group.map((option) => (
                        <ModelRow
                          key={option.name}
                          option={option}
                          selected={option.name === current.name}
                          onSelect={() => {
                            setHighlighted(option.name);
                            setNarrowView("detail");
                          }}
                          onConfirm={() => onConfirm(option, effort)}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="gooey-model-list-empty">
                  <p>No models match “{query}”.</p>
                  <button
                    type="button"
                    className="gooey-model-btn"
                    onClick={() => search("")}
                  >
                    Clear search
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="gooey-model-detail-pane gooey-thin-scroll">
            <button
              type="button"
              className="gooey-model-back"
              onClick={() => setNarrowView("list")}
            >
              <i className="fa-regular fa-arrow-left" aria-hidden="true" /> All
              models
            </button>
            <ModelDetail
              option={current}
              efforts={efforts}
              co2eMethodologyUrl={co2eMethodologyUrl}
              effort={effort}
              onEffortChange={setEffort}
            />
          </div>
        </div>

        <div className="gooey-model-picker-footer">
          <button type="button" className="gooey-model-btn" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="gooey-model-btn gooey-model-btn-primary"
            onClick={() => onConfirm(current, effort)}
          >
            Use model
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function ModelRow({
  option,
  selected,
  onSelect,
  onConfirm,
}: {
  option: ModelPickerOption;
  selected: boolean;
  onSelect: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      id={optionId(option.name)}
      className={clsx(
        "gooey-model-row",
        selected && "gooey-model-row-selected"
      )}
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      onDoubleClick={onConfirm}
    >
      <div className="gooey-model-row-identity">
        <ModelIcon option={option} size={20} />
        <span className="gooey-model-row-label">{option.label}</span>
      </div>
      {(option.price || option.co2e) && (
        <div className="gooey-model-row-metrics">
          {option.price && <Price price={option.price} />}
          {option.co2e && <EcoChip co2e={option.co2e} />}
        </div>
      )}
    </div>
  );
}

function ModelDetail({
  option,
  efforts,
  co2eMethodologyUrl,
  effort,
  onEffortChange,
}: {
  option: ModelPickerOption;
  efforts: ModelPickerProps["efforts"];
  co2eMethodologyUrl: string;
  effort: string | null;
  onEffortChange: (effort: string) => void;
}) {
  return (
    <div className="gooey-model-detail">
      <div className="gooey-model-detail-header">
        <div className="gooey-model-detail-identity">
          <ModelIcon option={option} size={32} />
          <h3>{option.label}</h3>
        </div>
        {option.creator && (
          <div className="gooey-model-detail-maker">
            <span>Made by</span>
            {option.icon_url && (
              <img src={option.icon_url} alt="" width={16} height={16} />
            )}
            <strong>{option.creator}</strong>
          </div>
        )}
      </div>

      {option.reasoning && (
        <section>
          <SectionTitle icon="fa-gear">Settings</SectionTitle>
          <div className="gooey-model-effort">
            <span id="gooey-model-effort-label">Effort</span>
            <div
              className="gooey-model-segmented"
              role="group"
              aria-labelledby="gooey-model-effort-label"
            >
              {Object.entries(efforts).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={value === effort}
                  onClick={() => onEffortChange(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      <section>
        <SectionTitle icon="fa-circle-info">Details</SectionTitle>
        <dl className="gooey-model-details">
          {option.price && (
            <div>
              <dt>Price</dt>
              <dd>
                <Price price={option.price} />
                <span className="gooey-model-details-note">
                  input → output, per 1M tokens
                </span>
              </dd>
            </div>
          )}
          {option.co2e && (
            <div>
              <dt>Est. CO₂e</dt>
              <dd>
                <span className="gooey-model-co2e">
                  <i className="fa-regular fa-leaf" aria-hidden="true" />
                  {option.co2e}
                  <span className="gooey-model-price-unit">/M</span>
                </span>
                <span className="gooey-model-details-note">
                  input → output, per 1M tokens ·{" "}
                  <a href={co2eMethodologyUrl} target="_blank" rel="noreferrer">
                    Learn more
                  </a>
                </span>
              </dd>
            </div>
          )}
          {option.context_window > 0 && (
            <div>
              <dt>Context window</dt>
              <dd>{formatTokens(option.context_window)} tokens</dd>
            </div>
          )}
          <div>
            <dt>Reasoning</dt>
            <dd>
              {option.reasoning
                ? `Supported · ${Object.values(efforts).join(", ")} effort`
                : "Not supported"}
            </dd>
          </div>
          <div>
            <dt>Input</dt>
            <dd>
              <Modalities all={INPUT_MODALITIES} supported={option.inputs} />
            </dd>
          </div>
          <div>
            <dt>Output</dt>
            <dd>
              <Modalities all={OUTPUT_MODALITIES} supported={option.outputs} />
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

function SectionTitle({
  icon,
  children,
}: {
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <h4 className="gooey-model-section-title">
      <i className={`fa-regular ${icon}`} aria-hidden="true" />
      {children}
    </h4>
  );
}

function Modalities({
  all,
  supported,
}: {
  all: Array<[Modality, string, string]>;
  supported: Modality[];
}) {
  return (
    <span className="gooey-model-modalities">
      {all.map(([modality, icon, label]) => {
        const on = supported.includes(modality);
        return (
          <span
            key={modality}
            className={clsx(!on && "gooey-model-modality-off")}
          >
            <i className={`fa-regular ${icon}`} aria-hidden="true" />
            {label}
            {!on && <span className="visually-hidden"> (not supported)</span>}
          </span>
        );
      })}
    </span>
  );
}

function ModelIcon({
  option,
  size,
}: {
  option: ModelPickerOption;
  size: 20 | 32;
}) {
  const className = `gooey-model-icon gooey-model-icon-${size}`;
  if (!option.icon_url) {
    return (
      <i className={`fa-regular fa-robot ${className}`} aria-hidden="true" />
    );
  }
  return (
    <img
      src={option.icon_url}
      alt=""
      width={size}
      height={size}
      className={className}
      loading="lazy"
      decoding="async"
    />
  );
}

function EcoChip({ co2e }: { co2e: string }) {
  return (
    <span className="gooey-model-eco-chip">
      <i className="fa-regular fa-leaf" aria-hidden="true" />
      <span className="visually-hidden">Estimated CO₂e per 1M tokens: </span>
      {co2e}
    </span>
  );
}

function Price({ price }: { price: string }) {
  return (
    <span className="gooey-model-price">
      {price}
      <span className="gooey-model-price-unit">/M</span>
    </span>
  );
}

function filterOptions(options: ModelPickerOption[], query: string) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return options.filter((o) => {
    const haystack = [o.label, o.creator, o.name].join(" ").toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

// The server orders models by creator, so consecutive runs are the groups.
function groupByCreator(options: ModelPickerOption[]) {
  const groups: Array<[string, ModelPickerOption[]]> = [];
  for (const option of options) {
    const creator = option.creator ?? "Other";
    const last = groups[groups.length - 1];
    if (last?.[0] === creator) {
      last[1].push(option);
    } else {
      groups.push([creator, [option]]);
    }
  }
  return groups;
}

function optionId(name: string) {
  return `gooey-model-option-${name}`;
}

function trapFocus(e: KeyboardEvent<HTMLDivElement>) {
  const focusable = Array.from(
    e.currentTarget.querySelectorAll<HTMLElement>("a[href], button, input")
  ).filter((el) => el.offsetParent !== null);
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}
