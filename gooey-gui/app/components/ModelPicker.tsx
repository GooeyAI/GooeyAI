import "./ModelPicker.css";

import type {
  ModelPickerOption,
  ModelPickerProps,
  ModelPickerRegion,
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
type Filters = { query: string; region: string | null; zdr: boolean };

const NO_FILTERS: Filters = { query: "", region: null, zdr: false };

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
 * stay staged in the dialog until "Use model" writes them to the form state. A model
 * offered in several regions is saved as the spec of the chosen region.
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
    (Array.isArray(catalog) && findOption(catalog, state[name])) || selected;
  const region = current.regions.find((r) => r.name === state[name]);
  // a region has its own price and CO2e
  const shown = region ?? current;

  const load = () => {
    setCatalog("loading");
    fetchServerAPI<ModelPickerOption[]>(options_url, {
      // the saved spec, which may be a region of `selected`
      selected: state[name] ?? selected.name,
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
  const confirm = (
    model: ModelPickerOption,
    effort: string | null,
    region: string | null
  ) => {
    close();
    const pick = region ?? model.name;
    // effort only applies to reasoning models; others leave it as it was
    const nextEffort = model.reasoning && effort ? effort : state[effort_name];
    if (pick === state[name] && nextEffort === state[effort_name]) {
      return;
    }
    state[name] = pick;
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
        aria-label={`Model: ${current.label}${region ? `, ${region.label}` : ""}. Change model`}
        onClick={openDialog}
      >
        <ModelIcon option={current} size={20} />
        <span className="gooey-model-trigger-label">{current.label}</span>
        {shown.price && (
          <span className="gooey-model-trigger-price">
            <span className="gooey-model-divider" />
            <Price price={shown.price} />
          </span>
        )}
        <span className="gooey-model-trigger-end">
          {region && <RegionChips region={region} />}
          {shown.co2e && <EcoChip co2e={shown.co2e} />}
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
          initialRegion={region?.name ?? null}
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
  initialRegion,
  initialEffort,
  onRetry,
  onCancel,
  onConfirm,
}: {
  catalog: Catalog;
  efforts: ModelPickerProps["efforts"];
  co2eMethodologyUrl: string;
  initialOption: ModelPickerOption;
  initialRegion: string | null;
  initialEffort: string | null;
  onRetry: () => void;
  onCancel: () => void;
  onConfirm: (
    model: ModelPickerOption,
    effort: string | null,
    region: string | null
  ) => void;
}) {
  const [filters, setFilters] = useState(NO_FILTERS);
  const [highlighted, setHighlighted] = useState(initialOption.name);
  const [region, setRegion] = useState(initialRegion);
  const [effort, setEffort] = useState(initialEffort);
  // below 768px the two panes take turns: picking a row opens its detail
  const [narrowView, setNarrowView] = useState<"list" | "detail">("list");
  const dialogRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const loaded = Array.isArray(catalog);
  const options = loaded ? catalog : [];
  const matches = matchOptions(options, filters);
  // while the list loads, the detail pane already shows the trigger's model
  const current = options.find((o) => o.name === highlighted) ?? initialOption;
  const currentListed = matches.includes(current);
  const areas = listAreas(options);
  const matching = [
    filters.query && `“${filters.query}”`,
    filters.region,
    filters.zdr && "ZDR",
  ]
    .filter(Boolean)
    .join(" and ");

  // the saved model keeps its saved region; another starts on the row's region
  const startingRegion = (option: ModelPickerOption, rowFilters: Filters) => {
    if (
      option.name === initialOption.name &&
      !rowFilters.region &&
      !rowFilters.zdr
    ) {
      return initialRegion;
    }
    return rowRegion(option, rowFilters)?.name ?? null;
  };

  const highlight = (option: ModelPickerOption, rowFilters = filters) => {
    setHighlighted(option.name);
    setRegion(startingRegion(option, rowFilters));
  };

  const updateFilters = (patch: Partial<Filters>) => {
    const next = { ...filters, ...patch };
    setFilters(next);
    const nextMatches = matchOptions(options, next);
    const stillListed = nextMatches.find((o) => o.name === highlighted);
    if (!stillListed) {
      if (nextMatches.length) highlight(nextMatches[0], next);
      return;
    }
    // a staged region the filters now rule out gives way to one they allow
    const staged = stillListed.regions.find((r) => r.name === region);
    if (staged && !regionFits(staged, next)) {
      setRegion(rowRegion(stillListed, next)?.name ?? null);
    }
  };

  const confirm = (option: ModelPickerOption) => {
    // a double-clicked row may not be the highlighted one yet
    const pick =
      option.name === current.name ? region : startingRegion(option, filters);
    onConfirm(option, effort, pick);
  };

  useLayoutEffect(() => {
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
    if (!matches.length) return;
    const index = matches.findIndex((o) => o.name === highlighted);
    const next =
      matches[Math.min(matches.length - 1, Math.max(0, index + delta))];
    highlight(next);
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
      // with nothing listed, the highlight is left over from before the search
      if (currentListed) confirm(current);
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
                value={filters.query}
                onChange={(e) => updateFilters({ query: e.target.value })}
                onKeyDown={onSearchKeyDown}
              />
            </label>
            {areas.length > 0 && (
              <RegionFilters
                filters={filters}
                areas={areas}
                onChange={updateFilters}
              />
            )}
            <div className="gooey-model-list-count" aria-live="polite">
              {loaded &&
                (matching
                  ? `${matches.length} of ${options.length} models match ${matching}`
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
                          region={
                            option.name === current.name
                              ? option.regions.find((r) => r.name === region)
                              : rowRegion(option, filters)
                          }
                          selected={option.name === current.name}
                          onSelect={() => {
                            highlight(option);
                            setNarrowView("detail");
                          }}
                          onConfirm={() => confirm(option)}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="gooey-model-list-empty">
                  <p>No models match {matching}.</p>
                  <button
                    type="button"
                    className="gooey-model-btn"
                    onClick={() => {
                      updateFilters(NO_FILTERS);
                      // the button unmounts, which would drop focus out of the dialog
                      searchRef.current?.focus();
                    }}
                  >
                    {filters.region || filters.zdr
                      ? "Clear filters"
                      : "Clear search"}
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
              region={region}
              onRegionChange={setRegion}
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
            onClick={() => confirm(current)}
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

function RegionFilters({
  filters,
  areas,
  onChange,
}: {
  filters: Filters;
  areas: string[];
  onChange: (patch: Partial<Filters>) => void;
}) {
  return (
    <div className="gooey-model-filters">
      <label
        className={clsx(
          "gooey-model-filter",
          filters.region && "gooey-model-filter-on"
        )}
      >
        <select
          aria-label="Region"
          value={filters.region ?? ""}
          // keeps the change from posting the form, as on the search box
          data-submit-disabled
          onChange={(e) => onChange({ region: e.target.value || null })}
        >
          <option value="">Region: Any</option>
          {areas.map((area) => (
            <option key={area} value={area}>
              Region: {area}
            </option>
          ))}
        </select>
        <i className="fa-regular fa-chevron-down" aria-hidden="true" />
      </label>
      <button
        type="button"
        className={clsx(
          "gooey-model-filter",
          filters.zdr && "gooey-model-filter-on"
        )}
        aria-pressed={filters.zdr}
        title="Provider zero data retention"
        onClick={() => onChange({ zdr: !filters.zdr })}
      >
        {filters.zdr && <i className="fa-solid fa-check" aria-hidden="true" />}
        ZDR
      </button>
      {(filters.region || filters.zdr) && (
        <button
          type="button"
          className="gooey-model-filter-clear"
          onClick={() => onChange({ region: null, zdr: false })}
        >
          Clear
        </button>
      )}
    </div>
  );
}

function ModelRow({
  option,
  region,
  selected,
  onSelect,
  onConfirm,
}: {
  option: ModelPickerOption;
  region: ModelPickerRegion | undefined;
  selected: boolean;
  onSelect: () => void;
  onConfirm: () => void;
}) {
  const shown = region ?? option;
  const others = option.regions.filter((r) => r !== region);
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
      {(shown.price || shown.co2e || region) && (
        <div className="gooey-model-row-metrics">
          {shown.price && <Price price={shown.price} />}
          <span className="gooey-model-row-chips">
            {region && <RegionChips region={region} />}
            {shown.co2e && <EcoChip co2e={shown.co2e} />}
          </span>
        </div>
      )}
      {others.length > 0 && (
        <div className="gooey-model-row-hosting">
          + {others.map((r) => r.label).join(", ")}
        </div>
      )}
    </div>
  );
}

function ModelDetail({
  option,
  efforts,
  co2eMethodologyUrl,
  region,
  onRegionChange,
  effort,
  onEffortChange,
}: {
  option: ModelPickerOption;
  efforts: ModelPickerProps["efforts"];
  co2eMethodologyUrl: string;
  region: string | null;
  onRegionChange: (region: string) => void;
  effort: string | null;
  onEffortChange: (effort: string) => void;
}) {
  // with regions, each region's card carries its own price and CO2e
  const regional = option.regions.length > 0;
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

      {regional && (
        <section>
          <SectionTitle icon="fa-cloud">
            Region and hosting · {option.regions.length}{" "}
            {option.regions.length === 1 ? "region" : "regions"}
          </SectionTitle>
          <div className="gooey-model-regions" role="group" aria-label="Region">
            {option.regions.map((r) => (
              <button
                key={r.name}
                type="button"
                className="gooey-model-region"
                aria-pressed={r.name === region}
                onClick={() => onRegionChange(r.name)}
              >
                <span className="gooey-model-region-name">
                  <RegionFlag region={r} />
                  <span>{r.label}</span>
                  {r.name === region && (
                    <i
                      className="fa-solid fa-circle-check"
                      aria-hidden="true"
                    />
                  )}
                </span>
                {r.price && <Price price={r.price} />}
                {r.co2e && (
                  <span className="gooey-model-co2e">
                    <i className="fa-regular fa-leaf" aria-hidden="true" />
                    {r.co2e}
                    <span className="gooey-model-price-unit">CO₂e/M</span>
                  </span>
                )}
                {r.zero_data_retention && (
                  <span className="gooey-model-region-zdr">
                    <i
                      className="fa-regular fa-shield-check"
                      aria-hidden="true"
                    />
                    Provider zero data retention
                  </span>
                )}
              </button>
            ))}
          </div>
          <p className="gooey-model-details-note">
            The region is where the model runs. Prices and CO₂e are input →
            output per 1M tokens.{" "}
            <a href={co2eMethodologyUrl} target="_blank" rel="noreferrer">
              Learn more
            </a>
          </p>
        </section>
      )}

      <section>
        <SectionTitle icon="fa-circle-info">Details</SectionTitle>
        <dl className="gooey-model-details">
          {option.price && !regional && (
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
          {option.co2e && !regional && (
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

function RegionChips({ region }: { region: ModelPickerRegion }) {
  return (
    <>
      <span className="gooey-model-chip" title={region.label}>
        <RegionFlag region={region} />
        <span aria-hidden="true">
          {region.country_code ?? shortLabel(region.label)}
        </span>
        <span className="visually-hidden">Runs in {region.label}</span>
      </span>
      {region.zero_data_retention && (
        <span className="gooey-model-chip" title="Provider zero data retention">
          <i className="fa-regular fa-shield-check" aria-hidden="true" />
          <span aria-hidden="true">ZDR</span>
          <span className="visually-hidden">Provider zero data retention</span>
        </span>
      )}
    </>
  );
}

function RegionFlag({ region }: { region: ModelPickerRegion }) {
  if (!region.country_code) {
    return <i className="fa-regular fa-globe" aria-hidden="true" />;
  }
  // the two regional indicator symbols that render as the country's flag
  const flag = String.fromCodePoint(
    ...[...region.country_code.toUpperCase()].map(
      (c) => 0x1f1a5 + c.charCodeAt(0)
    )
  );
  return <span aria-hidden="true">{flag}</span>;
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

function matchOptions(options: ModelPickerOption[], filters: Filters) {
  const words = filters.query.toLowerCase().split(/\s+/).filter(Boolean);
  return options.filter((o) => {
    const haystack = [o.label, o.creator, o.name].join(" ").toLowerCase();
    if (!words.every((word) => haystack.includes(word))) return false;
    if (!filters.region && !filters.zdr) return true;
    // with both filters on, ZDR must hold in the filtered area
    return o.regions.some((r) => regionFits(r, filters));
  });
}

// the option a spec belongs to: its own, or the one it's a region of
function findOption(options: ModelPickerOption[], specName: string) {
  return options.find(
    (o) => o.name === specName || o.regions.some((r) => r.name === specName)
  );
}

// the Region filter's areas, e.g. "EU", in the order they appear
function listAreas(options: ModelPickerOption[]) {
  const areas = options.flatMap((o) => o.regions.map((r) => r.area));
  return [...new Set(areas)].filter((area): area is string => area !== null);
}

// a row shows the model's default region, unless the filters rule it out
function rowRegion(option: ModelPickerOption, filters: Filters) {
  const lead = option.regions.find((r) => r.name === option.name);
  if (lead && regionFits(lead, filters)) return lead;
  return (
    option.regions.find((r) => regionFits(r, filters)) ??
    lead ??
    option.regions[0]
  );
}

function regionFits(region: ModelPickerRegion, filters: Filters) {
  return (
    (!filters.region || region.area === filters.region) &&
    (!filters.zdr || region.zero_data_retention)
  );
}

function shortLabel(label: string) {
  return label.split(" · ")[0];
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
