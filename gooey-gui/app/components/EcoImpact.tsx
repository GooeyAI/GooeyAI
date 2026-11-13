import "./EcoImpact.css";

import type { EcoCostProps, EcoRegionProps } from "@gooey-types/run_cost_props";
import {
  MIX_COLORS,
  MIX_LABELS,
  REASON_TEXT,
  carbonEquivalent,
  countryName,
  energyEquivalent,
  flagEmoji,
  formatGrams,
  formatMl,
  formatWh,
  gridNote,
  waterEquivalent,
} from "./ecoScale";
import { HelpTip, Tip } from "./RunCostTip";

/** The run cost modal's Eco tab: the run's footprint, where its power came
 * from, and how sure the estimate is. */
export function EcoImpact({
  eco,
  methodology_url,
  runs,
}: {
  eco: EcoCostProps;
  methodology_url: string;
  runs: number;
}) {
  const g = eco.co2e_grams * runs;
  const ml = eco.water_ml * runs;
  const mlDataCenter = eco.water_data_center_ml * runs;
  const wh = eco.energy_wh * runs;
  const water = waterEquivalent(ml);
  const energy = energyEquivalent(wh);
  return (
    <div
      role="tabpanel"
      id="gooey-run-cost-panel-eco"
      aria-labelledby="gooey-run-cost-tab-eco"
      className="gooey-run-cost-panel"
    >
      <h3 className="gooey-run-cost-h3">Environmental impact</h3>
      <div className="gooey-eco-tiles">
        <Tile
          icon="fa-solid fa-cloud"
          tone="ink"
          value={formatGrams(g)}
          unit={
            <>
              CO<sub>2</sub>e
            </>
          }
          line1={carbonEquivalent(g)}
        />
        <Tile
          icon="fa-solid fa-droplet"
          tone="blue"
          value={`≈ ${water.value}`}
          unit={water.unit}
          line1="estimated water footprint"
          line2={`${formatMl(mlDataCenter)} cooling · ${formatMl(ml - mlDataCenter)} power plants`}
        />
        <Tile
          icon="fa-solid fa-bolt"
          tone="amber"
          value={energy.value}
          unit={energy.unit}
          line1={energy.caption}
          line2={`${formatWh(wh)} at the meter`}
        />
      </div>

      {eco.region && <RegionBlock region={eco.region} />}

      <div className="gooey-eco-foot">
        {/* ecocost's reason codes, most important first */}
        <Tip
          content={
            <>
              <div className="gooey-eco-reasons-title">
                Why the range is wide
              </div>
              <ul className="gooey-eco-reasons">
                {eco.reasons.map((r) => (
                  <li key={r}>{REASON_TEXT[r] ?? r}</li>
                ))}
              </ul>
            </>
          }
          disabled={!eco.reasons.length}
        >
          <span
            className={`gooey-eco-pill gooey-eco-pill-${eco.confidence}`}
            tabIndex={eco.reasons.length ? 0 : undefined}
          >
            <i className="fa-regular fa-circle-info" />
            <span>{eco.confidence} confidence</span>
          </span>
        </Tip>
        <a
          href={methodology_url}
          target="_blank"
          rel="noreferrer"
          className="gooey-eco-card-link"
        >
          How this is estimated <i className="fa-regular fa-arrow-up-right" />
        </a>
      </div>
    </div>
  );
}

function RegionBlock({ region }: { region: EcoRegionProps }) {
  const flag = flagEmoji(region.country_code);
  const mix = Object.entries(region.mix);
  const color = (source: string) => MIX_COLORS[source] ?? MIX_COLORS.other;
  return (
    <>
      <h3 className="gooey-run-cost-h3">Region and grid mix</h3>
      <div className="gooey-eco-location">
        <div className="gooey-eco-place">
          <div className="gooey-eco-place-name">
            {flag && <span className="gooey-eco-flag">{flag}</span>}
            <span>{countryName(region.country_code)}</span>
            {region.assumption && (
              <HelpTip content={region.assumption} label="What's assumed" />
            )}
          </div>
          <div className="gooey-eco-place-note">
            {gridNote(region.gco2e_per_kwh, region.mix)}
          </div>
          <div className="gooey-eco-place-grid">
            {Math.round(region.gco2e_per_kwh)} gCO<sub>2</sub>e per kWh{" "}
            <span className="gooey-eco-muted">
              ({Math.round(region.gco2e_per_kwh_min)}–
              {Math.round(region.gco2e_per_kwh_max)})
            </span>
          </div>
        </div>
        <div className="gooey-eco-mix">
          <div className="gooey-eco-mix-title">Grid energy mix</div>
          <div className="gooey-eco-mix-bar" aria-hidden="true">
            {mix.map(([k, v]) => (
              <span
                key={k}
                style={{ width: `${v * 100}%`, background: color(k) }}
              />
            ))}
          </div>
          <ul className="gooey-eco-mix-list">
            {mix.map(([k, v]) => (
              <li key={k}>
                <span
                  className="gooey-eco-swatch"
                  style={{ background: color(k) }}
                />
                <span>{MIX_LABELS[k] ?? k}</span>
                <span className="gooey-eco-mix-pct">
                  {Math.round(v * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}

function Tile({
  icon,
  tone,
  value,
  unit,
  line1,
  line2,
}: {
  icon: string;
  tone: "ink" | "blue" | "amber";
  value: string;
  unit: React.ReactNode;
  line1: string;
  line2?: string;
}) {
  return (
    <div className="gooey-eco-tile">
      <i className={`${icon} gooey-eco-tile-icon gooey-eco-tone-${tone}`} />
      <div className="gooey-eco-tile-value">
        {value} <span className="gooey-eco-tile-unit">{unit}</span>
      </div>
      <div className="gooey-eco-tile-line1">{line1}</div>
      {line2 && <div className="gooey-eco-tile-line2">{line2}</div>}
    </div>
  );
}
