"""
Vẽ boxplot NDCG@20 của 4 mô hình trên CareerBuilder12.
Output: specs/013-thesis-report/report/figures/hinh-37-benchmark-boxplot.png

Chạy:
    cd backend
    python scripts/plot_benchmark.py
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
OUTPUT = (
    Path(__file__).resolve().parent.parent.parent
    / "specs" / "013-thesis-report" / "report" / "figures"
    / "hinh-37-benchmark-boxplot.png"
)

def load_values(path: Path, metric: str = "ndcg@20"):
    with open(path) as f:
        data = json.load(f)
    return data["metrics"][metric]["values"]


def main():
    # HeteroGraphSAGE on CB12
    hsage = load_values(RESULTS_DIR / "careerbuilder" / "summary.json")

    # LightGCN on CB12 (file tên movielens_summary.json nhưng thực ra chứa CB12 data)
    lgcn = load_values(RESULTS_DIR / "lightgcn" / "movielens_summary.json")

    # LSTM on CB12
    lstm = load_values(RESULTS_DIR / "lstm" / "careerbuilder_summary.json")

    # BiLSTM on CB12
    bilstm = load_values(RESULTS_DIR / "bilstm" / "careerbuilder_summary.json")

    labels = ["HeteroGraphSAGE", "BiLSTM", "LSTM", "LightGCN"]
    data = [hsage, bilstm, lstm, lgcn]
    colors = ["#2563eb", "#7c3aed", "#db2777", "#ea580c"]

    fig, ax = plt.subplots(figsize=(8, 5))

    bp = ax.boxplot(
        data,
        labels=labels,
        patch_artist=True,
        widths=0.5,
        showmeans=True,
        meanprops=dict(marker="D", markerfacecolor="white", markeredgecolor="black", markersize=6),
    )

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    for median in bp["medians"]:
        median.set_color("black")
        median.set_linewidth(1.5)

    ax.set_ylabel("NDCG@20", fontsize=13)
    ax.set_title("So sánh NDCG@20 trên CareerBuilder12 (3 seed)", fontsize=14, fontweight="bold")
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.3f"))
    ax.grid(axis="y", alpha=0.3)

    for i, vals in enumerate(data):
        mean_val = sum(vals) / len(vals)
        ax.annotate(
            f"{mean_val:.4f}",
            xy=(i + 1, mean_val),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            fontweight="bold",
            color=colors[i],
        )

    plt.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUTPUT}")
    plt.close()


if __name__ == "__main__":
    main()
