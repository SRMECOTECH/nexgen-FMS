"""
Enhanced Comparison Module
Additional comparison features that enrich the existing analyzer
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium


class EnhancedComparison:
    """Enhanced comparison features for route analysis"""

    @staticmethod
    def create_multi_route_map(routes_data):
        """Create map with multiple routes in different colors"""
        colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'lightred',
                  'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'pink', 'lightblue']

        # Calculate center
        all_lats = []
        all_lons = []
        for _, df_agg in routes_data:
            all_lats.extend(df_agg['latitude'].tolist())
            all_lons.extend(df_agg['longitude'].tolist())

        center_lat = np.mean(all_lats)
        center_lon = np.mean(all_lons)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

        # Add each route with distinct styling
        for idx, (route_name, df_agg) in enumerate(routes_data):
            color = colors[idx % len(colors)]

            # Route line
            coordinates = df_agg[['latitude', 'longitude']].values.tolist()
            folium.PolyLine(
                coordinates,
                color=color,
                weight=4,
                opacity=0.8,
                popup=f"<b>{route_name}</b><br>Distance: {df_agg['total_distance_km'].sum():.1f} km"
            ).add_to(m)

            # Start marker
            folium.Marker(
                [df_agg.iloc[0]['latitude'], df_agg.iloc[0]['longitude']],
                popup=f"<b>{route_name}</b><br>Start: {df_agg.iloc[0]['window_start']}",
                icon=folium.Icon(color=color, icon='play', prefix='fa')
            ).add_to(m)

            # End marker
            folium.Marker(
                [df_agg.iloc[-1]['latitude'], df_agg.iloc[-1]['longitude']],
                popup=f"<b>{route_name}</b><br>End: {df_agg.iloc[-1]['window_end']}",
                icon=folium.Icon(color=color, icon='stop', prefix='fa')
            ).add_to(m)

        return m

    @staticmethod
    def create_waypoint_distribution_chart(routes_data):
        """Create chart showing waypoint distribution over time"""
        fig = go.Figure()

        for route_name, df_agg in routes_data:
            fig.add_trace(go.Scatter(
                x=df_agg['window_start'],
                y=df_agg['waypoint_count'],
                mode='lines+markers',
                name=route_name,
                hovertemplate='<b>%{fullData.name}</b><br>' +
                              'Time: %{x}<br>' +
                              'Waypoints: %{y}<br>' +
                              '<extra></extra>'
            ))

        fig.update_layout(
            title='Waypoint Distribution Over Time',
            xaxis_title='Time',
            yaxis_title='Number of Waypoints',
            hovermode='x unified',
            height=500
        )

        return fig

    @staticmethod
    def create_comprehensive_heatmap(routes_data):
        """Create comprehensive heatmap comparing distance, speed, and stops"""
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('Distance Comparison', 'Speed Comparison', 'Stop Duration Comparison'),
            vertical_spacing=0.12,
            row_heights=[0.33, 0.33, 0.33]
        )

        for route_name, df_agg in routes_data:
            # Distance trace
            fig.add_trace(
                go.Scatter(
                    x=df_agg['window_start'],
                    y=df_agg['total_distance_km'],
                    name=f'{route_name} - Distance',
                    mode='lines',
                    showlegend=True
                ),
                row=1, col=1
            )

            # Speed trace
            fig.add_trace(
                go.Scatter(
                    x=df_agg['window_start'],
                    y=df_agg['avg_speed_kmph'],
                    name=f'{route_name} - Speed',
                    mode='lines',
                    showlegend=True
                ),
                row=2, col=1
            )

            # Stop duration trace
            fig.add_trace(
                go.Scatter(
                    x=df_agg['window_start'],
                    y=df_agg['stopped_time_sec'] / 60,  # Convert to minutes
                    name=f'{route_name} - Stops',
                    mode='lines',
                    fill='tozeroy',
                    showlegend=True
                ),
                row=3, col=1
            )

        fig.update_xaxes(title_text="Time", row=3, col=1)
        fig.update_yaxes(title_text="Distance (km)", row=1, col=1)
        fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
        fig.update_yaxes(title_text="Stop Duration (min)", row=3, col=1)

        fig.update_layout(height=1000, hovermode='x unified')

        return fig

    @staticmethod
    def create_time_of_day_analysis(routes_data):
        """Analyze patterns by time of day"""
        fig = make_subplots(
            rows=1, cols=len(routes_data),
            subplot_titles=[name for name, _ in routes_data],
            specs=[[{'type': 'polar'}] * len(routes_data)]
        )

        for idx, (route_name, df_agg) in enumerate(routes_data, 1):
            df_copy = df_agg.copy()
            df_copy['hour'] = df_copy['window_start'].dt.hour

            hourly_data = df_copy.groupby('hour').agg({
                'total_distance_km': 'sum',
                'avg_speed_kmph': 'mean'
            }).reset_index()

            fig.add_trace(
                go.Scatterpolar(
                    r=hourly_data['total_distance_km'],
                    theta=hourly_data['hour'] * 15,  # Convert hour to degrees
                    fill='toself',
                    name=route_name
                ),
                row=1, col=idx
            )

        fig.update_layout(
            title='Distance by Hour of Day (Polar View)',
            height=500,
            showlegend=True
        )

        return fig

    @staticmethod
    def analyze_meal_patterns(df_agg):
        """Identify potential lunch/dinner stops based on time and duration"""
        df_copy = df_agg.copy()
        df_copy['hour'] = df_copy['window_start'].dt.hour
        df_copy['stop_duration_min'] = df_copy['stopped_time_sec'] / 60

        # Define meal time windows
        lunch_window = (df_copy['hour'] >= 12) & (df_copy['hour'] <= 14)
        dinner_window = (df_copy['hour'] >= 19) & (df_copy['hour'] <= 21)

        # Find significant stops (>15 minutes)
        significant_stops = df_copy['stop_duration_min'] > 15

        lunch_stops = df_copy[lunch_window & significant_stops]
        dinner_stops = df_copy[dinner_window & significant_stops]

        return {
            'lunch_stops': lunch_stops[['window_start', 'latitude', 'longitude', 'stop_duration_min']],
            'dinner_stops': dinner_stops[['window_start', 'latitude', 'longitude', 'stop_duration_min']],
            'lunch_count': len(lunch_stops),
            'dinner_count': len(dinner_stops),
            'total_lunch_time_min': lunch_stops['stop_duration_min'].sum(),
            'total_dinner_time_min': dinner_stops['stop_duration_min'].sum()
        }

    @staticmethod
    def create_detailed_comparison_table(routes_data, raw_routes_data):
        """Build comprehensive comparison table with all metrics"""
        comparison_data = []

        for (route_name, df_agg), (_, df_raw) in zip(routes_data, raw_routes_data):
            total_distance = df_agg['total_distance_km'].sum()
            duration = (df_agg['moving_time_sec'].sum() + df_agg['stopped_time_sec'].sum()) / 3600
            moving_time = df_agg['moving_time_sec'].sum() / 3600
            stopped_time = df_agg['stopped_time_sec'].sum() / 3600
            avg_speed = df_agg['avg_speed_kmph'].mean()
            moving_speed = df_agg['avg_moving_speed_kmph'].mean()
            max_speed = df_agg['max_speed_kmph'].max()
            waypoints = len(df_raw)

            comparison_data.append({
                'Route': route_name,
                'Distance (km)': round(total_distance, 2),
                'Duration (hrs)': round(duration, 2),
                'Moving Time (hrs)': round(moving_time, 2),
                'Stopped Time (hrs)': round(stopped_time, 2),
                'Efficiency (%)': round((moving_time / duration * 100) if duration > 0 else 0, 1),
                'Avg Speed (km/h)': round(avg_speed, 1),
                'Moving Speed (km/h)': round(moving_speed, 1),
                'Max Speed (km/h)': round(max_speed, 1),
                'Total Waypoints': waypoints,
                'Aggregated Windows': len(df_agg),
                'Compression Ratio': round(waypoints / len(df_agg), 1) if len(df_agg) > 0 else 0,
                'Start Time': df_agg.iloc[0]['window_start'].strftime('%Y-%m-%d %H:%M'),
                'End Time': df_agg.iloc[-1]['window_end'].strftime('%Y-%m-%d %H:%M')
            })

        return pd.DataFrame(comparison_data)

    @staticmethod
    def create_stacked_duration_chart(routes_data):
        """Create stacked bar chart for moving vs stopped time"""
        fig = go.Figure()

        for route_name, df_agg in routes_data:
            moving_time = df_agg['moving_time_sec'].sum() / 3600
            stopped_time = df_agg['stopped_time_sec'].sum() / 3600

            fig.add_trace(go.Bar(
                name=f'{route_name} - Moving',
                x=[route_name],
                y=[moving_time],
                text=[f"{moving_time:.1f}h"],
                textposition='inside',
                marker_color='lightgreen'
            ))

            fig.add_trace(go.Bar(
                name=f'{route_name} - Stopped',
                x=[route_name],
                y=[stopped_time],
                text=[f"{stopped_time:.1f}h"],
                textposition='inside',
                marker_color='lightcoral'
            ))

        fig.update_layout(
            title='Time Breakdown: Moving vs Stopped',
            yaxis_title='Hours',
            barmode='stack',
            height=500,
            showlegend=True
        )

        return fig

    @staticmethod
    def create_speed_distribution_boxplot(routes_data):
        """Create box plot for speed distribution comparison"""
        fig = go.Figure()

        for route_name, df_agg in routes_data:
            fig.add_trace(go.Box(
                y=df_agg['avg_speed_kmph'],
                name=route_name,
                boxmean='sd'
            ))

        fig.update_layout(
            title='Speed Distribution Comparison',
            yaxis_title='Speed (km/h)',
            height=500
        )

        return fig

    @staticmethod
    def create_distance_comparison_chart(routes_data):
        """Create bar chart comparing total distances"""
        fig = go.Figure()

        for route_name, df_agg in routes_data:
            total_dist = df_agg['total_distance_km'].sum()
            fig.add_trace(go.Bar(
                name=route_name,
                x=[route_name],
                y=[total_dist],
                text=[f"{total_dist:.1f} km"],
                textposition='auto'
            ))

        fig.update_layout(
            title='Total Distance Comparison',
            yaxis_title='Distance (km)',
            showlegend=False,
            height=400
        )

        return fig

    @staticmethod
    def create_speed_timeline_comparison(routes_data):
        """Create timeline comparing speeds across routes"""
        fig = go.Figure()

        for route_name, df_agg in routes_data:
            fig.add_trace(go.Scatter(
                x=df_agg['window_start'],
                y=df_agg['avg_speed_kmph'],
                mode='lines',
                name=route_name,
                hovertemplate='<b>%{fullData.name}</b><br>' +
                              'Time: %{x}<br>' +
                              'Speed: %{y:.1f} km/h<br>' +
                              '<extra></extra>'
            ))

        fig.update_layout(
            title='Speed Timeline Comparison',
            xaxis_title='Time',
            yaxis_title='Speed (km/h)',
            hovermode='x unified',
            height=500
        )

        return fig