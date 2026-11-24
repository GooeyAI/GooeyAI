import { useEffect, useRef, useState } from "react";
import type {
  ArtifactCard,
  ArtifactFilterOption,
  ArtifactGridProps,
  ArtifactLink,
} from "@gooey-types/artifact_props";
import type { CustomComponentProps } from "~/components";

// The thumbnail shows the page as a desktop browser would, scaled down to the card.
const THUMB_WIDTH = 1280;
const THUMB_HEIGHT = 800;

export function ArtifactGrid({
  title,
  subtitle,
  create_menu,
  search_action,
  search_value = "",
  search_hidden = {},
  made_by,
  sort,
  cards,
  empty_message,
}: CustomComponentProps & ArtifactGridProps) {
  return (
    <div className="d-flex flex-column gap-4 py-4 px-1">
      <div className="d-flex align-items-start justify-content-between gap-3 flex-wrap">
        <div>
          <h1 className="mb-1" style={{ fontSize: 32, fontWeight: 500 }}>
            {title}
          </h1>
          <div className="text-muted">{subtitle}</div>
        </div>
        <Dropdown
          align="end"
          trigger={(open, toggle) => (
            <button
              type="button"
              className="btn btn-dark d-inline-flex align-items-center gap-2 fw-semibold"
              style={{ borderRadius: 9 }}
              onClick={toggle}
              aria-expanded={open}
            >
              <i className="fa-regular fa-plus" />
              Create new
              <i className="fa-regular fa-chevron-down small" />
            </button>
          )}
        >
          <MenuLinks links={create_menu} />
        </Dropdown>
      </div>

      <div className="d-flex align-items-center justify-content-end gap-2 flex-wrap">
        <form
          action={search_action}
          method="get"
          className="position-relative"
          style={{ minWidth: 240 }}
        >
          {Object.entries(search_hidden).map(([name, value]) => (
            <input key={name} type="hidden" name={name} value={value} />
          ))}
          <i
            className="fa-regular fa-magnifying-glass text-muted position-absolute"
            style={{ left: 12, top: "50%", transform: "translateY(-50%)" }}
          />
          <input
            type="search"
            name="q"
            defaultValue={search_value}
            placeholder="Search..."
            className="form-control"
            style={{ paddingLeft: 36, borderRadius: 9, height: 38 }}
          />
        </form>
        <FilterDropdown icon="fa-regular fa-filter" options={made_by} />
        <FilterDropdown icon="fa-regular fa-arrow-down-wide-short" options={sort} />
      </div>

      {cards.length ? (
        <div
          className="d-grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
        >
          {cards.map((card) => (
            <Card key={card.href} card={card} />
          ))}
        </div>
      ) : (
        <div className="text-muted py-5 text-center">{empty_message}</div>
      )}
    </div>
  );
}

function Card({ card }: { card: ArtifactCard }) {
  return (
    <div className="border rounded-3 bg-body overflow-hidden d-flex flex-column">
      <a href={card.href} className="d-block border-bottom" aria-label={card.title}>
        <Thumbnail srcdoc={card.thumbnail_srcdoc} title={card.title} />
      </a>
      <div className="d-flex flex-column gap-1 px-3 py-2">
        <div className="d-flex align-items-center justify-content-between gap-2">
          <a
            href={card.href}
            className="fw-semibold text-truncate text-reset text-decoration-none"
          >
            {card.title}
          </a>
          <Dropdown
            align="end"
            trigger={(open, toggle) => (
              <button
                type="button"
                className="btn btn-sm btn-link text-reset p-0 px-1"
                onClick={toggle}
                aria-expanded={open}
                aria-label={`Actions for ${card.title}`}
              >
                <i className="fa-regular fa-ellipsis" />
              </button>
            )}
          >
            <MenuLinks links={card.menu} />
          </Dropdown>
        </div>
        <div className="d-flex align-items-center justify-content-between gap-2 small text-muted">
          <span className="text-truncate">
            <i className="fa-regular fa-globe me-1" aria-hidden="true" />
            {card.meta}
          </span>
          {card.author_initial && (
            <span
              className="rounded-circle border d-inline-flex align-items-center justify-content-center flex-shrink-0"
              style={{ width: 20, height: 20, fontSize: 11 }}
              title={card.author_name}
            >
              {card.author_initial}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function Thumbnail({ srcdoc, title }: { srcdoc?: string | null; title: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.2);
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const observer = new ResizeObserver(([entry]) =>
      setScale(entry.contentRect.width / THUMB_WIDTH)
    );
    observer.observe(box);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={boxRef}
      className="position-relative overflow-hidden bg-body-tertiary"
      style={{ aspectRatio: `${THUMB_WIDTH} / ${THUMB_HEIGHT}` }}
    >
      {srcdoc ? (
        <iframe
          srcDoc={srcdoc}
          title={`Preview of ${title}`}
          tabIndex={-1}
          sandbox="allow-scripts"
          className="border-0 position-absolute top-0 start-0"
          style={{
            width: THUMB_WIDTH,
            height: THUMB_HEIGHT,
            transform: `scale(${scale})`,
            transformOrigin: "0 0",
            pointerEvents: "none",
            background: "#fff",
          }}
        />
      ) : (
        <div className="position-absolute top-50 start-50 translate-middle text-muted">
          <i className="fa-regular fa-globe fa-2x" aria-hidden="true" />
        </div>
      )}
    </div>
  );
}

function FilterDropdown({
  icon,
  options,
}: {
  icon: string;
  options: ArtifactFilterOption[];
}) {
  const active = options.find((option) => option.active) ?? options[0];
  return (
    <Dropdown
      align="end"
      trigger={(open, toggle) => (
        <button
          type="button"
          className="btn btn-outline-secondary text-reset d-inline-flex align-items-center gap-2 fw-semibold"
          style={{ borderRadius: 9, height: 38 }}
          onClick={toggle}
          aria-expanded={open}
        >
          <i className={icon} />
          {active?.label}
          <i className="fa-regular fa-chevron-down small" />
        </button>
      )}
    >
      {options.map((option) => (
        <a
          key={option.href}
          href={option.href}
          className="dropdown-item d-flex align-items-center justify-content-between gap-3 rounded-2 py-2"
        >
          {option.label}
          {option.active && <i className="fa-regular fa-check" />}
        </a>
      ))}
    </Dropdown>
  );
}

function MenuLinks({ links }: { links: ArtifactLink[] }) {
  return (
    <>
      {links.map((link) => (
        <a
          key={link.label}
          href={link.href}
          className={`dropdown-item d-flex align-items-center gap-2 rounded-2 py-2 ${
            link.is_danger ? "text-danger" : ""
          }`}
        >
          <i className={`${link.icon_class} fa-fw`} aria-hidden="true" />
          {link.label}
        </a>
      ))}
    </>
  );
}

function Dropdown({
  trigger,
  children,
  align = "start",
}: {
  trigger: (open: boolean, toggle: () => void) => React.ReactNode;
  children: React.ReactNode;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div ref={ref} className="position-relative">
      {trigger(open, () => setOpen((value) => !value))}
      {open && (
        <div
          className="position-absolute bg-body border rounded-3 shadow-sm p-1 mt-1"
          style={{ zIndex: 20, minWidth: 180, [align === "end" ? "right" : "left"]: 0 }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
