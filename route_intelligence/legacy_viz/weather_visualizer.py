"""
Weather Visualization Module
Creates heatmaps and visualizations for weather impact analysis
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Optional


class WeatherVisualizer:
    """Create weather impact visualizations"""

    @staticmethod
    def create_weather_heatmap(df: pd.DataFrame) -> go.Figure:
        """
        Create hourly weather heatmap showing temperature, rain, and wind

        Args:
            df: DataFrame with weather data and timestamps

        Returns:
            Plotly figure with weather heatmap
        """
        if 'window_start' not in df.columns:
            return None

        # Extract hour and date
        df_copy = df.copy()
        df_copy['hour'] = df_copy['window_start'].dt.hour
        df_copy['date'] = df_copy['window_start'].dt.date

        # Create pivot tables for different metrics
        weather_metrics = []

        # Temperature heatmap
        if 'temperature_c' in df_copy.columns:
            temp_pivot = df_copy.pivot_table(
                values='temperature_c',
                index='hour',
                columns='date',
                aggfunc='mean'
            )
            weather_metrics.append(('Temperature (°C)', temp_pivot, 'RdYlBu_r'))

        # Rain heatmap
        if 'rain_mm' in df_copy.columns:
            rain_pivot = df_copy.pivot_table(
                values='rain_mm',
                index='hour',
                columns='date',
                aggfunc='sum'
            )
            weather_metrics.append(('Rainfall (mm)', rain_pivot, 'Blues'))

        # Wind speed heatmap
        if 'wind_speed_kmh' in df_copy.columns:
            wind_pivot = df_copy.pivot_table(
                values='wind_speed_kmh',
                index='hour',
                columns='date',
                aggfunc='mean'
            )
            weather_metrics.append(('Wind Speed (km/h)', wind_pivot, 'Greens'))

        if not weather_metrics:
            return None

        # Create subplots
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=len(weather_metrics),
            cols=1,
            subplot_titles=[title for title, _, _ in weather_metrics],
            vertical_spacing=0.1
        )

        for idx, (title, pivot, colorscale) in enumerate(weather_metrics, 1):
            heatmap = go.Heatmap(
                z=pivot.values,
                x=[str(col) for col in pivot.columns],
                y=[f"{hour:02d}:00" for hour in pivot.index],
                colorscale=colorscale,
                showscale=True,
                hoverongaps=False,
                hovertemplate='Date: %{x}<br>Hour: %{y}<br>Value: %{z:.1f}<extra></extra>'
            )

            fig.add_trace(heatmap, row=idx, col=1)

        fig.update_layout(
            title='Weather Conditions Throughout Journey',
            height=300 * len(weather_metrics),
            showlegend=False
        )

        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="Hour of Day")

        return fig

    @staticmethod
    def create_weather_impact_chart(df: pd.DataFrame) -> go.Figure:
        """
        Compare speed/efficiency vs weather conditions

        Args:
            df: DataFrame with speed and weather data

        Returns:
            Plotly figure showing correlation
        """
        if 'avg_speed_kmph' not in df.columns or 'weather_description' not in df.columns:
            return None

        df_copy = df.copy()

        # Group by weather condition
        weather_performance = df_copy.groupby('weather_description').agg({
            'avg_speed_kmph': 'mean',
            'avg_moving_speed_kmph': 'mean',
            'stopped_time_sec': 'sum',
            'total_distance_km': 'sum'
        }).reset_index()

        weather_performance['stopped_hours'] = weather_performance['stopped_time_sec'] / 3600

        # Create grouped bar chart
        fig = go.Figure()

        fig.add_trace(go.Bar(
            name='Avg Speed',
            x=weather_performance['weather_description'],
            y=weather_performance['avg_speed_kmph'],
            marker_color='lightblue'
        ))

        fig.add_trace(go.Bar(
            name='Moving Speed',
            x=weather_performance['weather_description'],
            y=weather_performance['avg_moving_speed_kmph'],
            marker_color='darkblue'
        ))

        fig.update_layout(
            title='Speed Performance by Weather Condition',
            xaxis_title='Weather Condition',
            yaxis_title='Speed (km/h)',
            barmode='group',
            hovermode='x unified'
        )

        return fig

    @staticmethod
    def create_weather_timeline(df: pd.DataFrame) -> go.Figure:
        """
        Create timeline showing weather changes during journey

        Args:
            df: DataFrame with weather data over time

        Returns:
            Plotly figure with weather timeline
        """
        if 'window_start' not in df.columns:
            return None

        fig = go.Figure()

        # Temperature line
        if 'temperature_c' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['window_start'],
                y=df['temperature_c'],
                name='Temperature (°C)',
                yaxis='y',
                line=dict(color='red', width=2)
            ))

        # Rainfall bars
        if 'rain_mm' in df.columns:
            fig.add_trace(go.Bar(
                x=df['window_start'],
                y=df['rain_mm'],
                name='Rainfall (mm)',
                yaxis='y2',
                marker_color='blue',
                opacity=0.6
            ))

        # Wind speed line
        if 'wind_speed_kmh' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['window_start'],
                y=df['wind_speed_kmh'],
                name='Wind Speed (km/h)',
                yaxis='y3',
                line=dict(color='green', width=2, dash='dash')
            ))

        fig.update_layout(
            title='Weather Timeline During Journey',
            xaxis=dict(title='Time'),
            yaxis=dict(
                title=dict(text='Temperature (°C)', font=dict(color='red')),
                tickfont=dict(color='red')
            ),

            yaxis2=dict(
                title=dict(text='Rainfall (mm)', font=dict(color='blue')),
                tickfont=dict(color='blue'),
                anchor='free',
                overlaying='y',
                side='right',
                position=0.85
            ),
            yaxis3=dict(
                title=dict(text='Wind (km/h)', font=dict(color='green')),
                tickfont=dict(color='green'),
                anchor='x',
                overlaying='y',
                side='right'
            ),
            hovermode='x unified',
            height=500
        )

        return fig

    @staticmethod
    def create_weather_delay_analysis(df: pd.DataFrame) -> go.Figure:
        """
        Analyze delays caused by adverse weather

        Args:
            df: DataFrame with weather and speed data

        Returns:
            Plotly figure showing weather-related delays
        """
        if 'weather_description' not in df.columns or 'avg_speed_kmph' not in df.columns:
            return None

        df_copy = df.copy()

        # Identify adverse weather
        df_copy['is_adverse'] = df_copy['weather_description'].str.contains(
            'Rain|Storm|Snow|Fog|Heavy', case=False, na=False
        )

        # Compare speeds
        adverse_speed = df_copy[df_copy['is_adverse']]['avg_speed_kmph'].mean()
        normal_speed = df_copy[~df_copy['is_adverse']]['avg_speed_kmph'].mean()

        # Calculate time impact
        total_distance = df_copy['total_distance_km'].sum() if 'total_distance_km' in df_copy.columns else 0

        if normal_speed > 0 and adverse_speed > 0:
            time_normal = total_distance / normal_speed
            time_adverse = total_distance / adverse_speed
            delay_hours = time_adverse - time_normal
        else:
            delay_hours = 0

        # Create visualization
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=['Normal Weather', 'Adverse Weather'],
            y=[normal_speed, adverse_speed],
            marker_color=['green', 'red'],
            text=[f'{normal_speed:.1f} km/h', f'{adverse_speed:.1f} km/h'],
            textposition='auto'
        ))

        fig.update_layout(
            title=f'Weather Impact: {delay_hours:.1f}h delay from adverse conditions',
            yaxis_title='Average Speed (km/h)',
            showlegend=False
        )

        return fig


# Example usage
if __name__ == "__main__":
    # Test with sample data
    sample_data = pd.DataFrame({
        'window_start': pd.date_range('2026-01-01 08:00', periods=20, freq='30min'),
        'temperature_c': np.random.randint(20, 35, 20),
        'rain_mm': np.random.choice([0, 0, 0, 2, 5], 20),
        'wind_speed_kmh': np.random.randint(5, 25, 20),
        'avg_speed_kmph': np.random.randint(30, 50, 20),
        'avg_moving_speed_kmph': np.random.randint(40, 60, 20),
        'total_distance_km': np.random.randint(5, 15, 20),
        'stopped_time_sec': np.random.randint(0, 600, 20),
        'weather_description': np.random.choice(['Clear', 'Cloudy', 'Light Rain'], 20)
    })

    visualizer = WeatherVisualizer()
    fig = visualizer.create_weather_timeline(sample_data)
    if fig:
        fig.show()