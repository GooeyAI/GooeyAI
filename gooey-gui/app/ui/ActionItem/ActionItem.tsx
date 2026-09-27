import clsx from "clsx";
import type { ReactNode } from "react";
import { Link } from "@remix-run/react";

/** One pressable row. What it does is decided by which of `href`, `submit` and `onSelect`
 *  it carries - the same shape renders as a dropdown row (Menu) or a sheet row (Sheet), so
 *  one list can back both the desktop and the mobile form of a control. */
export type ActionItem = {
  key: string;
  label: ReactNode;
  icon?: ReactNode;
  /** Navigates, through Remix's router. */
  href?: string;
  /** Posts the page form with this button's name/value, like every other gooey control. */
  submit?: { name: string; value: string };
  onSelect?: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** Pinned to the row's end - a badge, a shortcut, a check. */
  trailing?: ReactNode;
  heading?: false;
};

/** A group label, not a control. */
export type ActionHeading = {
  key: string;
  label: ReactNode;
  heading: true;
};

export type ActionEntry = ActionItem | ActionHeading;

/** Renders one entry with `block`-prefixed classes (`<block>-item`, `<block>-icon`, ...),
 *  so Menu and Sheet share behaviour and keep their own look. */
export function ActionRow({
  entry,
  block,
  onDone,
}: {
  entry: ActionEntry;
  block: string;
  onDone: () => void;
}) {
  if (entry.heading) {
    return (
      <div role="presentation" className={`${block}-heading`}>
        {entry.label}
      </div>
    );
  }

  const className = clsx(
    `${block}-item`,
    entry.danger && `${block}-item--danger`
  );
  const inner = (
    <>
      {entry.icon != null && (
        <span className={`${block}-icon`} aria-hidden="true">
          {entry.icon}
        </span>
      )}
      <span className={`${block}-label`}>{entry.label}</span>
      {entry.trailing != null && (
        <span className={`${block}-trailing`}>{entry.trailing}</span>
      )}
    </>
  );

  if (entry.href && !entry.disabled) {
    return (
      <Link
        to={entry.href}
        role="menuitem"
        className={className}
        onClick={() => {
          entry.onSelect?.();
          onDone();
        }}
      >
        {inner}
      </Link>
    );
  }

  return (
    <button
      type={entry.submit ? "submit" : "button"}
      name={entry.submit?.name}
      value={entry.submit?.value}
      role="menuitem"
      disabled={entry.disabled}
      className={className}
      onClick={() => {
        entry.onSelect?.();
        // A submit row stays mounted until the page re-renders: a button taken out of the
        // DOM during its own click loses its form owner, and the browser drops the submit.
        if (!entry.submit) onDone();
      }}
    >
      {inner}
    </button>
  );
}
