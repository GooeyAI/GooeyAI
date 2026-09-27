import "./Sheet.css";

import clsx from "clsx";
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { ActionRow, type ActionEntry } from "../ActionItem";
import { useDismiss } from "../hooks/useDismiss";

export type SheetProps = {
  open: boolean;
  onDismiss: () => void;
  /** The sheet's accessible name. */
  label: string;
  /** Rows, in the same shape Menu takes - so one list can back both. */
  items?: ActionEntry[];
  /** Anything else, drawn above the rows. */
  children?: ReactNode;
  className?: string;
};

/** A panel that rises from the bottom edge over a scrim, for phone-width menus and pickers.
 *
 *  Not a `<dialog>`: a top-layer dialog paints above everything whatever its z-index, and a
 *  sheet has to stay under the nav drawer. Escape and a tap on the scrim both dismiss it. */
export function Sheet({
  open,
  onDismiss,
  label,
  items = [],
  children,
  className,
}: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useDismiss({ active: open, onDismiss });
  useReturnFocus(open, panelRef);

  if (!open) return null;
  return (
    <div className="gooey-ui-sheet-scrim" onClick={onDismiss}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={clsx("gooey-ui-sheet", className)}
        // without this a tap inside the sheet bubbles to the scrim and closes it
        onClick={(e) => e.stopPropagation()}
      >
        {/* A grab affordance only - Escape and the scrim are what dismiss. */}
        <div className="gooey-ui-sheet-handle" aria-hidden="true" />
        {children}
        {items.length > 0 && (
          <div role="menu" aria-label={label} className="gooey-ui-sheet-items">
            {items.map((entry) => (
              <ActionRow
                key={entry.key}
                entry={entry}
                block="gooey-ui-sheet"
                onDone={onDismiss}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Moves focus into the panel while it is open, and back to wherever it was on close - the
 *  control that opened it, as a rule. */
function useReturnFocus(open: boolean, panelRef: RefObject<HTMLElement>) {
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previous?.focus?.();
  }, [open, panelRef]);
}
