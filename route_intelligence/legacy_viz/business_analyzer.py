"""
Business Analytics Module
Provides actionable insights for fleet optimization
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta


class BusinessAnalyzer:
    """Generate business-focused insights from route data"""

    def __init__(self,
                 fuel_price_per_liter: float = 100.0,
                 fuel_efficiency_kmpl: float = 4.0,
                 driver_wage_per_hour: float = 150.0,
                 idle_fuel_consumption_lph: float = 1.5):
        """
        Initialize with cost parameters

        Args:
            fuel_price_per_liter: Current diesel price (₹)
            fuel_efficiency_kmpl: Average km per liter
            driver_wage_per_hour: Driver hourly wage (₹)
            idle_fuel_consumption_lph: Fuel consumed while idling (liters/hour)
        """
        self.fuel_price = fuel_price_per_liter
        self.fuel_efficiency = fuel_efficiency_kmpl
        self.driver_wage = driver_wage_per_hour
        self.idle_fuel_rate = idle_fuel_consumption_lph

    def calculate_journey_costs(self, df_agg: pd.DataFrame) -> Dict:
        """Calculate detailed cost breakdown"""
        total_distance = df_agg['total_distance_km'].sum()
        moving_hours = df_agg['moving_time_sec'].sum() / 3600
        stopped_hours = df_agg['stopped_time_sec'].sum() / 3600
        total_hours = moving_hours + stopped_hours

        # Fuel costs
        moving_fuel_liters = total_distance / self.fuel_efficiency
        idle_fuel_liters = stopped_hours * self.idle_fuel_rate
        total_fuel_liters = moving_fuel_liters + idle_fuel_liters
        total_fuel_cost = total_fuel_liters * self.fuel_price

        # Driver costs
        driver_cost = total_hours * self.driver_wage

        # Total trip cost
        total_cost = total_fuel_cost + driver_cost

        return {
            'total_cost_inr': round(total_cost, 2),
            'fuel_cost_inr': round(total_fuel_cost, 2),
            'driver_cost_inr': round(driver_cost, 2),
            'fuel_consumed_liters': round(total_fuel_liters, 2),
            'moving_fuel_liters': round(moving_fuel_liters, 2),
            'idle_fuel_liters': round(idle_fuel_liters, 2),
            'idle_fuel_waste_inr': round(idle_fuel_liters * self.fuel_price, 2),
            'cost_per_km': round(total_cost / total_distance, 2) if total_distance > 0 else 0
        }

    def identify_cost_savings_opportunities(self, df_agg: pd.DataFrame) -> List[Dict]:
        """Identify specific areas where costs can be reduced"""
        opportunities = []

        stopped_hours = df_agg['stopped_time_sec'].sum() / 3600
        moving_hours = df_agg['moving_time_sec'].sum() / 3600

        # Opportunity 1: Reduce idle time
        if stopped_hours > 2:
            idle_waste = stopped_hours * self.idle_fuel_rate * self.fuel_price
            potential_savings = idle_waste * 0.3  # Assume 30% reduction possible

            opportunities.append({
                'category': 'Idle Time Reduction',
                'current_waste_inr': round(idle_waste, 2),
                'potential_savings_inr': round(potential_savings, 2),
                'monthly_savings_inr': round(potential_savings * 30, 2),  # Assuming daily trips
                'recommendation': f'Reduce idle time by 30% (save ₹{potential_savings:.0f} per trip)',
                'priority': 'HIGH'
            })

        # Opportunity 2: Speed optimization
        avg_speed = df_agg['avg_moving_speed_kmph'].mean()
        if avg_speed < 40:
            # Faster routes could save time
            time_saved_hours = moving_hours * 0.15  # 15% faster
            cost_savings = time_saved_hours * self.driver_wage

            opportunities.append({
                'category': 'Route Optimization',
                'current_waste_inr': 0,
                'potential_savings_inr': round(cost_savings, 2),
                'monthly_savings_inr': round(cost_savings * 30, 2),
                'recommendation': f'Optimize route to increase avg speed to 45 km/h',
                'priority': 'MEDIUM'
            })

        # Opportunity 3: Peak hour avoidance
        df_agg_copy = df_agg.copy()
        df_agg_copy['hour'] = df_agg_copy['window_start'].dt.hour
        peak_hours = df_agg_copy[(df_agg_copy['hour'] >= 8) & (df_agg_copy['hour'] <= 10)]

        if len(peak_hours) > len(df_agg_copy) * 0.3:
            opportunities.append({
                'category': 'Peak Hour Avoidance',
                'current_waste_inr': 0,
                'potential_savings_inr': 500,  # Estimated
                'monthly_savings_inr': 15000,
                'recommendation': 'Start journeys before 7 AM to avoid peak traffic',
                'priority': 'MEDIUM'
            })

        return opportunities

    def compare_routes(self, routes_data: List[Tuple[str, pd.DataFrame]]) -> pd.DataFrame:
        """
        Compare multiple routes side-by-side

        Args:
            routes_data: List of (route_name, aggregated_df) tuples

        Returns:
            Comparison DataFrame
        """
        comparisons = []

        for route_name, df_agg in routes_data:
            costs = self.calculate_journey_costs(df_agg)

            total_distance = df_agg['total_distance_km'].sum()
            moving_hours = df_agg['moving_time_sec'].sum() / 3600
            stopped_hours = df_agg['stopped_time_sec'].sum() / 3600
            total_hours = moving_hours + stopped_hours

            avg_speed_effective = df_agg['avg_speed_kmph'].mean()
            avg_speed_moving = df_agg['avg_moving_speed_kmph'].mean()

            comparisons.append({
                'Route': route_name,
                'Distance (km)': round(total_distance, 2),
                'Duration (hrs)': round(total_hours, 2),
                'Moving Time (hrs)': round(moving_hours, 2),
                'Idle Time (hrs)': round(stopped_hours, 2),
                'Avg Speed (km/h)': round(avg_speed_effective, 1),
                'Moving Speed (km/h)': round(avg_speed_moving, 1),
                'Total Cost (₹)': costs['total_cost_inr'],
                'Fuel Cost (₹)': costs['fuel_cost_inr'],
                'Idle Waste (₹)': costs['idle_fuel_waste_inr'],
                'Cost/km (₹)': costs['cost_per_km'],
                'Efficiency (%)': round(moving_hours / total_hours * 100, 1) if total_hours > 0 else 0
            })

        df_comparison = pd.DataFrame(comparisons)

        # Add rankings
        df_comparison['Cost Rank'] = df_comparison['Total Cost (₹)'].rank()
        df_comparison['Time Rank'] = df_comparison['Duration (hrs)'].rank()
        df_comparison['Efficiency Rank'] = df_comparison['Efficiency (%)'].rank(ascending=False)

        return df_comparison

    def generate_executive_summary(self, df_agg: pd.DataFrame, route_name: str = "This Route") -> str:
        """Generate executive summary with actionable insights"""
        costs = self.calculate_journey_costs(df_agg)
        opportunities = self.identify_cost_savings_opportunities(df_agg)

        total_distance = df_agg['total_distance_km'].sum()
        moving_hours = df_agg['moving_time_sec'].sum() / 3600
        stopped_hours = df_agg['stopped_time_sec'].sum() / 3600

        summary = f"""
## 💼 Executive Summary: {route_name}

### 📊 Key Metrics
- **Total Cost**: ₹{costs['total_cost_inr']:,.2f}
- **Distance**: {total_distance:.1f} km
- **Cost per km**: ₹{costs['cost_per_km']:.2f}
- **Idle Time**: {stopped_hours:.1f} hours (₹{costs['idle_fuel_waste_inr']:,.0f} wasted)

### 💰 Cost Breakdown
- Fuel: ₹{costs['fuel_cost_inr']:,.2f} ({costs['fuel_consumed_liters']:.1f}L)
  - Moving: {costs['moving_fuel_liters']:.1f}L
  - Idle: {costs['idle_fuel_liters']:.1f}L ⚠️
- Driver Wages: ₹{costs['driver_cost_inr']:,.2f}

### 🎯 Cost Savings Opportunities
"""

        total_monthly_savings = 0
        for opp in opportunities:
            summary += f"\n**{opp['category']}** ({opp['priority']} Priority)\n"
            summary += f"- {opp['recommendation']}\n"
            summary += f"- Potential Monthly Savings: ₹{opp['monthly_savings_inr']:,.0f}\n"
            total_monthly_savings += opp['monthly_savings_inr']

        if total_monthly_savings > 0:
            summary += f"\n### 💵 Total Monthly Savings Potential: ₹{total_monthly_savings:,.0f}"
            summary += f"\n### 💵 Annual Savings Potential: ₹{total_monthly_savings * 12:,.0f}"

        return summary


# Example usage
if __name__ == "__main__":
    # Test with sample data
    sample_data = pd.DataFrame({
        'window_start': pd.date_range('2026-01-01 08:00', periods=10, freq='30min'),
        'total_distance_km': [5, 8, 6, 7, 9, 5, 6, 8, 7, 5],
        'moving_time_sec': [1200, 1500, 1300, 1400, 1600, 1200, 1300, 1500, 1400, 1200],
        'stopped_time_sec': [300, 200, 400, 300, 200, 500, 400, 300, 300, 400],
        'avg_speed_kmph': [35, 40, 32, 38, 42, 30, 33, 40, 37, 32],
        'avg_moving_speed_kmph': [45, 48, 42, 46, 50, 40, 43, 48, 46, 42]
    })

    analyzer = BusinessAnalyzer()
    costs = analyzer.calculate_journey_costs(sample_data)
    print("Costs:", costs)

    summary = analyzer.generate_executive_summary(sample_data)
    print(summary)