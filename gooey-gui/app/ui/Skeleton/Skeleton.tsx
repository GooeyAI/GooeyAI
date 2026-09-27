import "./Skeleton.css";

import clsx from "clsx";
import type { CSSProperties } from "react";

export type SkeletonShape = "line" | "box" | "circle";

export type SkeletonProps = {
  shape?: SkeletonShape;
  width?: number | string;
  height?: number | string;
  /** For `line`: stack this many, the last one short, the way a paragraph ends. */
  lines?: number;
  className?: string;
  style?: CSSProperties;
};

/** A placeholder in the shape of content that is still loading.
 *
 *  Hidden from assistive tech - it is decoration. The region it stands in for should say it
 *  is loading instead (`aria-busy` on the container), once, rather than every bar saying so. */
export function Skeleton({
  shape = "line",
  width,
  height,
  lines = 1,
  className,
  style,
}: SkeletonProps) {
  if (shape === "line" && lines > 1) {
    return (
      <span
        className={clsx("gooey-ui-skeleton-lines", className)}
        style={{ width, ...style }}
        aria-hidden="true"
      >
        {Array.from({ length: lines }, (_, i) => (
          <span
            key={i}
            className="gooey-ui-skeleton gooey-ui-skeleton--line"
            style={{ height, width: i === lines - 1 ? "60%" : undefined }}
          />
        ))}
      </span>
    );
  }
  return (
    <span
      className={clsx(
        "gooey-ui-skeleton",
        `gooey-ui-skeleton--${shape}`,
        className
      )}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  );
}
