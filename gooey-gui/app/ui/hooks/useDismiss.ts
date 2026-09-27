import { useEffect, useRef, type RefObject } from "react";

export type DismissReason = "escape" | "outside";

/** Calls `onDismiss` on Escape, and - when `ref` is given - on a pointer press outside it.
 *
 *  Listens only while `active`, so a closed menu costs nothing. `onDismiss` is read through
 *  a ref: call sites pass inline arrows, and listing one as a dependency would re-bind both
 *  document listeners on every render. */
export function useDismiss({
  active,
  onDismiss,
  ref,
}: {
  active: boolean;
  onDismiss: (reason: DismissReason) => void;
  ref?: RefObject<HTMLElement>;
}) {
  const latest = useRef(onDismiss);
  latest.current = onDismiss;

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") latest.current("escape");
    };
    const onPointer = (e: MouseEvent) => {
      if (ref?.current && !ref.current.contains(e.target as Node)) {
        latest.current("outside");
      }
    };
    document.addEventListener("keydown", onKey);
    if (ref) document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [active, ref]);
}
