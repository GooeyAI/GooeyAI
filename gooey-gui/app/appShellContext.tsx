import { useLocation } from "@remix-run/react";
import type { ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { PageShellConfig } from "@gooey-types/recipe_workspace_props";
import { WIDE_QUERY } from "./components/RecipeWorkspace/breakpoints";
import {
  foldForNarrowViewport,
  type PickedView,
  viewKeyForLayout,
  viewKeyFromHash,
  type WorkspaceLayout,
  workspaceLayoutForView,
  workspaceViews,
} from "./components/RecipeWorkspace/paneState";

export type PanelEntry = {
  open: boolean;
  storageKey: string | null;
  hydrated: boolean;
  commanded: boolean;
};

type AppShellContextValue = {
  panels: Record<string, PanelEntry>;
  setPanel: (key: string, entry: PanelEntry) => void;
  setPanelOpen: (key: string, open: boolean) => void;
  navDrawerOpen: boolean;
  setNavDrawerOpen: (open: boolean) => void;
  pickedView: PickedView | null;
  setPickedView: (picked: PickedView) => void;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

const useHydrationEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function AppShellProvider({ children }: { children: ReactNode }) {
  const [panels, setPanels] = useState<Record<string, PanelEntry>>({});
  const [navDrawerOpen, setNavDrawerOpen] = useState(false);
  const [pickedView, setPickedView] = useState<PickedView | null>(null);
  const panelsRef = useRef(panels);
  panelsRef.current = panels;
  const location = useLocation();
  const page = location.pathname + location.search;
  const lastLocation = useRef<string | null>(null);

  // A post lands the router on the same page with no hash, so the pick is written back.
  // A server redirect - a run, a duplicate - lands on a new url with no hash, where a browser
  // would have kept it, so the pick carries on to it. Any other arrival - a new page,
  // back/forward, an edited hash - adopts the view the url names, after hydration since the
  // server rendered without it.
  useEffect(() => {
    // the key alone is not enough: an entry the browser made for a hash edit has none
    const current = `${location.key}|${page}${location.hash}`;
    const arrived = lastLocation.current !== current;
    lastLocation.current = current;
    const fromUrl = viewKeyFromHash(location.hash);
    if (pickedView?.page === page && (!arrived || !fromUrl)) {
      writeViewHash(pickedView.viewKey);
      return;
    }
    if (!arrived) return;
    let viewKey = fromUrl;
    // the router marks a location it reached by following a redirect
    if (!viewKey && location.state?._isRedirect) {
      viewKey = pickedView?.viewKey ?? null;
    }
    setPickedView(viewKey ? { page, viewKey } : null);
  }, [location, page, pickedView]);

  const setPanel = useCallback((key: string, entry: PanelEntry) => {
    setPanels((current) => ({ ...current, [key]: entry }));
  }, []);

  // The storage key lives in the entry, so the write needs the current one - but a state
  // updater has to stay pure (React runs it twice in StrictMode), so the key is read out
  // through a ref and persisted here rather than inside the updater.
  const setPanelOpen = useCallback((key: string, open: boolean) => {
    const storageKey = panelsRef.current[key]?.storageKey ?? null;
    persistPanelOpen(storageKey, open);
    setPanels((current) => {
      const entry = current[key];
      return {
        ...current,
        [key]: {
          open,
          storageKey: entry?.storageKey ?? storageKey,
          hydrated: entry?.hydrated ?? true,
          commanded: true,
        },
      };
    });
  }, []);

  // Memoised because every workspace pane consumes this: an unmemoised literal made one
  // drawer tap re-render the whole workspace tree. The setters are already stable, so only
  // a real state change invalidates it.
  const value = useMemo(
    () => ({
      panels,
      setPanel,
      setPanelOpen,
      navDrawerOpen,
      setNavDrawerOpen,
      pickedView,
      setPickedView,
    }),
    [panels, setPanel, setPanelOpen, navDrawerOpen, pickedView]
  );

  return (
    <AppShellContext.Provider value={value}>
      {children}
    </AppShellContext.Provider>
  );
}

export function useWorkspaceLayout(config: PageShellConfig) {
  const { pickedView, setPickedView } = useAppShellContext();
  const location = useLocation();
  const page = location.pathname + location.search;
  const [isNarrow, setIsNarrow] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const layout = workspaceLayoutForView(
    config,
    pickedView?.page === page ? pickedView.viewKey : null
  );

  useEffect(() => {
    const wide = window.matchMedia(WIDE_QUERY);
    const sync = () => setIsNarrow(!wide.matches);
    sync();
    setHydrated(true);
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, []);

  // Not a router navigation: that would drop the live run's latest render (it lives in
  // `actionData`, which any navigation clears) and abort a post still in flight.
  const selectLayout = useCallback(
    (next: WorkspaceLayout) => {
      const viewKey = viewKeyForLayout(workspaceViews(config.views), next);
      setPickedView({ page, viewKey });
      writeViewHash(viewKey);
    },
    [config.views, page, setPickedView]
  );

  return {
    layout: foldForNarrowViewport(layout, config.narrow_surface, isNarrow),
    storedLayout: layout,
    hydrated,
    isNarrow,
    selectLayout,
  };
}

export function useAppShellPanel(
  key: string | null | undefined,
  defaultOpen = false,
  storageKey: string | null = null
) {
  const context = useAppShellContext();
  const entry = key ? context.panels[key] : undefined;
  const matchesStorage = entry?.storageKey === storageKey;
  const open = panelOpenForStorage(entry, storageKey, defaultOpen);

  useHydrationEffect(() => {
    if (!key) {
      return;
    }
    const current = context.panels[key];
    if (shouldAdoptPanelCommand(current, storageKey)) {
      persistPanelOpen(storageKey, current.open);
      context.setPanel(key, { ...current, storageKey });
      return;
    }
    if (!shouldRestorePanel(current, storageKey)) {
      return;
    }
    const restored = restorePanelOpen(storageKey, defaultOpen);
    context.setPanel(key, {
      open: restored,
      storageKey,
      hydrated: true,
      commanded: false,
    });
  }, [defaultOpen, key, storageKey]);

  const setOpen = useCallback(
    (nextOpen: boolean) => {
      if (!key) {
        return;
      }
      persistPanelOpen(storageKey, nextOpen);
      context.setPanel(key, {
        open: nextOpen,
        storageKey,
        hydrated: true,
        commanded: true,
      });
    },
    [context, key, storageKey]
  );

  return {
    open,
    hydrated: Boolean(matchesStorage && entry?.hydrated),
    setOpen,
  };
}

export function useNavDrawer() {
  const context = useAppShellContext();
  return {
    open: context.navDrawerOpen,
    setOpen: context.setNavDrawerOpen,
  };
}

export function useAppShellPanelActions() {
  const context = useAppShellContext();
  return { setPanelOpen: context.setPanelOpen };
}

export function panelOpenForStorage(
  entry: PanelEntry | undefined,
  storageKey: string | null,
  defaultOpen: boolean
): boolean {
  if (entry?.storageKey !== storageKey) {
    return defaultOpen;
  }
  return entry.open;
}

export function shouldRestorePanel(
  entry: PanelEntry | undefined,
  storageKey: string | null
): boolean {
  return !entry || entry.storageKey !== storageKey || !entry.commanded;
}

export function shouldAdoptPanelCommand(
  entry: PanelEntry | undefined,
  storageKey: string | null
): entry is PanelEntry {
  return Boolean(entry?.commanded && entry.storageKey === null && storageKey);
}

function useAppShellContext(): AppShellContextValue {
  const context = useContext(AppShellContext);
  if (!context) {
    throw new Error("App shell hooks require AppShellProvider");
  }
  return context;
}

function restorePanelOpen(
  storageKey: string | null,
  defaultOpen: boolean
): boolean {
  if (!storageKey) {
    return defaultOpen;
  }
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored !== null) {
      return stored === "true";
    }
  } catch {
    return defaultOpen;
  }
  return defaultOpen;
}

function persistPanelOpen(storageKey: string | null, open: boolean) {
  if (!storageKey) {
    return;
  }
  try {
    window.sessionStorage.setItem(storageKey, String(open));
  } catch {
    // The in-memory context remains usable when browser storage is unavailable.
  }
}

/** Mirror the view into the address bar, for reloads and shared links. A null key is a
 *  layout no declared view names, which the url cannot address. */
function writeViewHash(viewKey: string | null) {
  const url = new URL(window.location.href);
  const hash = viewKey ? `#${encodeURIComponent(viewKey)}` : "";
  if (url.hash === hash) return;
  url.hash = hash;
  // keep `history.state`: React Router stores its key for this entry there
  window.history.replaceState(window.history.state, "", url);
}
