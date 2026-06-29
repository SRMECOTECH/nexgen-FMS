"""
Enhanced Waypoint Analysis Module
Analyzes waypoints from GPS data with comprehensive diagrammatic visualizations
Includes line diagrams showing waypoints, distances between them, and time analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px


class WaypointAnalyzer:

    def __init__(self):
        pass
    
    @staticmethod
    def _extract_base_waypoint(waypoint_str):
        """Extract base waypoint name by removing distance suffix like '/0.10 km'"""
        if pd.isna(waypoint_str):
            return waypoint_str
        parts = str(waypoint_str).rsplit('/', 1)
        return parts[0].strip() if len(parts) > 1 else str(waypoint_str).strip()
    
    @staticmethod
    def _extract_speed(status_text):
        """Extract speed from status text like 'Moving 7 km/h'"""
        if pd.isna(status_text):
            return 0
        status_str = str(status_text)
        if 'Moving' in status_str:
            try:
                parts = status_str.split()
                for part in parts:
                    cleaned = part.replace('.', '', 1)
                    if cleaned.isdigit():
                        return float(part)
            except:
                pass
        return 0

    @staticmethod
    def preprocess_waypoint_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess waypoint data for analysis with cumulative metrics
        
        Args:
            df: Raw DataFrame with GPS data
            
        Returns:
            Preprocessed DataFrame with waypoint metrics
        """
        df_processed = df.copy()
        
        # Ensure required columns exist
        required_cols = ['Date Time', 'latitude', 'longitude']
        for col in required_cols:
            if col not in df_processed.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Handle Waypoint 1 and Waypoint 2 columns - extract base names
        if 'Waypoint 1' in df_processed.columns:
            df_processed['Waypoint1'] = df_processed['Waypoint 1'].apply(WaypointAnalyzer._extract_base_waypoint)
            df_processed['Waypoint1_Original'] = df_processed['Waypoint 1']
        elif 'Waypoint1' in df_processed.columns:
            df_processed['Waypoint1'] = df_processed['Waypoint1'].apply(WaypointAnalyzer._extract_base_waypoint)
        
        if 'Waypoint 2' in df_processed.columns:
            df_processed['Waypoint2'] = df_processed['Waypoint 2'].apply(WaypointAnalyzer._extract_base_waypoint)
            df_processed['Waypoint2_Original'] = df_processed['Waypoint 2']
        
        # Parse Distance and Cumulative Distance if present
        if 'Distance' in df_processed.columns:
            df_processed['Distance_km'] = df_processed['Distance'].astype(str).str.replace(' km', '', regex=False).astype(float)
        elif 'Distance_km' not in df_processed.columns:
            df_processed['Distance_km'] = 0
        
        if 'Cumulative Distance' in df_processed.columns:
            df_processed['cumulative_distance_km'] = df_processed['Cumulative Distance'].astype(str).str.replace(' km', '', regex=False).astype(float)
        
        # Extract speed from Status column
        if 'Status' in df_processed.columns and 'Speed_kmh' not in df_processed.columns:
            df_processed['Speed_kmh'] = df_processed['Status'].apply(WaypointAnalyzer._extract_speed)
        elif 'Speed_kmh' not in df_processed.columns:
            df_processed['Speed_kmh'] = 0
        
        # Add waypoint sequence number if not present
        if 'waypoint_sequence' not in df_processed.columns:
            df_processed['waypoint_sequence'] = range(1, len(df_processed) + 1)
        
        # Calculate time differences
        df_processed['time_diff_seconds'] = df_processed['Date Time'].diff().dt.total_seconds().fillna(0)
        df_processed['time_diff_minutes'] = df_processed['time_diff_seconds'] / 60
        df_processed['time_diff_hours'] = df_processed['time_diff_seconds'] / 3600
        
        # Calculate cumulative time
        df_processed['cumulative_time_seconds'] = df_processed['time_diff_seconds'].cumsum()
        df_processed['cumulative_time_minutes'] = df_processed['cumulative_time_seconds'] / 60
        df_processed['cumulative_time_hours'] = df_processed['cumulative_time_seconds'] / 3600
        
        # Calculate distance if not present
        if 'Distance_km' not in df_processed.columns:
            df_processed['Distance_km'] = 0
        
        # Calculate cumulative distance
        df_processed['cumulative_distance_km'] = df_processed['Distance_km'].cumsum()
        
        # Add time-based features
        df_processed['hour'] = df_processed['Date Time'].dt.hour
        df_processed['day_of_week'] = df_processed['Date Time'].dt.dayofweek
        df_processed['date'] = df_processed['Date Time'].dt.date
        
        # Add segment identifier (for grouping consecutive waypoints with gaps > 30 min)
        df_processed['is_new_segment'] = (df_processed['time_diff_minutes'] > 30).astype(int)
        df_processed['segment_id'] = df_processed['is_new_segment'].cumsum()
        
        # Calculate speed between waypoints if Speed_kmh not available
        if 'Speed_kmh' not in df_processed.columns:
            df_processed['Speed_kmh'] = np.where(
                df_processed['time_diff_hours'] > 0,
                df_processed['Distance_km'] / df_processed['time_diff_hours'],
                0
            )
        
        return df_processed
    
    @staticmethod
    def consolidate_waypoints(df: pd.DataFrame) -> pd.DataFrame:
        """
        Consolidate duplicate waypoint entries into unique waypoint visits
        Groups consecutive rows with same Waypoint1 base name
        
        Args:
            df: Preprocessed DataFrame with Waypoint1 column
            
        Returns:
            Consolidated DataFrame with unique waypoint visits
        """
        if 'Waypoint1' not in df.columns:
            return df
        
        # Create waypoint change indicator
        df_consolidated = df.copy()
        df_consolidated['waypoint_changed'] = (df_consolidated['Waypoint1'] != df_consolidated['Waypoint1'].shift(1)).astype(int)
        df_consolidated['visit_id'] = df_consolidated['waypoint_changed'].cumsum()
        
        # Group by visit_id and aggregate
        consolidated = df_consolidated.groupby('visit_id').agg({
            'Waypoint1': 'first',
            'Waypoint2': 'first',
            'Date Time': ['first', 'last'],
            'latitude': 'mean',
            'longitude': 'mean',
            'Distance_km': 'sum',
            'cumulative_distance_km': 'last',
            'Speed_kmh': 'mean',
            'waypoint_sequence': 'first',
            'Status': lambda x: 'Stopped' if (x.str.contains('Stopped', na=False)).any() else 'Moving'
        }).reset_index(drop=True)
        
        # Flatten column names
        consolidated.columns = ['Waypoint_Name', 'Next_Waypoint', 'Arrival_Time', 'Departure_Time',
                               'Latitude', 'Longitude', 'Distance_Covered', 'Cumulative_Distance',
                               'Avg_Speed', 'Sequence', 'Status']
        
        # Calculate time spent at each waypoint
        consolidated['Time_Spent_Minutes'] = (
            (consolidated['Departure_Time'] - consolidated['Arrival_Time']).dt.total_seconds() / 60
        )
        
        # Calculate distance to next waypoint
        consolidated['Distance_To_Next'] = consolidated['Distance_Covered']
        
        # Add visit number for each unique waypoint
        consolidated['Visit_Number'] = consolidated.groupby('Waypoint_Name').cumcount() + 1
        
        return consolidated

    @staticmethod
    def cumulative_preprocessing_multiple_trips(dataframes: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Cumulative preprocessing for multiple trips
        
        Args:
            dataframes: List of DataFrames from different trips
            
        Returns:
            Combined and preprocessed DataFrame
        """
        processed_dfs = []
        
        for idx, df in enumerate(dataframes):
            df_copy = df.copy()
            df_copy['trip_id'] = idx + 1
            df_copy['trip_name'] = f"Trip {idx + 1}"
            
            # Add source identifier if available
            if 'source_file' in df_copy.columns:
                df_copy['trip_name'] = df_copy['source_file'].iloc[0]
            
            processed_dfs.append(WaypointAnalyzer.preprocess_waypoint_data(df_copy))
        
        # Combine all trips
        combined_df = pd.concat(processed_dfs, ignore_index=True)
        combined_df = combined_df.sort_values(['trip_id', 'Date Time'])
        
        return combined_df
    
    @staticmethod
    def create_consolidated_waypoint_diagram(df_consolidated: pd.DataFrame) -> go.Figure:
        """
        Create diagram for consolidated unique waypoints showing transitions between locations
        
        Args:
            df_consolidated: Consolidated DataFrame from consolidate_waypoints()
            
        Returns:
            Plotly figure showing waypoint transitions
        """
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=(
                '🗺️ Waypoint Journey: Location Transitions',
                '⏱️ Time Spent at Each Waypoint',
                '📏 Distance Covered Between Waypoints'
            ),
            vertical_spacing=0.10,
            row_heights=[0.45, 0.275, 0.275]
        )
        
        # Row 1: Journey progression with waypoint names
        fig.add_trace(
            go.Scatter(
                x=list(range(len(df_consolidated))),
                y=df_consolidated['Cumulative_Distance'],
                mode='lines+markers+text',
                name='Journey Path',
                line=dict(color='#2E86DE', width=4),
                marker=dict(size=12, color='#2E86DE', symbol='diamond', line=dict(color='white', width=2)),
                text=df_consolidated['Waypoint_Name'],
                textposition='top center',
                textfont=dict(size=9, color='black'),
                hovertemplate=(
                    '<b>%{text}</b><br>' +
                    'Cumulative Distance: %{y:.2f} km<br>' +
                    'Arrival: %{customdata[0]}<br>' +
                    'Departure: %{customdata[1]}<br>' +
                    'Time Spent: %{customdata[2]:.1f} min<br>' +
                    '<extra></extra>'
                ),
                customdata=np.column_stack((
                    df_consolidated['Arrival_Time'].dt.strftime('%H:%M:%S'),
                    df_consolidated['Departure_Time'].dt.strftime('%H:%M:%S'),
                    df_consolidated['Time_Spent_Minutes']
                ))
            ),
            row=1, col=1
        )
        
        # Add START and END markers
        fig.add_trace(
            go.Scatter(
                x=[0],
                y=[df_consolidated['Cumulative_Distance'].iloc[0]],
                mode='markers+text',
                marker=dict(size=20, color='green', symbol='star', line=dict(color='darkgreen', width=2)),
                text=['🚀 START'],
                textposition='bottom center',
                textfont=dict(size=14, color='green'),
                showlegend=False
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=[len(df_consolidated)-1],
                y=[df_consolidated['Cumulative_Distance'].iloc[-1]],
                mode='markers+text',
                marker=dict(size=20, color='red', symbol='star', line=dict(color='darkred', width=2)),
                text=['🏁 END'],
                textposition='top center',
                textfont=dict(size=14, color='red'),
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Row 2: Time spent at each waypoint
        colors_time = df_consolidated['Time_Spent_Minutes'].values
        fig.add_trace(
            go.Bar(
                x=df_consolidated['Waypoint_Name'],
                y=df_consolidated['Time_Spent_Minutes'],
                name='Time Spent',
                marker=dict(
                    color=colors_time,
                    colorscale='Reds',
                    showscale=True,
                    colorbar=dict(title="Minutes", x=1.12, y=0.5, len=0.25)
                ),
                text=df_consolidated['Time_Spent_Minutes'].round(1),
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Time: %{y:.1f} minutes<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Row 3: Distance covered
        colors_dist = df_consolidated['Distance_To_Next'].values
        fig.add_trace(
            go.Bar(
                x=df_consolidated['Waypoint_Name'],
                y=df_consolidated['Distance_To_Next'],
                name='Distance',
                marker=dict(
                    color=colors_dist,
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="km", x=1.12, y=0.15, len=0.25)
                ),
                text=df_consolidated['Distance_To_Next'].round(2),
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Distance: %{y:.2f} km<extra></extra>'
            ),
            row=3, col=1
        )
        
        # Update layout
        fig.update_xaxes(title_text="Waypoint Sequence", row=1, col=1)
        fig.update_yaxes(title_text="Cumulative Distance (km)", row=1, col=1)
        
        fig.update_xaxes(title_text="Waypoint Location", row=2, col=1, tickangle=-45)
        fig.update_yaxes(title_text="Time (minutes)", row=2, col=1)
        
        fig.update_xaxes(title_text="Waypoint Location", row=3, col=1, tickangle=-45)
        fig.update_yaxes(title_text="Distance (km)", row=3, col=1)
        
        fig.update_layout(
            height=1100,
            title_text=f"<b>📍 Consolidated Waypoint Analysis ({len(df_consolidated)} unique stops)</b>",
            title_font_size=20,
            showlegend=False,
            hovermode='closest'
        )
        
        return fig

    @staticmethod
    def create_waypoint_journey_diagram(df: pd.DataFrame, sample_rate: int = 1) -> go.Figure:
        """
        Create comprehensive journey diagram showing all waypoints with distance and time
        This is the main diagrammatic visualization
        
        Args:
            df: Preprocessed DataFrame
            sample_rate: Show every nth waypoint (1 = show all)
            
        Returns:
            Plotly figure with comprehensive waypoint diagram
        """
        # Sample waypoints if needed for performance
        if len(df) > 500 and sample_rate == 1:
            sample_rate = max(1, len(df) // 500)
        
        df_sample = df.iloc[::sample_rate].copy()
        df_sample = df_sample.reset_index(drop=True)
        
        # Create subplot figure with 4 rows
        fig = make_subplots(
            rows=4, cols=1,
            subplot_titles=(
                '📍 Waypoint Journey Timeline - Distance Progression',
                '📏 Distance Between Consecutive Waypoints', 
                '⏱️ Time Intervals Between Waypoints',
                '🚗 Speed Profile Across Waypoints'
            ),
            vertical_spacing=0.08,
            row_heights=[0.35, 0.22, 0.22, 0.21]
        )
        
        # Row 1: Journey timeline with cumulative distance
        fig.add_trace(
            go.Scatter(
                x=df_sample['waypoint_sequence'],
                y=df_sample['cumulative_distance_km'],
                mode='lines+markers',
                name='Journey Progress',
                line=dict(color='#2E86DE', width=3),
                marker=dict(size=6, color='#2E86DE', symbol='circle'),
                hovertemplate=(
                    '<b>Waypoint #%{x}</b><br>' +
                    'Total Distance: %{y:.2f} km<br>' +
                    'Time: %{customdata[0]}<br>' +
                    'Elapsed Time: %{customdata[1]:.1f} hrs<br>' +
                    '<extra></extra>'
                ),
                customdata=np.column_stack((
                    df_sample['Date Time'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                    df_sample['cumulative_time_hours']
                ))
            ),
            row=1, col=1
        )
        
        # Add START marker
        fig.add_trace(
            go.Scatter(
                x=[df_sample['waypoint_sequence'].iloc[0]],
                y=[df_sample['cumulative_distance_km'].iloc[0]],
                mode='markers+text',
                name='Start',
                marker=dict(size=18, color='green', symbol='star', line=dict(color='darkgreen', width=2)),
                text=['🚀 START'],
                textposition='top center',
                textfont=dict(size=12, color='green'),
                showlegend=False,
                hovertemplate='<b>Journey Start</b><br>Time: %{customdata}<extra></extra>',
                customdata=[df_sample['Date Time'].iloc[0].strftime('%Y-%m-%d %H:%M:%S')]
            ),
            row=1, col=1
        )
        
        # Add END marker
        fig.add_trace(
            go.Scatter(
                x=[df_sample['waypoint_sequence'].iloc[-1]],
                y=[df_sample['cumulative_distance_km'].iloc[-1]],
                mode='markers+text',
                name='End',
                marker=dict(size=18, color='red', symbol='star', line=dict(color='darkred', width=2)),
                text=['🏁 END'],
                textposition='top center',
                textfont=dict(size=12, color='red'),
                showlegend=False,
                hovertemplate='<b>Journey End</b><br>Time: %{customdata}<extra></extra>',
                customdata=[df_sample['Date Time'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S')]
            ),
            row=1, col=1
        )
        
        # Row 2: Distance between consecutive waypoints (bar chart)
        distance_colors = df_sample['Distance_km'].values
        fig.add_trace(
            go.Bar(
                x=df_sample['waypoint_sequence'],
                y=df_sample['Distance_km'],
                name='Segment Distance',
                marker=dict(
                    color=distance_colors,
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(
                        title="Distance<br>(km)",
                        x=1.12,
                        y=0.65,
                        len=0.2
                    ),
                    line=dict(color='rgba(0,0,0,0.3)', width=0.5)
                ),
                hovertemplate=(
                    '<b>Waypoint %{x}</b><br>' +
                    'Distance from previous: %{y:.3f} km<br>' +
                    'Time taken: %{customdata:.1f} min<br>' +
                    '<extra></extra>'
                ),
                customdata=df_sample['time_diff_minutes']
            ),
            row=2, col=1
        )
        
        # Row 3: Time intervals (bar chart)
        time_colors = df_sample['time_diff_minutes'].values
        fig.add_trace(
            go.Bar(
                x=df_sample['waypoint_sequence'],
                y=df_sample['time_diff_minutes'],
                name='Time Interval',
                marker=dict(
                    color=time_colors,
                    colorscale='Plasma',
                    showscale=True,
                    colorbar=dict(
                        title="Time<br>(min)",
                        x=1.12,
                        y=0.35,
                        len=0.2
                    ),
                    line=dict(color='rgba(0,0,0,0.3)', width=0.5)
                ),
                hovertemplate=(
                    '<b>Waypoint %{x}</b><br>' +
                    'Time from previous: %{y:.1f} minutes<br>' +
                    'Distance covered: %{customdata:.3f} km<br>' +
                    '<extra></extra>'
                ),
                customdata=df_sample['Distance_km']
            ),
            row=3, col=1
        )
        
        # Row 4: Speed profile
        speed_colors = df_sample['Speed_kmh'].values
        fig.add_trace(
            go.Scatter(
                x=df_sample['waypoint_sequence'],
                y=df_sample['Speed_kmh'],
                mode='lines+markers',
                name='Speed',
                line=dict(color='#EE5A6F', width=2),
                marker=dict(
                    size=5, 
                    color=speed_colors,
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(
                        title="Speed<br>(km/h)",
                        x=1.12,
                        y=0.1,
                        len=0.2
                    ),
                    line=dict(color='rgba(0,0,0,0.3)', width=0.5)
                ),
                fill='tozeroy',
                fillcolor='rgba(238, 90, 111, 0.2)',
                hovertemplate=(
                    '<b>Waypoint %{x}</b><br>' +
                    'Speed: %{y:.1f} km/h<br>' +
                    'Time: %{customdata}<br>' +
                    '<extra></extra>'
                ),
                customdata=df_sample['Date Time'].dt.strftime('%H:%M:%S')
            ),
            row=4, col=1
        )
        
        # Update axes labels
        fig.update_xaxes(title_text="Waypoint Sequence Number", row=1, col=1)
        fig.update_yaxes(title_text="Cumulative Distance (km)", row=1, col=1)
        
        fig.update_xaxes(title_text="Waypoint Sequence Number", row=2, col=1)
        fig.update_yaxes(title_text="Distance (km)", row=2, col=1)
        
        fig.update_xaxes(title_text="Waypoint Sequence Number", row=3, col=1)
        fig.update_yaxes(title_text="Time (minutes)", row=3, col=1)
        
        fig.update_xaxes(title_text="Waypoint Sequence Number", row=4, col=1)
        fig.update_yaxes(title_text="Speed (km/h)", row=4, col=1)
        
        # Update layout
        fig.update_layout(
            height=1200,
            title_text=f"<b>📍 Complete Waypoint Journey Analysis ({len(df)} waypoints)</b>",
            title_font_size=22,
            title_x=0.5,
            showlegend=False,
            hovermode='x unified',
            plot_bgcolor='rgba(240,240,240,0.5)',
            font=dict(size=11)
        )
        
        # Add grid
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        
        return fig

    @staticmethod
    def create_waypoint_connection_diagram(df: pd.DataFrame, max_points: int = 50) -> go.Figure:
        """
        Create a network-style diagram showing waypoint connections
        
        Args:
            df: Preprocessed DataFrame
            max_points: Maximum number of points to show
            
        Returns:
            Plotly figure
        """
        # Sample waypoints evenly
        if len(df) > max_points:
            indices = np.linspace(0, len(df) - 1, max_points, dtype=int)
            df_sample = df.iloc[indices].copy()
        else:
            df_sample = df.copy()
        
        df_sample = df_sample.reset_index(drop=True)
        
        fig = go.Figure()
        
        # Add connecting line
        fig.add_trace(go.Scatter(
            x=df_sample['cumulative_time_hours'],
            y=df_sample['cumulative_distance_km'],
            mode='lines',
            line=dict(color='rgba(100, 150, 200, 0.4)', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Calculate marker sizes based on time spent (larger = more time)
        marker_sizes = df_sample['time_diff_minutes'].fillna(1)
        marker_sizes = np.clip(marker_sizes * 2, 8, 40)
        
        # Add waypoint markers
        fig.add_trace(go.Scatter(
            x=df_sample['cumulative_time_hours'],
            y=df_sample['cumulative_distance_km'],
            mode='markers+text',
            marker=dict(
                size=marker_sizes,
                color=df_sample.index,
                colorscale='Turbo',
                showscale=True,
                colorbar=dict(
                    title="Waypoint<br>Sequence",
                    x=1.15
                ),
                line=dict(color='white', width=2),
                symbol='circle'
            ),
            text=[f"WP{int(wp)}" for wp in df_sample['waypoint_sequence']],
            textposition='top center',
            textfont=dict(size=9, color='black'),
            name='Waypoints',
            hovertemplate=(
                '<b>Waypoint #%{customdata[0]}</b><br>' +
                'Time: %{customdata[1]}<br>' +
                'Cumulative Time: %{x:.2f} hours<br>' +
                'Cumulative Distance: %{y:.2f} km<br>' +
                'Segment Distance: %{customdata[2]:.3f} km<br>' +
                'Time at waypoint: %{customdata[3]:.1f} min<br>' +
                'Speed: %{customdata[4]:.1f} km/h<br>' +
                '<extra></extra>'
            ),
            customdata=np.column_stack((
                df_sample['waypoint_sequence'],
                df_sample['Date Time'].dt.strftime('%H:%M:%S'),
                df_sample['Distance_km'],
                df_sample['time_diff_minutes'],
                df_sample['Speed_kmh']
            ))
        ))
        
        # Add START marker
        fig.add_trace(go.Scatter(
            x=[df_sample['cumulative_time_hours'].iloc[0]],
            y=[df_sample['cumulative_distance_km'].iloc[0]],
            mode='markers+text',
            marker=dict(size=25, color='green', symbol='star', line=dict(color='darkgreen', width=2)),
            text=['START'],
            textposition='bottom center',
            textfont=dict(size=14, color='green', family='Arial Black'),
            name='Start Point',
            showlegend=True,
            hovertemplate='<b>Journey Start</b><br>%{customdata}<extra></extra>',
            customdata=[df_sample['Date Time'].iloc[0].strftime('%Y-%m-%d %H:%M:%S')]
        ))
        
        # Add END marker
        fig.add_trace(go.Scatter(
            x=[df_sample['cumulative_time_hours'].iloc[-1]],
            y=[df_sample['cumulative_distance_km'].iloc[-1]],
            mode='markers+text',
            marker=dict(size=25, color='red', symbol='star', line=dict(color='darkred', width=2)),
            text=['END'],
            textposition='top center',
            textfont=dict(size=14, color='red', family='Arial Black'),
            name='End Point',
            showlegend=True,
            hovertemplate='<b>Journey End</b><br>%{customdata}<extra></extra>',
            customdata=[df_sample['Date Time'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S')]
        ))
        
        # Add annotations for key statistics
        total_distance = df_sample['cumulative_distance_km'].iloc[-1]
        total_time = df_sample['cumulative_time_hours'].iloc[-1]
        avg_speed = total_distance / total_time if total_time > 0 else 0
        
        annotation_text = (
            f"<b>Journey Summary</b><br>" +
            f"Distance: {total_distance:.2f} km<br>" +
            f"Duration: {total_time:.2f} hrs<br>" +
            f"Avg Speed: {avg_speed:.1f} km/h<br>" +
            f"Waypoints: {len(df)}"
        )
        
        fig.add_annotation(
            x=0.02,
            y=0.98,
            xref='paper',
            yref='paper',
            text=annotation_text,
            showarrow=False,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='black',
            borderwidth=1,
            borderpad=10,
            font=dict(size=11),
            align='left',
            xanchor='left',
            yanchor='top'
        )
        
        fig.update_layout(
            title='<b>🔗 Waypoint Network Diagram: Distance vs Time Progression</b>',
            title_font_size=18,
            xaxis_title='Cumulative Time (hours)',
            yaxis_title='Cumulative Distance (km)',
            hovermode='closest',
            height=700,
            showlegend=True,
            plot_bgcolor='rgba(245,245,245,1)',
            legend=dict(
                x=0.02,
                y=0.15,
                bgcolor='rgba(255,255,255,0.9)',
                bordercolor='black',
                borderwidth=1
            )
        )
        
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.5)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.5)')
        
        return fig

    @staticmethod
    def create_waypoint_segment_analysis(df: pd.DataFrame) -> go.Figure:
        """
        Analyze and visualize journey segments
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            Plotly figure with segment analysis
        """
        # Group by segments
        segment_stats = df.groupby('segment_id').agg({
            'Distance_km': 'sum',
            'time_diff_minutes': 'sum',
            'Speed_kmh': 'mean',
            'waypoint_sequence': ['min', 'max', 'count'],
            'Date Time': ['min', 'max']
        }).reset_index()
        
        segment_stats.columns = ['segment_id', 'total_distance', 'total_time_min', 'avg_speed', 
                                 'start_wp', 'end_wp', 'waypoint_count', 'start_time', 'end_time']
        
        # Calculate efficiency metrics
        segment_stats['total_time_hours'] = segment_stats['total_time_min'] / 60
        segment_stats['calculated_speed'] = np.where(
            segment_stats['total_time_hours'] > 0,
            segment_stats['total_distance'] / segment_stats['total_time_hours'],
            0
        )
        segment_stats['segment_label'] = [
            f"Seg {i+1}: WP{int(start)}-{int(end)}" 
            for i, (start, end) in enumerate(zip(segment_stats['start_wp'], segment_stats['end_wp']))
        ]
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Distance per Segment',
                'Duration per Segment',
                'Average Speed per Segment',
                'Waypoints per Segment'
            ),
            specs=[[{'type': 'bar'}, {'type': 'bar'}],
                   [{'type': 'bar'}, {'type': 'bar'}]]
        )
        
        # Distance per segment
        fig.add_trace(
            go.Bar(
                x=segment_stats['segment_label'],
                y=segment_stats['total_distance'],
                marker_color='lightblue',
                text=segment_stats['total_distance'].round(2),
                textposition='outside',
                name='Distance',
                hovertemplate='<b>%{x}</b><br>Distance: %{y:.2f} km<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Duration per segment
        fig.add_trace(
            go.Bar(
                x=segment_stats['segment_label'],
                y=segment_stats['total_time_hours'],
                marker_color='lightcoral',
                text=segment_stats['total_time_hours'].round(2),
                textposition='outside',
                name='Duration',
                hovertemplate='<b>%{x}</b><br>Duration: %{y:.2f} hours<extra></extra>'
            ),
            row=1, col=2
        )
        
        # Average speed per segment
        fig.add_trace(
            go.Bar(
                x=segment_stats['segment_label'],
                y=segment_stats['calculated_speed'],
                marker_color='lightgreen',
                text=segment_stats['calculated_speed'].round(1),
                textposition='outside',
                name='Avg Speed',
                hovertemplate='<b>%{x}</b><br>Speed: %{y:.1f} km/h<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Waypoints per segment
        fig.add_trace(
            go.Bar(
                x=segment_stats['segment_label'],
                y=segment_stats['waypoint_count'],
                marker_color='lightyellow',
                text=segment_stats['waypoint_count'],
                textposition='outside',
                name='Waypoints',
                hovertemplate='<b>%{x}</b><br>Waypoints: %{y}<extra></extra>'
            ),
            row=2, col=2
        )
        
        # Update axes
        fig.update_xaxes(title_text="Segment", row=1, col=1, tickangle=-45)
        fig.update_yaxes(title_text="Distance (km)", row=1, col=1)
        
        fig.update_xaxes(title_text="Segment", row=1, col=2, tickangle=-45)
        fig.update_yaxes(title_text="Duration (hours)", row=1, col=2)
        
        fig.update_xaxes(title_text="Segment", row=2, col=1, tickangle=-45)
        fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
        
        fig.update_xaxes(title_text="Segment", row=2, col=2, tickangle=-45)
        fig.update_yaxes(title_text="Waypoint Count", row=2, col=2)
        
        fig.update_layout(
            height=700,
            title_text=f"<b>📊 Journey Segment Analysis ({len(segment_stats)} segments)</b>",
            title_font_size=18,
            showlegend=False
        )
        
        return fig

    @staticmethod
    def create_distance_time_correlation(df: pd.DataFrame) -> go.Figure:
        """
        Create scatter plot showing correlation between distance and time
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            Plotly figure
        """
        # Remove zero values for better visualization
        df_filtered = df[(df['Distance_km'] > 0) & (df['time_diff_minutes'] > 0)].copy()
        
        fig = go.Figure()
        
        # Add scatter plot
        fig.add_trace(go.Scatter(
            x=df_filtered['Distance_km'],
            y=df_filtered['time_diff_minutes'],
            mode='markers',
            marker=dict(
                size=8,
                color=df_filtered['Speed_kmh'],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Speed<br>(km/h)"),
                line=dict(color='white', width=0.5)
            ),
            text=[f"WP{int(wp)}" for wp in df_filtered['waypoint_sequence']],
            hovertemplate=(
                '<b>Waypoint %{text}</b><br>' +
                'Distance: %{x:.3f} km<br>' +
                'Time: %{y:.1f} min<br>' +
                'Speed: %{marker.color:.1f} km/h<br>' +
                '<extra></extra>'
            )
        ))
        
        # Add trend line if enough data points
        if len(df_filtered) > 2:
            z = np.polyfit(df_filtered['Distance_km'], df_filtered['time_diff_minutes'], 1)
            p = np.poly1d(z)
            x_trend = np.linspace(df_filtered['Distance_km'].min(), df_filtered['Distance_km'].max(), 100)
            
            fig.add_trace(go.Scatter(
                x=x_trend,
                y=p(x_trend),
                mode='lines',
                line=dict(color='red', width=2, dash='dash'),
                name='Trend Line',
                hoverinfo='skip'
            ))
        
        fig.update_layout(
            title='<b>📊 Distance vs Time Correlation Between Waypoints</b>',
            title_font_size=16,
            xaxis_title='Distance (km)',
            yaxis_title='Time (minutes)',
            height=600,
            hovermode='closest',
            showlegend=True
        )
        
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        
        return fig

    @staticmethod
    def create_waypoint_timeline_chart(df: pd.DataFrame) -> go.Figure:
        """
        Create timeline chart showing waypoint distribution over time
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            Plotly figure
        """
        df_copy = df.copy()
        
        fig = go.Figure()
        
        # Cumulative waypoints
        fig.add_trace(go.Scatter(
            x=df_copy['Date Time'],
            y=df_copy['waypoint_sequence'],
            mode='lines+markers',
            name='Cumulative Waypoints',
            line=dict(color='#3498db', width=2),
            marker=dict(size=4),
            fill='tozeroy',
            fillcolor='rgba(52, 152, 219, 0.2)',
            hovertemplate=(
                '<b>Waypoint #%{y}</b><br>' +
                'Time: %{x}<br>' +
                '<extra></extra>'
            )
        ))
        
        fig.update_layout(
            title='<b>Waypoint Accumulation Over Time</b>',
            title_font_size=16,
            xaxis_title='Time',
            yaxis_title='Cumulative Waypoints',
            hovermode='x unified',
            height=450,
            plot_bgcolor='rgba(240,240,240,0.5)'
        )
        
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.3)')
        
        return fig

    @staticmethod
    def create_waypoint_speed_distribution(df: pd.DataFrame) -> go.Figure:
        """
        Create distribution chart of speeds at waypoints
        
        Args:
            df: DataFrame with Speed_kmh column
            
        Returns:
            Plotly figure
        """
        if 'Speed_kmh' not in df.columns:
            return None
        
        fig = go.Figure()
        
        # Histogram
        fig.add_trace(go.Histogram(
            x=df['Speed_kmh'],
            nbinsx=50,
            name='Speed Distribution',
            marker_color='lightblue',
            marker_line_color='darkblue',
            marker_line_width=0.5
        ))
        
        # Add mean line
        mean_speed = df['Speed_kmh'].mean()
        fig.add_vline(
            x=mean_speed, 
            line_dash="dash", 
            line_color="red",
            annotation_text=f"Mean: {mean_speed:.1f} km/h",
            annotation_position="top"
        )
        
        fig.update_layout(
            title='<b>Speed Distribution at Waypoints</b>',
            title_font_size=16,
            xaxis_title='Speed (km/h)',
            yaxis_title='Number of Waypoints',
            height=450,
            showlegend=False
        )
        
        return fig

    @staticmethod
    def create_hourly_waypoint_heatmap(df: pd.DataFrame) -> go.Figure:
        """
        Create heatmap showing waypoint density by hour and day
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            Plotly figure
        """
        # Group by date and hour
        heatmap_data = df.groupby(['date', 'hour']).size().reset_index(name='count')
        
        # Pivot for heatmap
        pivot_data = heatmap_data.pivot(index='hour', columns='date', values='count').fillna(0)
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot_data.values,
            x=[str(col) for col in pivot_data.columns],
            y=[f"{hour:02d}:00" for hour in pivot_data.index],
            colorscale='Blues',
            hovertemplate='Date: %{x}<br>Hour: %{y}<br>Waypoints: %{z}<extra></extra>',
            colorbar=dict(title="Waypoint<br>Count")
        ))
        
        fig.update_layout(
            title='<b>Waypoint Density by Hour and Day</b>',
            title_font_size=16,
            xaxis_title='Date',
            yaxis_title='Hour of Day',
            height=550
        )
        
        return fig

    @staticmethod
    def compare_waypoints_across_trips(combined_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compare waypoint metrics across multiple trips
        
        Args:
            combined_df: Combined DataFrame from multiple trips
            
        Returns:
            Comparison DataFrame
        """
        if 'trip_id' not in combined_df.columns:
            raise ValueError("combined_df must have trip_id column")
        
        comparison_data = []
        
        for trip_id in combined_df['trip_id'].unique():
            trip_df = combined_df[combined_df['trip_id'] == trip_id]
            
            trip_metrics = {
                'Trip': trip_df['trip_name'].iloc[0] if 'trip_name' in trip_df.columns else f"Trip {trip_id}",
                'Total Waypoints': len(trip_df),
                'Duration (hrs)': trip_df['cumulative_time_hours'].max(),
                'Total Distance (km)': trip_df['cumulative_distance_km'].max(),
                'Avg Speed (km/h)': trip_df['Speed_kmh'].mean() if 'Speed_kmh' in trip_df.columns else 0,
                'Max Speed (km/h)': trip_df['Speed_kmh'].max() if 'Speed_kmh' in trip_df.columns else 0,
                'Stopped Waypoints': len(trip_df[trip_df['Speed_kmh'] == 0]) if 'Speed_kmh' in trip_df.columns else 0,
                'Moving Waypoints': len(trip_df[trip_df['Speed_kmh'] > 0]) if 'Speed_kmh' in trip_df.columns else 0,
                'Avg Distance Between WP (km)': trip_df['Distance_km'].mean(),
                'Avg Time Between WP (min)': trip_df['time_diff_minutes'].mean()
            }
            
            # Add Waypoint1 analysis if available
            if 'Waypoint1' in trip_df.columns:
                trip_metrics['Unique Waypoint1 Values'] = trip_df['Waypoint1'].nunique()
                trip_metrics['Most Common Waypoint1'] = trip_df['Waypoint1'].mode()[0] if len(
                    trip_df['Waypoint1'].mode()) > 0 else 'N/A'
            
            comparison_data.append(trip_metrics)
        
        return pd.DataFrame(comparison_data)

    @staticmethod
    def create_waypoint_comparison_chart(comparison_df: pd.DataFrame) -> go.Figure:
        """
        Create comparison chart for multiple trips
        
        Args:
            comparison_df: DataFrame from compare_waypoints_across_trips()
            
        Returns:
            Plotly figure
        """
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Total Waypoints', 
                'Duration (hours)', 
                'Average Speed', 
                'Distance Covered'
            ),
            specs=[[{'type': 'bar'}, {'type': 'bar'}],
                   [{'type': 'bar'}, {'type': 'bar'}]]
        )
        
        # Total waypoints
        fig.add_trace(
            go.Bar(
                x=comparison_df['Trip'], 
                y=comparison_df['Total Waypoints'],
                name='Waypoints', 
                marker_color='lightblue',
                text=comparison_df['Total Waypoints'],
                textposition='outside'
            ),
            row=1, col=1
        )
        
        # Duration
        fig.add_trace(
            go.Bar(
                x=comparison_df['Trip'], 
                y=comparison_df['Duration (hrs)'],
                name='Duration', 
                marker_color='lightgreen',
                text=comparison_df['Duration (hrs)'].round(2),
                textposition='outside'
            ),
            row=1, col=2
        )
        
        # Average speed
        fig.add_trace(
            go.Bar(
                x=comparison_df['Trip'], 
                y=comparison_df['Avg Speed (km/h)'],
                name='Avg Speed', 
                marker_color='orange',
                text=comparison_df['Avg Speed (km/h)'].round(1),
                textposition='outside'
            ),
            row=2, col=1
        )
        
        # Distance
        fig.add_trace(
            go.Bar(
                x=comparison_df['Trip'], 
                y=comparison_df['Total Distance (km)'],
                name='Distance', 
                marker_color='purple',
                text=comparison_df['Total Distance (km)'].round(2),
                textposition='outside'
            ),
            row=2, col=2
        )
        
        fig.update_xaxes(tickangle=-45)
        fig.update_layout(
            height=700, 
            showlegend=False, 
            title_text="<b>Trip Comparison Metrics</b>",
            title_font_size=18
        )
        
        return fig

    @staticmethod
    def analyze_waypoint1_column(df: pd.DataFrame) -> Dict:
        """
        Analyze Waypoint1 column if present
        
        Args:
            df: DataFrame with Waypoint1 column
            
        Returns:
            Dictionary with Waypoint1 analysis
        """
        if 'Waypoint1' not in df.columns:
            return {'error': 'Waypoint1 column not found'}
        
        waypoint_counts = df['Waypoint1'].value_counts()
        
        # Identify frequent waypoints
        frequent_waypoints = waypoint_counts[waypoint_counts > 1]
        
        # Analyze waypoint sequences/transitions
        waypoint_transitions = []
        for i in range(len(df) - 1):
            if pd.notna(df.iloc[i]['Waypoint1']) and pd.notna(df.iloc[i + 1]['Waypoint1']):
                transition = f"{df.iloc[i]['Waypoint1']} → {df.iloc[i + 1]['Waypoint1']}"
                waypoint_transitions.append(transition)
        
        transition_counts = pd.Series(waypoint_transitions).value_counts()
        
        return {
            'total_waypoints': len(df),
            'unique_waypoint1_values': df['Waypoint1'].nunique(),
            'waypoint1_counts': waypoint_counts.to_dict(),
            'frequent_waypoints': frequent_waypoints.to_dict(),
            'top_10_waypoints': waypoint_counts.head(10).to_dict(),
            'top_transitions': transition_counts.head(10).to_dict(),
            'waypoints_with_stops': len(
                df[df['Status'].str.contains('Stopped', na=False)]) if 'Status' in df.columns else 0
        }

    @staticmethod
    def create_waypoint1_frequency_chart(df: pd.DataFrame, top_n: int = 15) -> Optional[go.Figure]:
        """
        Create frequency chart for Waypoint1 values
        
        Args:
            df: DataFrame with Waypoint1 column
            top_n: Number of top waypoints to show
            
        Returns:
            Plotly figure or None
        """
        if 'Waypoint1' not in df.columns:
            return None
        
        waypoint_counts = df['Waypoint1'].value_counts().head(top_n)
        
        fig = go.Figure(data=[
            go.Bar(
                x=waypoint_counts.index,
                y=waypoint_counts.values,
                marker_color='teal',
                text=waypoint_counts.values,
                textposition='auto',
                hovertemplate='<b>%{x}</b><br>Count: %{y}<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title=f'<b>Top {top_n} Most Frequent Waypoint1 Values</b>',
            title_font_size=16,
            xaxis_title='Waypoint1',
            yaxis_title='Frequency',
            height=450,
            xaxis_tickangle=-45
        )
        
        return fig

    @staticmethod
    def analyze_waypoint_patterns(df: pd.DataFrame) -> Dict:
        """
        Analyze patterns in waypoint distribution
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            Dictionary with pattern analysis
        """
        # Temporal patterns
        hourly_waypoints = df.groupby('hour').size()
        daily_waypoints = df.groupby('date').size()
        
        # Speed at waypoints
        speed_stats = {}
        if 'Speed_kmh' in df.columns:
            speed_stats = {
                'avg_speed_at_waypoints': df['Speed_kmh'].mean(),
                'max_speed': df['Speed_kmh'].max(),
                'min_speed': df['Speed_kmh'].min(),
                'waypoints_stopped': len(df[df['Speed_kmh'] == 0]),
                'waypoints_moving': len(df[df['Speed_kmh'] > 0])
            }
        
        # Distance patterns
        distance_stats = {}
        if 'Distance_km' in df.columns:
            distance_stats = {
                'total_distance': df['cumulative_distance_km'].max() if 'cumulative_distance_km' in df.columns else df['Distance_km'].sum(),
                'avg_distance_between_waypoints': df['Distance_km'].mean(),
                'max_distance_segment': df['Distance_km'].max()
            }
        
        return {
            'temporal': {
                'waypoints_by_hour': hourly_waypoints.to_dict(),
                'waypoints_by_day': daily_waypoints.to_dict(),
                'peak_hour': hourly_waypoints.idxmax(),
                'quiet_hour': hourly_waypoints.idxmin()
            },
            'speed_patterns': speed_stats,
            'distance_patterns': distance_stats,
            'total_waypoints_analyzed': len(df)
        }

    @staticmethod
    def generate_waypoint_summary(df: pd.DataFrame, trip_name: str = "Trip") -> str:
        """
        Generate text summary of waypoint analysis
        
        Args:
            df: Preprocessed DataFrame
            trip_name: Name of the trip
            
        Returns:
            Markdown formatted summary
        """
        total_waypoints = len(df)
        
        if 'cumulative_time_hours' in df.columns:
            duration = df['cumulative_time_hours'].max()
        else:
            duration = (df['Date Time'].max() - df['Date Time'].min()).total_seconds() / 3600
        
        waypoints_per_hour = total_waypoints / max(1, duration)
        
        summary = f"""
## 📍 Waypoint Analysis Summary: {trip_name}

### Key Metrics
- **Total Waypoints**: {total_waypoints:,}
- **Journey Duration**: {duration:.2f} hours
- **Waypoint Frequency**: {waypoints_per_hour:.1f} waypoints/hour
- **Start Time**: {df['Date Time'].min().strftime('%Y-%m-%d %H:%M:%S')}
- **End Time**: {df['Date Time'].max().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if 'cumulative_distance_km' in df.columns:
            total_dist = df['cumulative_distance_km'].max()
            avg_dist = df['Distance_km'].mean()
            summary += f"""
### Distance Metrics
- **Total Distance Covered**: {total_dist:.2f} km
- **Avg Distance Between Waypoints**: {avg_dist:.3f} km
- **Max Single Segment**: {df['Distance_km'].max():.3f} km
"""
        
        if 'Speed_kmh' in df.columns:
            stopped = len(df[df['Speed_kmh'] == 0])
            moving = len(df[df['Speed_kmh'] > 0])
            avg_speed = df[df['Speed_kmh'] > 0]['Speed_kmh'].mean()
            
            summary += f"""
### Movement Metrics
- **Waypoints While Moving**: {moving:,} ({moving / total_waypoints * 100:.1f}%)
- **Waypoints While Stopped**: {stopped:,} ({stopped / total_waypoints * 100:.1f}%)
- **Avg Speed (when moving)**: {avg_speed:.1f} km/h
- **Max Speed**: {df['Speed_kmh'].max():.1f} km/h
"""
        
        if 'Waypoint1' in df.columns:
            unique_wp1 = df['Waypoint1'].nunique()
            most_common = df['Waypoint1'].mode()[0] if len(df['Waypoint1'].mode()) > 0 else 'N/A'
            
            summary += f"""
### Waypoint1 Analysis
- **Unique Waypoint1 Values**: {unique_wp1}
- **Most Common Waypoint1**: {most_common}
"""
        
        return summary