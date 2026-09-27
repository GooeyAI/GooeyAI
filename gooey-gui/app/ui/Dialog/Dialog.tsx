import "./Dialog.css";

import clsx from "clsx";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { Button } from "../Button";

export type DialogSize = "sm" | "md" | "lg";

export type DialogProps = {
  open: boolean;
  onDismiss: () => void;
  title: ReactNode;
  children?: ReactNode;
  /** The action row - Buttons, as a rule, primary last. */
  footer?: ReactNode;
  size?: DialogSize;
  /** False for a dialog that must be answered: Escape, the backdrop and the close button
   *  stop dismissing it. */
  dismissible?: boolean;
  className?: string;
};

export type ConfirmDialogProps = Omit<DialogProps, "footer"> & {
  confirmLabel?: string;
  cancelLabel?: string;
  /** For a destructive action - the confirm button turns red. */
  danger?: boolean;
  onConfirm?: () => void;
  /** Makes confirm post the page form with this name/value, like any gooey control. */
  confirmSubmit?: { name: string; value: string };
};

/** A Dialog whose answer is yes or no. */
export function ConfirmDialog({
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  confirmSubmit,
  size = "sm",
  ...dialog
}: ConfirmDialogProps) {
  return (
    <Dialog
      size={size}
      {...dialog}
      footer={
        <>
          <Button variant="outline" onClick={dialog.onDismiss}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "solid"}
            type={confirmSubmit ? "submit" : "button"}
            name={confirmSubmit?.name}
            value={confirmSubmit?.value}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}

/** A modal dialog on the native `<dialog>`: the browser supplies the backdrop, the focus
 *  trap, inert page content and Escape.
 *
 *  It stays where it is rendered in the DOM - only its painting moves to the top layer - so
 *  a submit button inside it still belongs to the page form and posts like any other.
 *  The top layer is also why a Tippy tooltip (appended to <body>) cannot show above it. */
export function Dialog({
  open,
  onDismiss,
  title,
  children,
  footer,
  size = "md",
  dismissible = true,
  className,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const pressStartedOnBackdrop = useRef(false);
  const [titleId] = useState(nextTitleId);
  useModal(ref, open);

  const dismiss = () => {
    if (dismissible) onDismiss();
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={open ? titleId : undefined}
      className={clsx("gooey-ui-dialog", `gooey-ui-dialog--${size}`, className)}
      // Escape. Cancelled so the element never closes itself behind React's back - `open`
      // is the one source of truth, and the owner decides whether to flip it.
      onCancel={(e) => {
        e.preventDefault();
        dismiss();
      }}
      // Chrome lets a second Escape close a dialog even when the first was cancelled, so it
      // can still close itself. Put it back the way `open` says it should be.
      onClose={() => {
        if (!open) return;
        if (dismissible) onDismiss();
        else ref.current?.showModal();
      }}
      // The panel fills the dialog's box, so a press that lands on the dialog itself landed
      // on the backdrop. Both ends are checked: a text selection dragged out of the panel
      // ends on the backdrop too, and that is not a dismiss.
      onMouseDown={(e) => {
        pressStartedOnBackdrop.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (pressStartedOnBackdrop.current && e.target === e.currentTarget) {
          dismiss();
        }
      }}
    >
      {open && (
        <div className="gooey-ui-dialog-panel">
          <div className="gooey-ui-dialog-header">
            <h2 id={titleId} className="gooey-ui-dialog-title">
              {title}
            </h2>
            {dismissible && (
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                aria-label="Close"
                icon={<i className="fa-regular fa-xmark" />}
                onClick={onDismiss}
              />
            )}
          </div>
          {children != null && (
            <div className="gooey-ui-dialog-body">{children}</div>
          )}
          {footer != null && (
            <div className="gooey-ui-dialog-footer">{footer}</div>
          )}
        </div>
      )}
    </dialog>
  );
}

/** Keeps the element's modal state in step with `open`. Through a ref and `showModal()`
 *  because React 17 cannot put a dialog in the top layer by attribute - `open` would show it
 *  non-modal, with no backdrop and no focus trap. */
function useModal(ref: RefObject<HTMLDialogElement>, open: boolean) {
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [ref, open]);
}

let titleCount = 0;

function nextTitleId() {
  titleCount += 1;
  return `gooey-ui-dialog-title-${titleCount}`;
}
