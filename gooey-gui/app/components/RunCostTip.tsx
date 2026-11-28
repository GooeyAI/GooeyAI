import Tippy from "@tippyjs/react";

/** An ⓘ that explains the thing beside it. */
export function HelpTip({
  content,
  label,
}: {
  content: React.ReactNode;
  label: string;
}) {
  return (
    <Tip content={content}>
      <i
        role="button"
        tabIndex={0}
        aria-label={label}
        className="fa-regular fa-circle-info gooey-run-cost-help-icon"
      />
    </Tip>
  );
}

/** The run cost modal's tooltip, on hover, focus or tap. The modal body
 * scrolls, so an in-place tooltip would be clipped; this one mounts under
 * <body> like the modal itself. */
export function Tip({
  content,
  disabled,
  children,
}: {
  content: React.ReactNode;
  disabled?: boolean;
  children: React.ReactElement;
}) {
  return (
    <Tippy
      content={<div className="gooey-run-cost-help">{content}</div>}
      disabled={disabled}
      // a tap is a click; hiding on it would close the tip it just opened
      hideOnClick={false}
      placement="top"
      maxWidth={320}
      animation="scale"
      duration={80}
      appendTo={() => document.body}
    >
      {children}
    </Tippy>
  );
}
