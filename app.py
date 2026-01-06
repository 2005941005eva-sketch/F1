import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# -----------------------
# Driver colors (edit here)
# -----------------------
DRIVER_COLORS = {
    "NOR": "#FF8700",  # McLaren orange
    "VER": "#1E41FF",  # Red Bull-ish blue
    "LEC": "#DC0000",  # Ferrari red
    "HAM": "#00D2BE",  # Mercedes teal
    "ALO": "#006F62",  # Aston-ish green
}

# -----------------------
# Page config
# -----------------------
st.set_page_config(page_title="F1 Pit Wall (MVP)", layout="wide")
st.title("F1 Pit Wall Strategy Dashboard — MVP")

# -----------------------
# 0. Data (synthetic so it runs from zero)
# -----------------------
np.random.seed(7)
drivers = ["NOR", "VER", "LEC", "HAM", "ALO"]
laps_total = 58

rows = []
for d in drivers:
    base = 93.0 + np.random.uniform(-0.6, 0.6)
    pit_laps = sorted(np.random.choice(range(10, 45), size=2, replace=False))
    stint = 1
    compounds = ["SOFT", "MEDIUM", "HARD"]
    comp = compounds[np.random.randint(0, 3)]

    for lap in range(1, laps_total + 1):
        # simple degradation + noise
        deg = 0.02 * lap
        noise = np.random.normal(0, 0.25)
        lap_time = base + deg + noise

        pit = lap in pit_laps
        if pit:
            lap_time += 20.5  # pit loss
            stint += 1
            comp = compounds[(compounds.index(comp) + 1) % 3

            ]

        rows.append(
            {
                "race": "SAMPLE_RACE",
                "driver": d,
                "lap": lap,
                "lap_time_s": round(float(lap_time), 3),
                "stint": stint,
                "compound": comp,
                "pit_stop": pit,
            }
        )

df = pd.DataFrame(rows)

# -----------------------
# Sidebar controls
# -----------------------
st.sidebar.header("Controls")
selected_drivers = st.sidebar.multiselect(
    "Drivers", sorted(df["driver"].unique()), default=["NOR", "VER", "LEC"]
)
show_pit_markers = st.sidebar.checkbox("Show pit markers", value=True)

# Keep baseline among selected drivers (for Delta plot)
if not selected_drivers:
    st.warning("Please select at least one driver.")
    st.stop()

baseline_driver = st.sidebar.selectbox(
    "Delta baseline driver",
    options=selected_drivers,
    index=0,
    help="Delta plot will show each driver's lap time minus baseline driver's lap time (same lap).",
)

# Ensure plotting DF includes baseline (safe)
plot_drivers = sorted(set(selected_drivers + [baseline_driver]))
plot_df = df[df["driver"].isin(plot_drivers)].copy()

# color map for plotly
color_map = {d: DRIVER_COLORS.get(d, "#999999") for d in plot_drivers}

# -----------------------
# Layout
# -----------------------
left, right = st.columns([2, 1], gap="large")

# -----------------------
# Right column first (so its values can be used in left plots for shading)
# -----------------------
with right:
    st.subheader("What-if: Undercut (Toy Model)")

    driver_focus = st.selectbox("Focus driver", sorted(df["driver"].unique()), index=0)
    ddf = df[df["driver"] == driver_focus].sort_values("lap")

    target_lap = st.slider("Hypothetical pit lap", 1, int(ddf["lap"].max()), 20)
    last_n = st.slider("Use last N clean laps", 3, 15, 8)
    pit_loss = st.number_input("Assumed pit loss (s)", 10.0, 35.0, 20.5, 0.5)
    tire_gain = st.number_input("Assumed tire gain (s/lap)", 0.0, 3.0, 0.8, 0.1)
    window_laps = st.slider("Evaluation window (laps)", 1, 15, 5)

    hist = ddf[(ddf["lap"] < target_lap) & (~ddf["pit_stop"])].tail(last_n)

    if len(hist) < 3:
        st.warning("Not enough clean laps before the selected pit lap.")
    else:
        baseline = hist["lap_time_s"].mean()
        net = pit_loss - tire_gain * window_laps

        st.metric("Estimated net delta after window (s)", f"{net:.2f}")
        st.caption(
            f"Baseline pace (avg last {len(hist)} clean laps): {baseline:.3f}s. "
            f"Net = pit_loss ({pit_loss:.1f}) - tire_gain ({tire_gain:.1f}) × window ({window_laps})."
        )
        if net <= 0:
            st.success("Toy model suggests the undercut window is favorable (net gain).")
        else:
            st.info("Toy model suggests the undercut may not be worth it (net loss).")

# -----------------------
# Left column (plots + tables)
# -----------------------
with left:
    # ---------
    # B) Lap Time Trace + Pit window shading
    # ---------
    st.subheader("Lap Time Trace")
    fig = px.line(
        plot_df,
        x="lap",
        y="lap_time_s",
        color="driver",
        hover_data=["stint", "compound", "pit_stop"],
        color_discrete_map=color_map,
    )

    # B: Pit window shading (use focus driver controls)
    # Mark the target lap line and the evaluation window [target_lap, target_lap + window_laps]
    x0 = target_lap
    x1 = min(target_lap + window_laps, int(df["lap"].max()))
    fig.add_vline(
        x=x0,
        line_width=2,
        line_dash="dash",
        annotation_text=f"Pit lap (focus): {driver_focus} L{x0}",
        annotation_position="top left",
    )
    fig.add_vrect(
        x0=x0,
        x1=x1,
        opacity=0.12,
        line_width=0,
        annotation_text=f"Eval window: {window_laps} laps",
        annotation_position="top right",
    )

    if show_pit_markers:
        pit_df = plot_df[plot_df["pit_stop"]]
        if not pit_df.empty:
            pit_scatter = px.scatter(
                pit_df,
                x="lap",
                y="lap_time_s",
                color="driver",
                hover_data=["stint", "compound"],
                color_discrete_map=color_map,
            )
            for tr in pit_scatter.data:
                # Make pit markers more visible
                tr.update(marker=dict(size=9, symbol="x"))
                fig.add_trace(tr)

    fig.update_layout(xaxis_title="Lap", yaxis_title="Lap time (s)", height=520)
    st.plotly_chart(fig, use_container_width=True)

    # ---------
    # C) Delta / Gap style plot (relative to baseline driver)
    # ---------
    st.subheader(f"Delta to {baseline_driver} (per lap)")

    # Use "clean" laps (exclude pit_stop spikes) for delta plot
    clean = plot_df.copy()
    clean["lap_time_clean"] = np.where(clean["pit_stop"], np.nan, clean["lap_time_s"])

    pivot = clean.pivot_table(
        index="lap",
        columns="driver",
        values="lap_time_clean",
        aggfunc="mean",
    ).sort_index()

    if baseline_driver not in pivot.columns:
        st.warning("Baseline driver not available in the current selection.")
    else:
        delta = pivot.sub(pivot[baseline_driver], axis=0)

        # Remove baseline line itself (optional, cleaner)
        if baseline_driver in delta.columns:
            delta = delta.drop(columns=[baseline_driver])

        delta_long = (
            delta.reset_index()
            .melt(id_vars="lap", var_name="driver", value_name="delta_s")
            .dropna()
        )

        if delta_long.empty:
            st.info("No clean-lap overlap to compute delta (try toggling drivers).")
        else:
            fig2 = px.line(
                delta_long,
                x="lap",
                y="delta_s",
                color="driver",
                color_discrete_map=color_map,
                hover_data=["delta_s"],
            )
            fig2.add_hline(y=0, line_width=1, line_dash="dot")
            fig2.update_layout(
                xaxis_title="Lap",
                yaxis_title=f"Delta vs {baseline_driver} (s)",
                height=360,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ---------
    # Table
    # ---------
    st.subheader("Stints (Summary Table)")
    stint_table = (
        plot_df.groupby(["driver", "stint", "compound"], as_index=False)
        .agg(lap_start=("lap", "min"), lap_end=("lap", "max"), laps=("lap", "count"))
        .sort_values(["driver", "stint"])
    )
    st.dataframe(stint_table, use_container_width=True, hide_index=True)

st.caption("MVP uses synthetic data. Next step: replace with real race lap data (CSV).")

