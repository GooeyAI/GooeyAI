import "./Menu.css";

import clsx from "clsx";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactElement,
  type RefObject,
} from "react";
import { ActionRow, type ActionEntry } from "../ActionItem";
import { useDismiss, type DismissReason } from "../hooks/useDismiss";

/** Spread these onto the trigger - they wire up opening, and name the menu it opens. */
export type MenuTriggerProps = {
  ref: RefObject<HTMLButtonElement>;
  "aria-haspopup": "menu";
  "aria-expanded": boolean;
  onClick: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
};

export type MenuProps = {
  items: ActionEntry[];
  trigger: (props: MenuTriggerProps) => ReactElement;
  /** Which edge of the trigger the menu lines up with. */
  align?: "start" | "end";
  /** The menu's accessible name. */
  label?: string;
  /** Pass both to control it; leave both out and it keeps its own state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

type FocusTarget = "first" | "last";

/** A dropdown of actions, opened from a trigger you render.
 *
 *  Keyboard follows the WAI-ARIA menu button pattern: ArrowDown/ArrowUp on the trigger opens
 *  onto the first/last row, arrows and Home/End move, Escape closes and hands focus back to
 *  the trigger, Tab closes and lets focus move on. */
export function Menu({
  items,
  trigger,
  align = "start",
  label,
  open: controlledOpen,
  onOpenChange,
  className,
}: MenuProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const focusOnOpen = useRef<FocusTarget>("first");

  const setOpen = (next: boolean) => {
    if (controlledOpen === undefined) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };

  useDismiss({
    active: open,
    ref: wrapRef,
    onDismiss: (reason: DismissReason) => {
      setOpen(false);
      // Focus was in the menu that is closing; the trigger is what outlives it.
      if (reason === "escape") triggerRef.current?.focus();
    },
  });

  useEffect(() => {
    if (!open || !listRef.current) return;
    const rows = menuRows(listRef.current);
    const row =
      focusOnOpen.current === "last" ? rows[rows.length - 1] : rows[0];
    row?.focus();
  }, [open]);

  const openAt = (target: FocusTarget) => {
    focusOnOpen.current = target;
    setOpen(true);
  };

  return (
    <div ref={wrapRef} className={clsx("gooey-ui-menu-wrap", className)}>
      {trigger({
        ref: triggerRef,
        "aria-haspopup": "menu",
        "aria-expanded": open,
        onClick: () => (open ? setOpen(false) : openAt("first")),
        onKeyDown: (e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            openAt(e.key === "ArrowDown" ? "first" : "last");
          }
        },
      })}
      {open && items.length > 0 && (
        <div
          ref={listRef}
          role="menu"
          aria-label={label}
          className={clsx("gooey-ui-menu", `gooey-ui-menu--${align}`)}
          onKeyDown={(e) => handleMenuKey(e, () => setOpen(false))}
        >
          {items.map((entry) => (
            <ActionRow
              key={entry.key}
              entry={entry}
              block="gooey-ui-menu"
              onDone={() => setOpen(false)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function handleMenuKey(e: KeyboardEvent<HTMLDivElement>, close: () => void) {
  if (e.key === "Tab") {
    close();
    return;
  }
  const rows = menuRows(e.currentTarget);
  if (!rows.length) return;
  const current = rows.indexOf(document.activeElement as HTMLElement);
  const next = nextRowIndex(e.key, current, rows.length);
  if (next === null) return;
  e.preventDefault();
  rows[next].focus();
}

function menuRows(menu: HTMLElement): HTMLElement[] {
  return Array.from(
    menu.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)')
  );
}

/** Where a navigation key moves focus to, wrapping at both ends; null for any other key. */
export function nextRowIndex(
  key: string,
  current: number,
  count: number
): number | null {
  switch (key) {
    case "ArrowDown":
      return (current + 1) % count;
    case "ArrowUp":
      return current <= 0 ? count - 1 : current - 1;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}
