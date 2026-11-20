import type { CustomComponentProps } from "~/components";
import "./InsufficientCredits.css";

type InsufficientCreditsProps = CustomComponentProps & {
  accountUrl: string;
  isAnonymous: boolean;
  verifiedEmailUserFreeCredits: number;
  rerunKey: string;
  upgradeKey: string;
  buyCreditsKey: string;
  priceLabel: string | null;
  title: string;
  showUpgrade: boolean;
  showRerun: boolean;
  rerunWorkspaceName: string | null;
  rerunWorkspaceBalanceLabel: string | null;
  rerunEvent?: string | null;
};

function SubmitKeyBtn({
  name,
  label,
  variant = "primary",
  onClick,
}: {
  name: string;
  label: string;
  variant?: "primary" | "secondary";
  onClick?: () => void;
}) {
  return (
    <button
      type={onClick ? "button" : "submit"}
      name={name}
      value="1"
      className={`btn btn-theme p-2 m-0 btn-${variant}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function CostLine({
  priceLabel,
  workspaceName,
  workspaceBalanceLabel,
}: {
  priceLabel: string | null;
  workspaceName: string | null;
  workspaceBalanceLabel: string | null;
}) {
  return (
    <div className="insufficient-credits__subtext">
      This run will cost <strong>{priceLabel ?? "more than $0.01"}</strong>{" "}
      and your current <strong>{workspaceName}</strong> balance is{" "}
      <strong>{workspaceBalanceLabel ?? "—"}</strong>.
    </div>
  );
}

function Title({ children }: { children: React.ReactNode }) {
  return (
    <div className="insufficient-credits__title">
      <span className="insufficient-credits__icon">
        <i className="fa-regular fa-coin" />
      </span>
      <span>{children}</span>
    </div>
  );
}

export function InsufficientCredits({
  accountUrl,
  isAnonymous,
  verifiedEmailUserFreeCredits,
  rerunKey,
  upgradeKey,
  buyCreditsKey,
  priceLabel,
  title,
  showUpgrade,
  showRerun,
  rerunWorkspaceName,
  rerunWorkspaceBalanceLabel,
  rerunEvent,
}: InsufficientCreditsProps) {
  if (isAnonymous) {
    return (
      <div className="insufficient-credits" data-submitafterlogin>
        <Title>{title}</Title>
        <div className="insufficient-credits__body">
          Doh!{" "}
          <a href={accountUrl} target="_top">
            Please login
          </a>{" "}
          to run more Gooey.AI workflows.
        </div>
      </div>
    );
  }

  return (
    <div className="insufficient-credits">
      <Title>{title}</Title>
      <CostLine
        priceLabel={priceLabel}
        workspaceName={rerunWorkspaceName}
        workspaceBalanceLabel={rerunWorkspaceBalanceLabel}
      />
      <div className="insufficient-credits__actions">
        {showUpgrade && <SubmitKeyBtn name={upgradeKey} label="Upgrade Team" />}
        {showRerun ? (
          <SubmitKeyBtn
            name={rerunKey}
            label={`Re-run in ${rerunWorkspaceName}`}
            variant={showUpgrade ? "secondary" : "primary"}
            onClick={
              rerunEvent
                ? () => window.dispatchEvent(new CustomEvent(rerunEvent))
                : undefined
            }
          />
        ) : (
          <SubmitKeyBtn
            name={buyCreditsKey}
            label={`Buy ${rerunWorkspaceName} Credits`}
            variant={showUpgrade ? "secondary" : "primary"}
          />
        )}
      </div>
    </div>
  );
}
