import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# -----------------------
# Driver color mapping (edit here)
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
# 0) Data (synthetic so it runs from zero)
# -----------------------
np.random.seed(7)
drivers = list(DRIVER_COLORS.keys())
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
            comp = compounds[(compounds.index(comp) + 1) % 3]

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
    "Drivers",
    options=sorted(df["driver"].unique()),
    default=["NOR", "VER", "LEC"],
)
show_pit_markers = st.sidebar.checkbox("Show pit markers", value=True)

plot_df = df[df["driver"].isin(selected_drivers)].copy()


# -----------------------
# Helper: build stint summary
# -----------------------
stint_table = (
    plot_df.groupby(["driver", "stint", "compound"], as_index=False)
    .agg(
        lap_start=("lap", "min"),
        lap_end=("lap", "max"),
        laps=("lap", "count"),
        has_pit=("pit_stop", "max"),
    )
    .sort_values(["driver", "stint"])
)

# Keep color map only for selected drivers (prevents surprises)
color_map = {d: DRIVER_COLORS.get(d, "#AAAAAA") for d in selected_drivers}


# -----------------------
# Layout
# -----------------------
left, right = st.columns([2, 1], gap="large")

with left:
    st.subheader("Lap Time Trace")

    fig = px.line(
        plot_df,
        x="lap",
        y="lap_time_s",
        color="driver",
        hover_data=["stint", "compound", "pit_stop"],
        color_discrete_map=color_map,
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
                fig.add_trace(tr)

    fig.update_layout(
        xaxis_title="Lap",
        yaxis_title="Lap time (s)",
        height=520,
        legend_title_text="Driver",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Stint Timeline (Bars colored by Driver)")

    # Build a horizontal "stint bar" plot (true bar chart style)
    # Each stint becomes a bar segment from lap_start to lap_end.
    stint_fig = go.Figure()
    legend_added = set()

    # y order: keep stable ordering
    y_order = list(sorted(selected_drivers))
    # If you prefer top-to-bottom same as list, you can reverse:
    # y_order = list(reversed(sorted(selected_drivers)))

    for _, r in stint_table.iterrows():
        d = r["driver"]
        if d not in selected_drivers:
            continue

        start = int(r["lap_start"])
        end = int(r["lap_end"])
        width = max(1, end - start + 1)

        hover = (
            f"Driver: {d}<br>"
            f"Stint: {int(r['stint'])}<br>"
            f"Compound: {r['compound']}<br>"
            f"Laps: {width}<br>"
            f"Lap range: {start}–{end}"
        )

        show_legend = d not in legend_added
        if show_legend:
            legend_added.add(d)

        stint_fig.add_trace(
            go.Bar(
                y=[d],
                x=[width],
                base=[start],
                orientation="h",
                name=d,
                showlegend=show_legend,
                marker=dict(color=color_map.get(d, "#AAAAAA")),
                hovertemplate=hover + "<extra></extra>",
            )
        )

    stint_fig.update_layout(
        barmode="stack",
        height=320 + 30 * max(1, len(selected_drivers)),
        xaxis=dict(title="Lap", range=[1, laps_total + 1], dtick=5),
        yaxis=dict(title="", categoryorder="array", categoryarray=y_order),
        legend_title_text="Driver",
        margin=dict(l=40, r=20, t=10, b=40),
    )
    st.plotly_chart(stint_fig, use_container_width=True)

    st.subheader("Stints (Summary Table)")
    st.dataframe(
        stint_table[["driver", "stint", "compound", "lap_start", "lap_end", "laps"]],
        use_container_width=True,
        hide_index=True,
    )

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
        baseline = float(hist["lap_time_s"].mean())
        net = float(pit_loss - tire_gain * window_laps)

        st.metric("Estimated net delta after window (s)", f"{net:.2f}")
        st.caption(
            f"Baseline pace (avg last {len(hist)} clean laps): {baseline:.3f}s. "
            f"Net = pit_loss ({pit_loss:.1f}) - tire_gain ({tire_gain:.1f}) × window ({window_laps})."
        )
        if net <= 0:
            st.success("Toy model suggests the undercut window is favorable (net gain).")
        else:
            st.info("Toy model suggests the undercut may not be worth it (net loss).")

st.caption("MVP uses synthetic data. Next step: replace with real race lap data (CSV).")
