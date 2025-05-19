import pandas as pd
import json


def load_df(filename: str):
    with open(filename) as f:
        data = json.load(f)
    df = pd.DataFrame.from_records(data)

    # Get rid of columns where all values are identical
    df = df.loc[:, df.nunique() > 1]

    return df

def plot_against_recovery(dfs: list, figsize=(900, 900), df_names=None, markers=None,
                                   title_text=''):
    """
    Plot all columns against 'recovery' for multiple dataframes with:
    - Formatted variable names (underscores to spaces, capitalized)
    - Aligned x-axis ticks across all subplots
    - No subplot titles, using y-axis labels instead
    - X-axis ticks on all plots
    - Different markers for each dataframe

    Parameters:
    - dfs: List of pandas DataFrames, each containing data and a 'recovery' column
    - figsize: tuple (width, height) for the figure
    - df_names: List of names for each dataframe (for legend labels)
    - markers: List of marker symbols to use for each dataframe

    Returns:
    - Plotly figure
    """
    import math
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px

    # Convert single dataframe to list
    if not isinstance(dfs, list):
        dfs = [dfs]

    # Default dataframe names if not provided
    if df_names is None:
        df_names = [f"" for i in range(len(dfs))]

    # Default markers if not provided
    if markers is None:
        marker_options = ['circle', 'square', 'diamond', 'cross', 'x', 'triangle-up', 'triangle-down', 'star']
        markers = [marker_options[i % len(marker_options)] for i in range(len(dfs))]

    # Get columns to plot (excluding recovery) from the first dataframe
    # Assuming all dataframes have the same columns
    cols_to_plot = [col for col in dfs[0].columns if col != 'recovery']

    # Format variable names (underscore to space, capitalize)
    formatted_names = {}
    for col in cols_to_plot:
        # Replace underscores with spaces and capitalize each word
        formatted = ' '.join(word.capitalize() for word in col.split('_'))
        formatted_names[col] = formatted

    # Calculate grid dimensions
    n_plots = len(cols_to_plot)
    n_cols = 3  # 3 plots per row
    n_rows = math.ceil(n_plots / n_cols)

    # Create subplot grid with shared x-axes but no subplot titles
    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        shared_xaxes=True,
        horizontal_spacing=0.08,
        vertical_spacing=0.12
    )

    # Plotly color sequence
    colors = px.colors.qualitative.Plotly

    # Find global x range for all dataframes
    x_min = min(df['recovery'].min() for df in dfs)
    x_max = max(df['recovery'].max() for df in dfs)
    # Add a small buffer (5%) for better visualization
    x_range = [x_min - 0.05 * (x_max - x_min), x_max + 0.05 * (x_max - x_min)]

    # Add traces
    for i, col in enumerate(cols_to_plot):
        row = i // n_cols + 1
        col_pos = i % n_cols + 1
        color_idx = i % len(colors)  # Color based on subplot (variable)

        # Add data for each dataframe
        for df_idx, df in enumerate(dfs):
            marker_symbol = markers[df_idx]

            fig.add_trace(
                go.Scatter(
                    x=df['recovery'],
                    y=df[col],
                    mode='markers',
                    marker=dict(
                        color=colors[color_idx],  # Same color for all dataframes in this subplot
                        size=8,
                        symbol=marker_symbol  # Different symbol for each dataframe
                    ),
                    name=f"{df_names[df_idx]}",
                    showlegend=(i == 0),  # Only show in legend for the first subplot
                    legendgroup=df_names[df_idx]  # Group by dataset for legend
                ),
                row=row, col=col_pos
            )

        # Add formatted y-axis title
        fig.update_yaxes(
            title_text=formatted_names[col],
            showticklabels=True,
            title_standoff=0,  # Reduce space between axis and title
            row=row, col=col_pos
        )

        # Add x-axis ticks to all plots
        fig.update_xaxes(
            title_text="Recovery",
            showticklabels=True,  # Show ticks on all x-axes
            row=row, col=col_pos,
            range=x_range  # Use the same range for all x-axes
        )

    # Update layout
    fig.update_layout(
        height=figsize[1],
        width=figsize[0],
        title_text=title_text,
        margin=dict(l=80, r=30, t=50, b=50),  # Adjust margins for better layout
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    # Add grid lines for better alignment visualization
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='lightgray'
    )

    return fig

if __name__ == '__main__':
    # df = load_df('oaro_with_nf_5_stage.json').drop('aggregate_fixed_operating_cost', axis=1)
    df = load_df('oaro_with_nf_5_stage.json')
    fig = plot_against_recovery(df)
    fig.show()
