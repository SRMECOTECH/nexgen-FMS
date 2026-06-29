"""
Route Comparison Visualization Module
Creates charts for comparing multiple routes
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Tuple, Dict


class ComparisonVisualizer:
    """Create visualizations for route comparisons"""

    @staticmethod
    def create_cost_comparison_chart(comparison_df: pd.DataFrame) -> go.Figure:
        """
        Create cost comparison bar chart

        Args:
            comparison_df: DataFrame from BusinessAnalyzer.compare_routes()

        Returns:
            Plotly figure with cost comparisons
        """
        fig = go.Figure()

        # Total cost bars
        fig.add_trace(go.Bar(
            name='Total Cost',
            x=comparison_df['Route'],
            y=comparison_df['Total Cost (₹)'],
            marker_color='lightblue',
            text=comparison_df['Total Cost (₹)'].apply(lambda x: f'₹{x:,.0f}'),
            textposition='auto'
        ))

        # Fuel cost bars
        fig.add_trace(go.Bar(
            name='Fuel Cost',
            x=comparison_df['Route'],
            y=comparison_df['Fuel Cost (₹)'],
            marker_color='orange',
            text=comparison_df['Fuel Cost (₹)'].apply(lambda x: f'₹{x:,.0f}'),
            textposition='auto'
        ))

        # Idle waste bars
        fig.add_trace(go.Bar(
            name='Idle Waste',
            x=comparison_df['Route'],
            y=comparison_df['Idle Waste (₹)'],
            marker_color='red',
            text=comparison_df['Idle Waste (₹)'].apply(lambda x: f'₹{x:,.0f}'),
            textposition='auto'
        ))

        fig.update_layout(
            title='💰 Cost Comparison Across Routes',
            xaxis_title='Route',
            yaxis_title='Cost (₹)',
            barmode='group',
            hovermode='x unified',
            height=500
        )

        return fig

    @staticmethod
    def create_efficiency_comparison_radar(comparison_df: pd.DataFrame) -> go.Figure:
        """
        Create radar chart comparing route efficiencies

        Args:
            comparison_df: DataFrame from BusinessAnalyzer.compare_routes()

        Returns:
            Plotly figure with radar chart
        """
        # Normalize metrics to 0-100 scale
        metrics = ['Efficiency (%)', 'Avg Speed (km/h)', 'Moving Speed (km/h)']

        fig = go.Figure()

        for idx, row in comparison_df.iterrows():
            # Normalize values
            efficiency = row['Efficiency (%)']
            speed_norm = (row['Avg Speed (km/h)'] / 80) * 100  # Assume 80 km/h is max
            moving_speed_norm = (row['Moving Speed (km/h)'] / 80) * 100

            # Invert cost per km (lower is better)
            max_cost = comparison_df['Cost/km (₹)'].max()
            cost_norm = ((max_cost - row['Cost/km (₹)']) / max_cost) * 100

            # Invert idle time (lower is better)
            max_idle = comparison_df['Idle Time (hrs)'].max()
            idle_norm = ((max_idle - row['Idle Time (hrs)']) / max_idle) * 100 if max_idle > 0 else 0

            fig.add_trace(go.Scatterpolar(
                r=[efficiency, speed_norm, moving_speed_norm, cost_norm, idle_norm],
                theta=['Time Efficiency', 'Avg Speed', 'Moving Speed', 'Cost Efficiency', 'Idle Efficiency'],
                fill='toself',
                name=row['Route']
            ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )
            ),
            title='📊 Multi-Dimensional Route Performance',
            showlegend=True,
            height=600
        )

        return fig

    @staticmethod
    def create_time_distance_comparison(comparison_df: pd.DataFrame) -> go.Figure:
        """
        Create scatter plot comparing time vs distance

        Args:
            comparison_df: DataFrame from BusinessAnalyzer.compare_routes()

        Returns:
            Plotly figure with scatter plot
        """
        fig = go.Figure()

        # Size bubbles by total cost
        sizes = comparison_df['Total Cost (₹)'] / comparison_df['Total Cost (₹)'].max() * 100

        fig.add_trace(go.Scatter(
            x=comparison_df['Distance (km)'],
            y=comparison_df['Duration (hrs)'],
            mode='markers+text',
            marker=dict(
                size=sizes,
                color=comparison_df['Cost/km (₹)'],
                colorscale='Reds',
                showscale=True,
                colorbar=dict(title="Cost/km (₹)"),
                line=dict(width=2, color='DarkSlateGrey')
            ),
            text=comparison_df['Route'],
            textposition='top center',
            hovertemplate='<b>%{text}</b><br>' +
                          'Distance: %{x:.1f} km<br>' +
                          'Duration: %{y:.1f} hrs<br>' +
                          '<extra></extra>'
        ))

        fig.update_layout(
            title='⏱️ Distance vs Time Comparison (Bubble size = Total Cost)',
            xaxis_title='Distance (km)',
            yaxis_title='Duration (hours)',
            height=500,
            hovermode='closest'
        )

        return fig

    @staticmethod
    def create_ranking_table(comparison_df: pd.DataFrame) -> go.Figure:
        """
        Create ranking table showing best routes

        Args:
            comparison_df: DataFrame from BusinessAnalyzer.compare_routes()

        Returns:
            Plotly figure with table
        """
        # Create ranking summary
        ranking_data = []

        for idx, row in comparison_df.iterrows():
            ranking_data.append({
                'Route': row['Route'],
                '🏆 Cost Rank': int(row['Cost Rank']),
                '⏱️ Time Rank': int(row['Time Rank']),
                '⚡ Efficiency Rank': int(row['Efficiency Rank']),
                '💰 Total Cost': f"₹{row['Total Cost (₹)']:,.0f}",
                '🎯 Overall Score': int((3 - row['Cost Rank'] - row['Time Rank'] - row['Efficiency Rank']) / 3 * 100)
            })

        ranking_df = pd.DataFrame(ranking_data).sort_values('🎯 Overall Score', ascending=False)

        # Color code cells
        fig = go.Figure(data=[go.Table(
            header=dict(
                values=list(ranking_df.columns),
                fill_color='paleturquoise',
                align='left',
                font=dict(size=12, color='black')
            ),
            cells=dict(
                values=[ranking_df[col] for col in ranking_df.columns],
                fill_color='lavender',
                align='left',
                font=dict(size=11)
            )
        )])

        fig.update_layout(
            title='🏆 Route Rankings (Lower rank = Better)',
            height=300
        )

        return fig

    @staticmethod
    def create_speed_profile_comparison(routes_data: List[Tuple[str, pd.DataFrame]]) -> go.Figure:
        """
        Compare speed profiles across routes over time

        Args:
            routes_data: List of (route_name, aggregated_df) tuples

        Returns:
            Plotly figure with speed profiles
        """
        fig = go.Figure()

        colors = px.colors.qualitative.Set2

        for idx, (route_name, df_agg) in enumerate(routes_data):
            # Normalize time to 0-100% of journey
            df_copy = df_agg.copy()

            # FIX: Convert range to list comprehension
            if len(df_copy) > 1:
                df_copy['journey_pct'] = [i / (len(df_copy) - 1) * 100 for i in range(len(df_copy))]
            else:
                df_copy['journey_pct'] = [0]

            fig.add_trace(go.Scatter(
                x=df_copy['journey_pct'],
                y=df_copy['avg_speed_kmph'],
                mode='lines',
                name=route_name,
                line=dict(color=colors[idx % len(colors)], width=2),
                hovertemplate=f'<b>{route_name}</b><br>' +
                              'Journey: %{x:.0f}%<br>' +
                              'Speed: %{y:.1f} km/h<br>' +
                              '<extra></extra>'
            ))

        fig.update_layout(
            title='🚛 Speed Profiles Across Journey',
            xaxis_title='Journey Progress (%)',
            yaxis_title='Speed (km/h)',
            hovermode='x unified',
            height=500,
            showlegend=True
        )

        return fig

    @staticmethod
    def create_best_route_recommendation(comparison_df: pd.DataFrame) -> Dict:
        """
        Determine and recommend the best route based on multiple criteria

        Args:
            comparison_df: DataFrame from BusinessAnalyzer.compare_routes()

        Returns:
            Dictionary with recommendations
        """
        # Find best in each category
        cheapest = comparison_df.loc[comparison_df['Total Cost (₹)'].idxmin()]
        fastest = comparison_df.loc[comparison_df['Duration (hrs)'].idxmin()]
        most_efficient = comparison_df.loc[comparison_df['Efficiency (%)'].idxmax()]
        lowest_cost_per_km = comparison_df.loc[comparison_df['Cost/km (₹)'].idxmin()]

        # Calculate overall winner (weighted score)
        comparison_df_copy = comparison_df.copy()
        comparison_df_copy['score'] = (
                (1 / comparison_df_copy['Cost Rank']) * 0.4 +  # 40% weight on cost
                (1 / comparison_df_copy['Time Rank']) * 0.3 +  # 30% weight on time
                (1 / comparison_df_copy['Efficiency Rank']) * 0.3  # 30% weight on efficiency
        )

        overall_best = comparison_df_copy.loc[comparison_df_copy['score'].idxmax()]

        return {
            'overall_best': {
                'route': overall_best['Route'],
                'reason': 'Best balanced performance across cost, time, and efficiency'
            },
            'cheapest': {
                'route': cheapest['Route'],
                'cost': cheapest['Total Cost (₹)'],
                'savings_vs_most_expensive': comparison_df['Total Cost (₹)'].max() - cheapest['Total Cost (₹)']
            },
            'fastest': {
                'route': fastest['Route'],
                'duration': fastest['Duration (hrs)'],
                'time_saved': comparison_df['Duration (hrs)'].max() - fastest['Duration (hrs)']
            },
            'most_efficient': {
                'route': most_efficient['Route'],
                'efficiency': most_efficient['Efficiency (%)']
            },
            'best_cost_per_km': {
                'route': lowest_cost_per_km['Route'],
                'cost_per_km': lowest_cost_per_km['Cost/km (₹)']
            }
        }


# Example usage
if __name__ == "__main__":
    # Test with sample comparison data
    sample_comparison = pd.DataFrame({
        'Route': ['Route A', 'Route B', 'Route C'],
        'Distance (km)': [150, 145, 160],
        'Duration (hrs)': [4.5, 4.2, 5.0],
        'Total Cost (₹)': [2500, 2300, 2700],
        'Fuel Cost (₹)': [1800, 1700, 2000],
        'Idle Waste (₹)': [300, 200, 400],
        'Cost/km (₹)': [16.7, 15.9, 16.9],
        'Efficiency (%)': [75, 82, 70],
        'Avg Speed (km/h)': [33, 35, 32],
        'Moving Speed (km/h)': [45, 48, 42],
        'Idle Time (hrs)': [1.2, 0.8, 1.5],
        'Cost Rank': [2, 1, 3],
        'Time Rank': [2, 1, 3],
        'Efficiency Rank': [2, 1, 3]
    })

    visualizer = ComparisonVisualizer()
    fig = visualizer.create_cost_comparison_chart(sample_comparison)
    fig.show()