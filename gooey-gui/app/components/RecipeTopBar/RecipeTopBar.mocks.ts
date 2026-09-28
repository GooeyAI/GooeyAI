// Payloads shaped like the ones `BasePageV2._render_top_bar` sends, for stories and tests.
// Typed against the generated contract, so a change to the Python model that these no
// longer satisfy fails `npm run typecheck` here rather than a story silently drifting.
import type {
  EcoLabelProps,
  PageShellConfig,
  RecipeTopBarProps,
  TopBarIntegration,
  TopBarMenuItem,
  WorkspaceView,
} from "@gooey-types/recipe_top_bar_props";

const SUBMIT_INTENT_KEY = "--recipe-submit-intent";

const icons = {
  info: "<i class='fa-regular fa-circle-info'></i>",
  play: '<i class="fa-regular fa-play"></i>',
  edit: '<i class="fa-regular fa-pencil"></i>',
  split: '<i class="fa-regular fa-table-columns"></i>',
  history: '<i class="fa-regular fa-history"></i>',
  fork: '<i class="fa-regular fa-code-fork"></i>',
  delete: '<i class="fa-solid fa-trash-can"></i>',
  share: '<i class="fa-regular fa-share-nodes"></i>',
  whatsapp: '<i class="fa-brands fa-whatsapp"></i>',
  slack: '<i class="fa-brands fa-slack"></i>',
};

/** `get_tab_spec` - what someone who can edit the workflow gets. */
const OWNER_VIEWS: WorkspaceView[] = [
  {
    key: "about",
    label: "About",
    icon_html: icons.info,
    layout: { kind: "split", primary: "about", secondary: "preview" },
    desktop_only: false,
  },
  {
    key: "preview",
    label: "Preview",
    icon_html: icons.play,
    layout: { kind: "single", surface: "preview" },
    desktop_only: false,
  },
  {
    key: "edit",
    label: "Edit",
    icon_html: icons.edit,
    layout: { kind: "single", surface: "editor" },
    desktop_only: false,
  },
  {
    key: "split",
    label: "Split",
    icon_html: icons.split,
    layout: { kind: "split", primary: "editor", secondary: "preview" },
    desktop_only: true,
  },
];

/** `get_viewer_tab_spec` - a visitor's two tabs. */
const VISITOR_VIEWS: WorkspaceView[] = [
  OWNER_VIEWS[0],
  {
    key: "how-it-works",
    label: "How it works",
    icon_html: icons.edit,
    layout: { kind: "split", primary: "editor", secondary: "preview" },
    desktop_only: false,
  },
];

function shellConfig(views: WorkspaceView[]): PageShellConfig {
  return {
    // Its own key per story, so a layout one story stores is not what the next opens on.
    storage_key: `storybook-${views.length}`,
    initial_layout: views[0].layout,
    run_layout: { kind: "split", primary: "editor", secondary: "preview" },
    route_layout: null,
    views,
    narrow_surface: "preview",
    workspace_href: "/copilot/farmer-bot-abc123/",
    workspace_active: true,
    active_run_id: null,
  };
}

const TITLE_MENU: TopBarMenuItem[] = [
  {
    key: "--menu-version-history",
    label: "Versions",
    icon_html: icons.history,
    target: {
      kind: "submit",
      intent: { kind: "menu", item_key: "--menu-version-history" },
    },
    is_danger: false,
  },
  {
    key: "--menu-duplicate",
    label: "Duplicate",
    icon_html: icons.fork,
    target: {
      kind: "submit",
      intent: { kind: "menu", item_key: "--menu-duplicate" },
    },
    is_danger: false,
  },
  {
    key: "--menu-delete",
    label: "Delete",
    icon_html: icons.delete,
    target: {
      kind: "submit",
      intent: { kind: "menu", item_key: "--menu-delete" },
    },
    is_danger: true,
  },
];

const INTEGRATIONS: TopBarIntegration[] = [
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon_html: icons.whatsapp,
    target: { kind: "link", href: "/copilot/farmer-bot-abc123/integrations/" },
    color: "#25D366",
  },
  {
    key: "slack",
    label: "Slack",
    icon_html: icons.slack,
    target: { kind: "link", href: "/copilot/farmer-bot-abc123/integrations/" },
    color: null,
  },
];

/** The figures behind the cost readout's "Run Cost & Environment Impact" modal. */
const ECO_COST: EcoLabelProps = {
  confidence: "medium",
  reasons: ["Token counts are estimated for one of the models."],
  models: [
    {
      model_id: "gpt-4o",
      label: "GPT-4o",
      input_tokens: 1840,
      output_tokens: 420,
    },
  ],
  co2e_grams: 1.9,
  co2e_min: 0.8,
  co2e_max: 4.1,
  energy_wh: 4.6,
  water_ml: 12,
  water_data_center_ml: 3,
  region: {
    country_code: "US",
    assumption: null,
    gco2e_per_kwh: 410,
    gco2e_per_kwh_min: 180,
    gco2e_per_kwh_max: 890,
    mix: { gas: 0.43, coal: 0.16, nuclear: 0.18, wind: 0.1, solar: 0.05 },
  },
  run_cost: "3 Cr",
  run_cost_usd: 0.03,
  methodology_url: "https://gooey.ai/",
  run_by: { name: "Jane Doe", photo_url: null, url: null },
  charged_to: { name: "Gooey.AI", photo_url: null, url: null },
  balance: "1,240 Cr",
  balance_url: "/account/billing/",
};

/** An owner on their own published workflow, with unsaved edits. */
export const ownerTopBar: RecipeTopBarProps = {
  config: shellConfig(OWNER_VIEWS),
  title: "Farmer Bot",
  title_href: "/copilot/farmer-bot-abc123/",
  photo_url: null,
  circle_photo: false,
  author: { label: "Gooey.AI" },
  parent: null,
  title_menu_items: TITLE_MENU,
  integrations: INTEGRATIONS,
  submit_intent_key: SUBMIT_INTENT_KEY,
  publish_label: "Update",
  publish_intent: { kind: "publish" },
  has_unpublished_changes: true,
  api_href: "/copilot/farmer-bot-abc123/api/",
  deploy_href: "/copilot/farmer-bot-abc123/integrations/",
  share: { kind: "manage", intent: { kind: "share" }, icon_html: icons.share },
  view_only: false,
  crumb_label: null,
  builder_panel_key: null,
  builder_storage_key: null,
  builder_new_event: null,
  usage_href: "/copilot/farmer-bot-abc123/usage/",
  usage_active: false,
  run_intent: { kind: "run" },
  cost_label: "3 Cr",
  cost_href: "/account/billing/",
  cost_title: "Each run costs about 3 credits",
  eco_cost: ECO_COST,
};

/** The same bar while a run is in flight - Run turns into Stop. */
export const runningTopBar: RecipeTopBarProps = {
  ...ownerTopBar,
  run_intent: { kind: "stop" },
};

/** A visitor: `is_view_only()`, so nothing to publish, no API/Deploy and two tabs. */
export const visitorTopBar: RecipeTopBarProps = {
  ...ownerTopBar,
  config: {
    ...shellConfig(VISITOR_VIEWS),
    narrow_surface: "editor",
  },
  title_menu_items: [TITLE_MENU[1]],
  integrations: [],
  publish_label: null,
  publish_intent: null,
  has_unpublished_changes: false,
  api_href: null,
  deploy_href: null,
  share: {
    kind: "copy",
    url: "https://gooey.ai/copilot/farmer-bot-abc123/",
    icon_html: icons.share,
  },
  view_only: true,
  usage_href: null,
};

/** A saved run under its published workflow - the crumb names the parent. */
export const savedRunTopBar: RecipeTopBarProps = {
  ...ownerTopBar,
  title: "Run #42",
  parent: { label: "Farmer Bot", href: "/copilot/farmer-bot-abc123/" },
  publish_label: "Save as New",
  has_unpublished_changes: false,
};
