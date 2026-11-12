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
import { fetchServerAPI } from "~/fetchServerAPI";
import { formatTokens } from "./ecoScale";

type Modality = ModelPickerOption["inputs"][number];
type Catalog = ModelPickerOption[] | "loading" | "failed";

// below this the dialog's two panes take turns
const WIDE = "(min-width: 768px)";

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
  selected,
  options_url,
  co2e_methodology_url,
  state,
  onChange,
}: CustomComponentProps & ModelPickerProps) {
  const [open, setOpen] = useState(false);
  // fetched on first open, then kept for as long as the page is
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // after "Use model", shows the pick until the rerun brings its `selected`
  const current =
    (Array.isArray(catalog) && catalog.find((o) => o.name === state[name])) ||
    selected;
  // a reasoning model's thinking level, shown beside its name
  let effortLabel: string | undefined;
  if (current.reasoning) {
    // null is the provider's default, as the dialog's first segment says
    effortLabel = state[effort_name] ? efforts[state[effort_name]] : "Default";
  }
  let ariaLabel = `Model: ${current.label}`;
  if (effortLabel) ariaLabel += `, ${effortLabel} effort`;

  const load = () => {
    setCatalog("loading");
    fetchServerAPI<ModelPickerOption[]>(options_url, {
      selected: selected.name,
    }).then(setCatalog, () => setCatalog("failed"));
  };
  const openDialog = () => {
    setOpen(true);
    if (catalog === null || catalog === "failed") load();
  };
  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };
  const confirm = (model: ModelPickerOption, effort: string | null) => {
    close();
    // effort only applies to reasoning models, where null is the provider's default
    const nextEffort = model.reasoning ? effort : state[effort_name];
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
        aria-label={`${ariaLabel}. Change model`}
        onClick={openDialog}
      >
        <ModelIcon option={current} size={20} />
        <span className="gooey-model-trigger-label">{current.label}</span>
        {effortLabel && (
          <span className="gooey-model-trigger-effort">{effortLabel}</span>
        )}
        {current.price && (
          <span className="gooey-model-trigger-price">
            <span className="gooey-model-divider" />
            <Price price={current.price} />
          </span>
        )}
        <span className="gooey-model-trigger-end">
          {current.co2e && <EcoChip co2e={current.co2e} />}
          <span className="gooey-model-divider" />
          <i className="fa-regular fa-chevron-down" aria-hidden="true" />
        </span>
      </button>
      {open && (
        <ModelPickerDialog
          catalog={catalog ?? "loading"}
          efforts={efforts}
          co2eMethodologyUrl={co2e_methodology_url}
          initialOption={current}
          initialEffort={state[effort_name] ?? null}
          onRetry={load}
          onCancel={close}
          onConfirm={confirm}
        />
      )}
    </>
  );
}

function ModelPickerDialog({
  catalog,
  efforts,
  co2eMethodologyUrl,
  initialOption,
  initialEffort,
  onRetry,
  onCancel,
  onConfirm,
}: {
  catalog: Catalog;
  efforts: ModelPickerProps["efforts"];
  co2eMethodologyUrl: string;
  initialOption: ModelPickerOption;
  initialEffort: string | null;
  onRetry: () => void;
  onCancel: () => void;
  onConfirm: (model: ModelPickerOption, effort: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(initialOption.name);
  const [effort, setEffort] = useState(initialEffort);
  // below 768px the two panes take turns: picking a row opens its detail
  const [narrowView, setNarrowView] = useState<"list" | "detail">("list");
  const dialogRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const loaded = Array.isArray(catalog);
  const options = loaded ? catalog : [];
  const matches = filterOptions(options, query);
  // the highlight follows the list: a model the search hides gives way to the first match
  const active = loaded
    ? (matches.find((o) => o.name === highlighted) ?? matches[0])
    : initialOption;
  // while the list loads, or matches nothing, the detail pane shows the trigger's model
  const current = active ?? initialOption;

  useLayoutEffect(() => {
    // a phone would raise its keyboard over the list
    if (window.matchMedia(WIDE).matches) {
      searchRef.current?.focus();
    } else {
      dialogRef.current?.focus();
    }
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  // before paint, so the list never shows its top and then jumps to the pick
  useLayoutEffect(() => {
    if (!loaded) return;
    document
      .getElementById(optionId(initialOption.name))
      ?.scrollIntoView({ block: "center" });
  }, [loaded, initialOption.name]);

  const retry = () => {
    // "Try again" unmounts, which would drop focus out of the dialog
    dialogRef.current?.focus();
    onRetry();
  };

  const move = (delta: number) => {
    if (!active) return;
    const index = matches.indexOf(active);
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
      if (!active) return;
      if (window.matchMedia(WIDE).matches) {
        onConfirm(active, effort);
      } else {
        // the detail pane, with the effort, is otherwise out of a keyboard's reach
        setNarrowView("detail");
        dialogRef.current?.focus();
      }
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
                aria-activedescendant={active && optionId(active.name)}
                autoComplete="off"
                // the dialog is portaled out of the form, but React still bubbles its
                // events to the form's onChange - this keeps typing from posting it
                data-submit-disabled
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onSearchKeyDown}
              />
            </label>
            <div className="gooey-model-list-count" aria-live="polite">
              {loaded &&
                (query
                  ? `${matches.length} of ${options.length} models match “${query}”`
                  : `${options.length} models`)}
            </div>
            <div className="gooey-model-list gooey-thin-scroll">
              {!loaded ? (
                <CatalogStatus catalog={catalog} onRetry={retry} />
              ) : matches.length ? (
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
                          selected={option === active}
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
                    onClick={() => {
                      setQuery("");
                      // the button unmounts, which would drop focus out of the dialog
                      searchRef.current?.focus();
                    }}
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
              onClick={() => {
                setNarrowView("list");
                // the detail pane hides, which would drop focus out of the dialog
                dialogRef.current?.focus();
              }}
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
            // with nothing listed, there is no model on screen to use
            disabled={!active}
            onClick={() => active && onConfirm(active, effort)}
          >
            Use model
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function CatalogStatus({
  catalog,
  onRetry,
}: {
  catalog: Exclude<Catalog, ModelPickerOption[]>;
  onRetry: () => void;
}) {
  if (catalog === "loading") {
    return (
      <div className="gooey-model-list-loading" role="status">
        <i className="fa-regular fa-spinner-third fa-spin" aria-hidden="true" />
        Loading models…
      </div>
    );
  }
  return (
    <div className="gooey-model-list-empty" role="alert">
      <p>We couldn’t load the models. Check your connection and try again.</p>
      <button type="button" className="gooey-model-btn" onClick={onRetry}>
        Try again
      </button>
    </div>
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
  onEffortChange: (effort: string | null) => void;
}) {
  // null leaves the effort to the provider, as v1's blank option does
  const effortOptions: Array<[string | null, string]> = [
    [null, "Default"],
    ...Object.entries(efforts),
  ];
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
              {effortOptions.map(([value, label]) => (
                <button
                  key={value ?? ""}
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
                  per 1M output tokens ·{" "}
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
          <div>
            <dt>Reasoning</dt>
            <dd>
              {/* the effort control above already lists the levels */}
              {option.reasoning ? "Supported" : "Not supported"}
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
      <span className="visually-hidden">
        Estimated CO₂e per 1M output tokens:{" "}
      </span>
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
  const active = document.activeElement;
  // below 768px the dialog itself takes focus on open, which sits before `first`
  if (e.shiftKey && (active === first || active === e.currentTarget)) {
    e.preventDefault();
    last?.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first?.focus();
  }
}
