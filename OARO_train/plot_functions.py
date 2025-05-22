import pandas as pd
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import numpy as np


def load_df(filename: str, exclude_keys=None):
    """
    Load JSON data into a pandas DataFrame, excluding columns with single unique values
    and optionally excluding specific keys.

    Args:
        filename: Path to the JSON file
        exclude_keys: Single key or list of keys to exclude from the DataFrame

    Returns:
        DataFrame with filtered columns
    """
    if exclude_keys is None:
        exclude_keys = []
    elif not isinstance(exclude_keys, list):
        exclude_keys = [exclude_keys]

    with open(filename) as f:
        data = json.load(f)

    # Filter out excluded keys from each record
    filtered_data = []
    for record in data:
        filtered_record = {k: v for k, v in record.items() if k not in exclude_keys}
        filtered_data.append(filtered_record)

    df = pd.DataFrame.from_records(filtered_data)

    # Get rid of columns where all values are identical
    df = df.loc[:, df.nunique() > 1]

    return df

def plot_against_recovery(dfs: list, figsize=(900, 900), df_names=None, markers=None,
                                   title_text=''):
    """
    Plot all columns against 'recovery' for multiple dataframes with:
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

        # Add y-axis title
        fig.update_yaxes(
            title_text=col,
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

def plot_sec_at_recovery(dfs, target_recovery, df_names=None, figsize=(800, 500), 
                         title_text='Energy Consumption at Specified Recovery', 
                         tolerance=0.005):
    """
    Create a bar plot comparing SEC (kWh/m³) values at a specific recovery value 
    for different OARO simulations.

    Parameters:
    - dfs: List of pandas DataFrames containing the simulation results
    - target_recovery: Target recovery value to compare SEC values at
    - df_names: List of names for each dataframe (for x-axis labels)
    - figsize: Tuple (width, height) for figure size
    - title_text: Title for the plot
    - tolerance: Tolerance for finding the nearest recovery value

    Returns:
    - Plotly figure
    """
    
    # Convert single dataframe to list
    if not isinstance(dfs, list):
        dfs = [dfs]
        
    # Default dataframe names if not provided
    if df_names is None:
        df_names = [f"Simulation {i+1}" for i in range(len(dfs))]
    
    # Get SEC values at target recovery
    sec_values = []
    
    for df in dfs:
        # Find the row with recovery closest to target_recovery
        idx = (df['recovery'] - target_recovery).abs().idxmin()
        # Check if the closest recovery is within tolerance
        if abs(df.loc[idx, 'recovery'] - target_recovery) <= tolerance:
            sec_values.append(df.loc[idx, 'SEC (kWh/m³)'])
        else:
            # Find the two closest points and interpolate
            df_sorted = df.sort_values('recovery')
            # Find indices where target would be inserted
            insertion_point = np.searchsorted(df_sorted['recovery'], target_recovery)
            
            if insertion_point == 0:
                # Target is before first point
                sec_values.append(df_sorted.iloc[0]['SEC (kWh/m³)'])
            elif insertion_point == len(df_sorted):
                # Target is after last point
                sec_values.append(df_sorted.iloc[-1]['SEC (kWh/m³)'])
            else:
                # Interpolate between two points
                x0 = df_sorted.iloc[insertion_point-1]['recovery']
                x1 = df_sorted.iloc[insertion_point]['recovery']
                y0 = df_sorted.iloc[insertion_point-1]['SEC (kWh/m³)']
                y1 = df_sorted.iloc[insertion_point]['SEC (kWh/m³)']
                
                # Linear interpolation
                sec_interpolated = y0 + (target_recovery - x0) * (y1 - y0) / (x1 - x0)
                sec_values.append(sec_interpolated)
    
    # Create bar plot
    fig = go.Figure()
    
    fig.add_trace(
        go.Bar(
            x=df_names,
            y=sec_values,
            text=[f"{val:.3f}" for val in sec_values],
            textposition='auto',
            marker_color='skyblue'
        )
    )
    
    # Customize layout
    fig.update_layout(
        title=f"{title_text} (Recovery = {target_recovery:.2f})",
        yaxis_title="SEC (kWh/m³)",
        height=figsize[1],
        width=figsize[0],
        yaxis=dict(
            range=[0, max(sec_values) * 1.2],  # Add some space above the bars
        ),
    )
    
    return fig


def plot_sec_barplot(dfs, target_recovery, df_names=None, figsize=(800, 500), 
                     tolerance=0.005,
                     fig=None):
    """
    Create a bar plot comparing SEC (kWh/m³) values at a specific recovery value 
    for different OARO simulations.

    Parameters:
    - dfs: List of pandas DataFrames containing the simulation results
    - target_recovery: Target recovery value to compare SEC values at
    - df_names: List of names for each dataframe (for x-axis labels)
    - figsize: Tuple (width, height) for figure size
    - title_text: Title for the plot
    - tolerance: Tolerance for finding the nearest recovery value

    Returns:
    - Plotly figure
    """
    
    # Convert single dataframe to list
    if not isinstance(dfs, list):
        dfs = [dfs]
        
    # Default dataframe names if not provided
    if df_names is None:
        df_names = [f"{i+2} Stages" for i in range(len(dfs))]
    
    # Get SEC values at target recovery
    sec_values = []
    
    for df in dfs:
        # Find the row with recovery closest to target_recovery
        idx = (df['recovery'] - target_recovery).abs().idxmin()
        # Check if the closest recovery is within tolerance
        if abs(df.loc[idx, 'recovery'] - target_recovery) <= tolerance:
            sec_values.append(df.loc[idx, 'SEC (kWh/m³)'])
        else:
            # Find the two closest points and interpolate
            df_sorted = df.sort_values('recovery')
            # Find indices where target would be inserted
            insertion_point = np.searchsorted(df_sorted['recovery'], target_recovery)
            
            if insertion_point == 0:
                # Target is before first point
                sec_values.append(df_sorted.iloc[0]['SEC (kWh/m³)'])
            elif insertion_point == len(df_sorted):
                # Target is after last point
                sec_values.append(df_sorted.iloc[-1]['SEC (kWh/m³)'])
            else:
                # Interpolate between two points
                x0 = df_sorted.iloc[insertion_point-1]['recovery']
                x1 = df_sorted.iloc[insertion_point]['recovery']
                y0 = df_sorted.iloc[insertion_point-1]['SEC (kWh/m³)']
                y1 = df_sorted.iloc[insertion_point]['SEC (kWh/m³)']
                
                # Linear interpolation
                sec_interpolated = y0 + (target_recovery - x0) * (y1 - y0) / (x1 - x0)
                sec_values.append(sec_interpolated)
        
    fig.add_trace(
        go.Bar(
            x=df_names,
            y=sec_values,
            text=[f"{val:.3f}" for val in sec_values],
            textposition='auto',
        ), row=1, col=1
    )
    
    # Customize layout
    fig.update_layout(
        yaxis_title="SEC (kWh/m³)",
        height=figsize[1],
        width=figsize[0],
        yaxis=dict(
            range=[0, max(sec_values) * 1.2]  # Add some space above the bars
        )
    )
    
    return fig

def plot_stage_area_barplot(filenames, target_recovery=0.15, figsize=(900, 600),
                            tolerance=0.005, fig=None):
    """
    Create a grouped bar plot comparing membrane area for each stage across different configurations.
    
    Parameters:
    - filenames: List of JSON filenames containing the simulation results
    - target_recovery: Target recovery value to compare areas at
    - figsize: Tuple (width, height) for figure size
    - title_text: Title for the plot
    - tolerance: Tolerance for finding the nearest recovery value
    
    Returns:
    - Plotly figure
    """
    # Load data from each file
    all_data = []
    for filename in filenames:
        with open(filename) as f:
            data = json.load(f)
        all_data.append(data)
    
    # Calculate number of stages for each configuration
    stage_counts = []
    for data in all_data:
        # Find a valid record with Stage Area data
        for record in data:
            if 'Stage Area' in record:
                stage_counts.append(len(record['Stage Area']))
                break
    
    # Get configuration labels
    config_labels = [f"{count} Stages" for count in stage_counts]
    
    # Find data points closest to target recovery
    selected_data = []
    for data in all_data:
        # Find record with recovery closest to target
        min_diff = float('inf')
        closest_record = None
        
        for record in data:
            diff = abs(record['recovery'] - target_recovery)
            if diff < min_diff:
                min_diff = diff
                closest_record = record
        
        # Check if within tolerance
        if min_diff <= tolerance:
            selected_data.append(closest_record)
        else:
            # Find the two closest points and interpolate
            # Sort by recovery
            sorted_data = sorted(data, key=lambda x: x['recovery'])
            
            # Find insertion point
            recoveries = [record['recovery'] for record in sorted_data]
            insertion_point = np.searchsorted(recoveries, target_recovery)
            
            if insertion_point == 0:
                selected_data.append(sorted_data[0])
            elif insertion_point == len(sorted_data):
                selected_data.append(sorted_data[-1])
            else:
                # Interpolate between two points
                r0 = sorted_data[insertion_point-1]['recovery']
                r1 = sorted_data[insertion_point]['recovery']
                
                # Create interpolated record
                interp_record = {'recovery': target_recovery, 'Stage Area': {}}
                
                # Interpolate each stage's area
                stage_area0 = sorted_data[insertion_point-1]['Stage Area']
                stage_area1 = sorted_data[insertion_point]['Stage Area']
                
                all_stages = set(list(stage_area0.keys()) + list(stage_area1.keys()))
                
                for stage in all_stages:
                    if stage in stage_area0 and stage in stage_area1:
                        area0 = stage_area0[stage]
                        area1 = stage_area1[stage]
                        interp_area = area0 + (target_recovery - r0) * (area1 - area0) / (r1 - r0)
                        interp_record['Stage Area'][stage] = interp_area
                    elif stage in stage_area0:
                        interp_record['Stage Area'][stage] = stage_area0[stage]
                    else:
                        interp_record['Stage Area'][stage] = stage_area1[stage]
                
                selected_data.append(interp_record)
    
    # Find maximum number of stages across all configurations
    max_stages = max(stage_counts)
    
    # Define a color palette for stages
    colors = ['rgb(31, 119, 180)', 'rgb(255, 127, 14)', 'rgb(44, 160, 44)', 
              'rgb(214, 39, 40)', 'rgb(148, 103, 189)', 'rgb(140, 86, 75)']
    
    # Add bars for each stage in each configuration
    for i, record in enumerate(selected_data):
        stage_area = record['Stage Area']
        
        for stage_num in range(1, max_stages+1):
            stage_key = str(stage_num)
            
            # Skip if this stage doesn't exist in this configuration
            if stage_key not in stage_area:
                continue
                
            area = stage_area[stage_key]
            
            fig.add_trace(go.Bar(
                x=[config_labels[i]],
                y=[area],
                name=f'Stage {stage_key}',
                marker_color=colors[(stage_num-1) % len(colors)],
                text=[f"{area:.1f} m²"],
                textposition='auto',
                legendgroup=f'Stage {stage_key}',
                showlegend=(i == 2),  # Only show in legend for first config
                width=0.3  # Increase bar width
            ), row=1, col=2)
    
    fig.update_xaxes(row=1, col=2)
    fig.update_yaxes(title_text="Membrane Area (m²)", row=1, col=2)
    fig.update_layout(
        height=figsize[1],
        width=figsize[0],
        barmode='group',
        bargap=0.2,        # Reduce gap between bar groups significantly
        bargroupgap=0.2,    # Reduce gap within groups to minimum
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
    )

    return fig

def sec_stage_area_sublots(dfs):
    fig = make_subplots(rows=1, cols=2,)

    fig = plot_sec_barplot(dfs, 0.5, fig=fig)

    fig.data[0].showlegend = False

    names = ['oaro_with_nf_3_stage.json', 'oaro_with_nf_4_stage.json', 'oaro_with_nf_5_stage.json']
    fig = plot_stage_area_barplot(names, fig=fig)

    fig.write_image('oaro_with_nf_barplots.png')

if __name__ == '__main__':

    names = [f'oaro_with_nf_{nstage}_stage.json' for nstage in [3, 4, 5]]
    dfs = [load_df(name, exclude_keys=['Stage Area']) for name in names]
    sec_stage_area_sublots(dfs)
    fig = plot_against_recovery(dfs,
                                df_names=[f'{i} stages' for i in [3, 4, 5]],)

    fig.write_image('oaro_with_nf_stage_recovery.png')



