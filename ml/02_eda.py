"""
PAIMANA AI - STEP 3 (EXPLORATORY DATA ANALYSIS FOR ML)
======================================================
Project : PAIMANA AI - Predictive Infrastructure Risk Monitoring and Early Warning System
Phase   : ML prototype only.

Reads  : data/processed/paimana_clean.csv   (produced by ml/01_data_audit.py)
Writes : outputs/eda/*.png  +  outputs/eda/02_eda_summary.txt
Original CSV is never touched.

EDA focus (as required): original cost, revised cost, cumulative expenditure,
physical progress, project duration, target vs revised completion date,
cost escalation, schedule revision, expenditure vs physical progress - i.e.
everything that will decide feature design, target design and leakage control.

Run:  python ml/02_eda.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless / reproducible
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN_CSV = ROOT / "data" / "processed" / "paimana_clean.csv"
OUT_DIR = ROOT / "outputs" / "eda"

RANDOM_SEED = 42
REPORT_MONTH = pd.Timestamp("2026-04-01")  # 'report_month' column = April 2026
np.random.seed(RANDOM_SEED)
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 110,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.autolayout": True,
})

DATE_COLS = ["approval_date", "start_date", "target_doc", "revised_doc"]


def _yearmonth(x) -> object:
    """Year*12+month for a Series (dt accessor) or a single Timestamp."""
    if isinstance(x, pd.Series):
        return x.dt.year * 12 + x.dt.month
    return x.year * 12 + x.month


def months_between(a, b) -> pd.Series:
    """Signed whole months from a to b (b - a). Accepts Series or Timestamps."""
    return _yearmonth(b) - _yearmonth(a)


def save(fig: plt.Figure, name: str) -> None:
    path = OUT_DIR / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {path.relative_to(ROOT)}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CLEAN_CSV, parse_dates=DATE_COLS)
    lines: list[str] = []
    add = lines.append

    # derived quantities used ONLY for analysis (labels come later, in 03) ---
    df["cost_escalation"] = (df["revised_cost_crore"] - df["original_cost_crore"]) \
        / df["original_cost_crore"]
    df["schedule_slip_months"] = months_between(df["target_doc"], df["revised_doc"])
    df["duration_months"] = months_between(df["start_date"], df["target_doc"])
    df["expenditure_ratio"] = (df["cumulative_expenditure_crore"]
                               / df["original_cost_crore"])
    df["target_passed"] = df["target_doc"] < REPORT_MONTH

    add("=" * 78)
    add("PAIMANA AI - STEP 3 : EDA SUMMARY (ML-oriented)")
    add(f"rows: {len(df)}   report month: {df['report_month'].iloc[0]}")
    add("=" * 78)

    # ---- 1. cost distributions --------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    ax[0].hist(df["original_cost_crore"], bins=60, color="#3b6ea5", label="original")
    ax[0].hist(df["revised_cost_crore"], bins=60, color="#c1443c", alpha=0.65,
               label="revised")
    ax[0].set_yscale("log")
    ax[0].set_xlabel("cost (₹ crore)"); ax[0].set_ylabel("count (log)")
    ax[0].set_title("Original vs revised project cost"); ax[0].legend()
    esc = df["cost_escalation"].clip(-1, 3)
    ax[1].hist(esc, bins=80, color="#6a994e")
    ax[1].axvline(0, color="black", lw=1.2)
    ax[1].set_xlabel("(revised - original) / original  [clipped to [-1, 3]]")
    ax[1].set_title("Cost escalation ratio")
    save(fig, "03_1_cost_distributions.png")

    add("\n[1] COST")
    add(f"    original_cost  : mean={df['original_cost_crore'].mean():.1f}  "
        f"median={df['original_cost_crore'].median():.1f}  "
        f"max={df['original_cost_crore'].max():.1f} ₹ Cr")
    add(f"    revised_cost   : mean={df['revised_cost_crore'].mean():.1f}  "
        f"median={df['revised_cost_crore'].median():.1f}  "
        f"max={df['revised_cost_crore'].max():.1f} ₹ Cr")
    add(f"    escalated (>0) : {(df['cost_escalation'] > 0).sum()} "
        f"({100 * (df['cost_escalation'] > 0).mean():.1f}%)")
    for thr in (0.01, 0.05, 0.10, 0.25):
        add(f"    escalated >{thr:>5.0%} : {(df['cost_escalation'] > thr).sum()}")

    # ---- 2. escalation threshold bar --------------------------------------
    counts = [(df["cost_escalation"] > t).sum() for t in (0, 0.01, 0.05, 0.10, 0.25)]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar([">0%", ">1%", ">5%", ">10%", ">25%"], counts, color="#3b6ea5")
    for i, c in enumerate(counts):
        ax.text(i, c + 8, str(c), ha="center")
    ax.set_ylabel("# projects with cost escalation")
    ax.set_title("Cost-overrun label: effect of the escalation threshold")
    save(fig, "03_2_cost_threshold_sensitivity.png")

    # ---- 3. expenditure vs physical progress -------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 6))
    sc = ax.scatter(df["expenditure_ratio"] * 100, df["physical_progress_pct"],
                    s=12, alpha=0.45, c=df["cost_escalation"].clip(-0.5, 1),
                    cmap="coolwarm", vmin=-0.5, vmax=1)
    ax.plot([0, 140], [0, 140], "k--", lw=1, label="money spent == progress made")
    ax.set_xlabel("cumulative expenditure as % of ORIGINAL cost")
    ax.set_ylabel("physical progress (%)")
    ax.set_title("Expenditure ratio vs physical progress\n"
                 "(colour = cost escalation, blue<0<red)")
    ax.legend(); fig.colorbar(sc, ax=ax, label="cost escalation ratio")
    save(fig, "03_3_expenditure_vs_progress.png")

    gap = df["expenditure_ratio"] * 100 - df["physical_progress_pct"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.hist(gap.clip(-60, 120), bins=90, color="#7b2cbf")
    ax.axvline(0, color="black", lw=1.2)
    ax.set_xlabel("expenditure% - progress%  (positive = overspending vs progress)")
    ax.set_title("Progress-expenditure gap")
    save(fig, "03_4_progress_expenditure_gap.png")

    add("\n[2] EXPENDITURE vs PHYSICAL PROGRESS")
    add(f"    expenditure_ratio : mean={df['expenditure_ratio'].mean():.3f}  "
        f"median={df['expenditure_ratio'].median():.3f}  "
        f"p95={df['expenditure_ratio'].quantile(0.95):.3f}")
    add(f"    progress%         : mean={df['physical_progress_pct'].mean():.1f}  "
        f"median={df['physical_progress_pct'].median():.1f}")
    add(f"    gap (exp% - prog%): mean={gap.mean():.1f}  median={gap.median():.1f}  "
        f"share gap>10pp={(gap > 10).mean():.1%}")
    add(f"    correlation(expenditure_ratio, physical_progress) = "
        f"{df['expenditure_ratio'].corr(df['physical_progress_pct']):.3f}")

    # ---- 4. durations / schedule ------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    dur = df["duration_months"].clip(0, 240)
    ax[0].hist(dur, bins=60, color="#3b6ea5")
    ax[0].set_xlabel("months from start to target completion")
    ax[0].set_title("Planned project duration")
    age = months_between(df["start_date"], REPORT_MONTH)
    ax[1].hist(age.clip(0, 300), bins=60, color="#6a994e")
    ax[1].set_xlabel("months from start to April 2026")
    ax[1].set_title("Project age at report month")
    save(fig, "03_5_duration_and_age.png")

    add("\n[3] DURATION / AGE")
    add(f"    planned duration (start->target): median={df['duration_months'].median():.0f} "
        f"months, IQR=({df['duration_months'].quantile(.25):.0f}, "
        f"{df['duration_months'].quantile(.75):.0f})")
    add(f"    negative durations (target<start): {(df['duration_months'] < 0).sum()}")
    add(f"    approval->start lag median       : "
        f"{months_between(df['approval_date'], df['start_date']).median():.0f} months")

    # ---- 5. schedule revision ---------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    slip = df["schedule_slip_months"]
    ax[0].hist(slip.dropna().clip(-24, 120), bins=80, color="#c1443c")
    ax[0].axvline(0, color="black", lw=1.2)
    ax[0].set_xlabel("months (revised completion - target completion)")
    ax[0].set_title("Schedule slip where revised date exists")
    known = slip.notna()
    ax[1].bar(["no revised date\n(n=354 est.)", "slip <= 0", "slip > 0"],
              [int((~known).sum()), int((slip <= 0).sum()), int((slip > 0).sum())],
              color=["#999999", "#3b6ea5", "#c1443c"])
    ax[1].set_title("Schedule-revision outcome counts")
    save(fig, "03_6_schedule_slip.png")

    add("\n[4] SCHEDULE REVISION (target vs revised completion date)")
    add(f"    revised_doc missing (assumed no revision) : {int((~known).sum())}")
    add(f"    slip months: median={slip.median():.0f}  p90={slip.quantile(.9):.0f}  "
        f"max={slip.max():.0f}")
    add(f"    projects with slip>0 (time-overrun candidates): {int((slip > 0).sum())} "
        f"({100 * (slip > 0).mean():.1f}% of all rows)")
    add(f"    target completion already passed April 2026 : {int(df['target_passed'].sum())}")
    add(f"    cross: target_passed & slip>0 = "
        f"{int((df['target_passed'] & (slip > 0)).sum())}")

    # ---- 6. escalation / slip by sector groups ------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    top_states = df["state"].value_counts().head(12).index
    esc_by_state = df[df["state"].isin(top_states)].groupby("state").apply(
        lambda g: pd.Series({
            "escalated": (g["cost_escalation"] > 0).mean(),
            "slipped": (g["schedule_slip_months"] > 0).mean(),
            "n": len(g)}), include_groups=False)
    esc_by_state.sort_values("escalated").plot.barh(
        ax=ax[0], color=["#3b6ea5", "#c1443c"], legend=True)
    ax[0].set_title("Escalation / slip rate by state (top 12 by volume)")
    ax[0].set_xlim(0, 1)

    top_agency = df["agency"].value_counts().head(10).index
    esc_by_ag = df[df["agency"].isin(top_agency)].groupby("agency").apply(
        lambda g: pd.Series({
            "escalated": (g["cost_escalation"] > 0).mean(),
            "slipped": (g["schedule_slip_months"] > 0).mean()}),
        include_groups=False)
    esc_by_ag.sort_values("escalated").plot.barh(
        ax=ax[1], color=["#3b6ea5", "#c1443c"], legend=True)
    ax[1].set_title("Escalation / slip rate by agency (top 10 by volume)")
    ax[1].set_xlim(0, 1)
    save(fig, "03_7_rates_by_state_and_agency.png")

    # ---- 7. correlation heatmap -------------------------------------------
    num_cols = ["original_cost_crore", "revised_cost_crore",
                "cumulative_expenditure_crore", "physical_progress_pct",
                "expenditure_ratio", "duration_months",
                "schedule_slip_months", "cost_escalation"]
    corr = df[num_cols].corr()
    fig, ax = plt.subplots(figsize=(8.5, 7))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(num_cols)), [c.replace("_", "\n") for c in num_cols],
                  rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(num_cols)), [c.replace("_", "\n") for c in num_cols],
                  fontsize=8)
    for i in range(len(num_cols)):
        for j in range(len(num_cols)):
            ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center",
                    fontsize=7.5,
                    color="white" if abs(corr.values[i, j]) > 0.6 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Correlation matrix (shows which columns are target-derived)")
    save(fig, "03_8_correlation_matrix.png")

    add("\n[5] CORRELATIONS THAT DRIVE LEAKAGE CONTROL")
    add(f"    corr(revised_cost, original_cost)       = "
        f"{corr.loc['revised_cost_crore', 'original_cost_crore']:.3f}  "
        f"-> revised_cost IS the target source (rejected as feature)")
    add(f"    corr(schedule_slip, cost_escalation)    = "
        f"{corr.loc['schedule_slip_months', 'cost_escalation']:.3f}")
    add(f"    corr(expenditure_ratio, physical_progress) = "
        f"{corr.loc['expenditure_ratio', 'physical_progress_pct']:.3f}")

    # ---- 8. ML target class balance preview --------------------------------
    df["cost_overrun_candidate"] = (df["revised_cost_crore"]
                                     > df["original_cost_crore"]).astype(int)
    df["time_overrun_candidate"] = (df["schedule_slip_months"] > 0).astype(int)
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for i, col in enumerate(["cost_overrun_candidate", "time_overrun_candidate"]):
        vc = df[col].value_counts().sort_index()
        bars = ax[i].bar(["0 (no overrun)", "1 (overrun)"],
                         [vc.get(0, 0), vc.get(1, 0)],
                         color=["#3b6ea5", "#c1443c"])
        ax[i].set_title(col.replace("_", " "))
        for b, v in zip(bars, [vc.get(0, 0), vc.get(1, 0)]):
            ax[i].text(b.get_x() + b.get_width() / 2, v + 15,
                       f"{v}\n({100 * v / len(df):.1f}%)", ha="center", fontsize=9)
    save(fig, "03_9_class_balance_preview.png")

    add("\n[6] CLASS BALANCE PREVIEW (final labels are built in step 03 script)")
    add(f"    cost  overrun candidate : {df['cost_overrun_candidate'].sum()} / {len(df)} "
        f"({100 * df['cost_overrun_candidate'].mean():.1f}%)  -> minority class, "
        f"imbalance ratio {1 / df['cost_overrun_candidate'].mean():.1f}:1")
    add(f"    time  overrun candidate : {df['time_overrun_candidate'].sum()} / {len(df)} "
        f"({100 * df['time_overrun_candidate'].mean():.1f}%)  -> mild imbalance "
        f"{(1 - df['time_overrun_candidate'].mean()) / df['time_overrun_candidate'].mean():.1f}:1")
    add("    => accuracy alone is NOT an acceptable objective for either target.")

    # ---- 9. key ML implications -------------------------------------------
    add("\n[7] IMPLICATIONS FOR MODELLING")
    add("    - expenditure_ratio, physical_progress, gap are strong early-warning signals.")
    add("    - revised_cost and schedule_slip are OUTCOME columns -> features must exclude them.")
    add("    - report_month is constant -> zero variance -> rejected.")
    add("    - state/agency are high-cardinality -> one-hot with min_frequency grouping.")
    add("    - both targets are binary & imbalanced -> optimise recall/PR-AUC, not accuracy.")

    summary = "\n".join(lines)
    print(summary)
    (OUT_DIR / "02_eda_summary.txt").write_text(summary, encoding="utf-8")
    print(f"\nSaved -> {OUT_DIR / '02_eda_summary.txt'}")


if __name__ == "__main__":
    main()


