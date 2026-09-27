// Payloads shaped like the ones `BasePageV2._render_top_bar` sends, for stories and tests.
// Typed against the generated contract, so a change to the Python model that these no
// longer satisfy fails `npm run typecheck` here rather than a story silently drifting.
import type {
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

/** An owner on their own published workflow, with unsaved edits. */
export const ownerTopBar: RecipeTopBarProps = {
  config: shellConfig(OWNER_VIEWS),
  title: "Farmer Bot",
  title_href: "/copilot/farmer-bot-abc123/",
  logo_image_url: "https://gooey.ai/favicon.ico",
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
  builder_panel_key: null,
  builder_storage_key: null,
  builder_new_event: null,
  builder_photo_url: null,
  usage_href: "/copilot/farmer-bot-abc123/usage/",
  active_document_tab: null,
  run_intent: { kind: "run" },
  cost_label: "3 Cr",
  cost_href: "/account/billing/",
  cost_title: "Each run costs about 3 credits",
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
