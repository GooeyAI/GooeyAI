import "./Button.css";

import clsx from "clsx";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "solid" | "outline" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

type ButtonBaseProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Defaults to "button", not the browser's "submit": every page here is one big form,
   *  and a bare `<button>` in it posts the whole page when pressed. */
  type?: "button" | "submit" | "reset";
  icon?: ReactNode;
  /** Disables the button and swaps its icon for a spinner. */
  loading?: boolean;
};

/** An icon-only button has no text to be named by, so it must be given a label. */
export type ButtonProps = ButtonBaseProps &
  ({ iconOnly?: false } | { iconOnly: true; "aria-label": string });

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "solid",
      size = "md",
      type = "button",
      icon,
      iconOnly = false,
      loading = false,
      disabled,
      className,
      children,
      ...rest
    },
    ref
  ) {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={buttonClassName({ variant, size, iconOnly, className })}
        {...rest}
      >
        {loading ? (
          <span className="gooey-ui-button-spinner" aria-hidden="true" />
        ) : (
          icon != null && (
            <span className="gooey-ui-button-icon" aria-hidden="true">
              {icon}
            </span>
          )
        )}
        {!iconOnly && children}
      </button>
    );
  }
);

/** The button's classes on their own, for something that has to be another element - a
 *  Remix `<Link>` that should look like a button, say. */
export function buttonClassName({
  variant = "solid",
  size = "md",
  iconOnly = false,
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconOnly?: boolean;
  className?: string;
} = {}) {
  return clsx(
    "gooey-ui-button",
    `gooey-ui-button--${variant}`,
    `gooey-ui-button--${size}`,
    iconOnly && "gooey-ui-button--icon-only",
    className
  );
}
