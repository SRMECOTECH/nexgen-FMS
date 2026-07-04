"""
AI-Powered Journey Planner
Uses LangChain and OpenAI to provide intelligent journey recommendations
"""

import os
from typing import Dict, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

load_dotenv()


class JourneyPlannerAgent:
    """AI agent for journey planning and route optimization.

    ``langchain_openai`` is an OPTIONAL extra — imported lazily so the whole
    Streamlit app doesn't crash at import time when it isn't installed."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.enabled = False
        if api_key:
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    temperature=0.3,
                    openai_api_key=api_key,
                    model_name="gpt-4o-mini"
                )
                self.enabled = True
            except ImportError:
                # key present but extra not installed — planner stays disabled
                self.enabled = False

    def plan_journey(
            self,
            start_location: str,
            end_location: str,
            distance_km: float,
            historical_data: Dict = None,
            weather_forecast: Dict = None,
            driver_preferences: Dict = None,
            cost_data: Dict = None
    ) -> str:
        """
        Generate AI-powered journey recommendations WITH ACTIONABLE INSIGHTS

        Args:
            start_location: Starting location name
            end_location: Destination name
            distance_km: Total distance
            historical_data: Past journey data on this route
            weather_forecast: Weather predictions
            driver_preferences: Driver preferences
            cost_data: Cost breakdown from business analyzer

        Returns:
            Journey plan as formatted text
        """
        if not self.enabled:
            return "AI Journey Planner unavailable - OpenAI API key not configured"

        try:
            prompt = ChatPromptTemplate.from_template(
                """You are a logistics optimization expert helping a truck fleet owner reduce costs and improve efficiency.

    **Journey Details:**
    - From: {start_location}
    - To: {end_location}
    - Distance: {distance_km} km

    **Historical Performance:**
    {historical_data}

    **Cost Analysis:**
    {cost_data}

    **Weather Conditions:**
    {weather_forecast}

    Provide a BUSINESS-FOCUSED action plan with these sections:

    1. **💰 Cost Optimization (Most Important)**
       - Specific actions to reduce fuel costs
       - How to minimize idle time waste
       - Best departure time to avoid traffic costs
       - Quantify potential savings in ₹

    2. **⏱️ Time Efficiency**
       - Optimal departure time based on traffic patterns
       - Recommended break schedule to maintain legal compliance
       - Expected arrival time window

    3. **⚠️ Risk Mitigation**
       - Weather-related precautions with cost implications
       - High-traffic segments to avoid
       - Safety recommendations

    4. **📍 Strategic Stops**
       - Cheapest fuel stations along route
       - Cost-effective rest areas
       - Emergency service locations

    5. **🎯 Performance Targets**
       - Target average speed for fuel efficiency
       - Maximum acceptable idle time
       - Benchmark cost per kilometer

    Be SPECIFIC with numbers, times, and cost savings. Focus on actionable recommendations that save money.
    """
            )

            # Prepare context
            historical_text = self._format_historical_data(historical_data) if historical_data else "No historical data"
            weather_text = self._format_weather_data(weather_forecast) if weather_forecast else "No weather data"
            cost_text = self._format_cost_data(cost_data) if cost_data else "No cost data"
            preferences_text = self._format_preferences(
                driver_preferences) if driver_preferences else "Standard preferences"

            chain = prompt | self.llm | StrOutputParser()

            result = chain.invoke({
                "start_location": start_location,
                "end_location": end_location,
                "distance_km": distance_km,
                "historical_data": historical_text,
                "weather_forecast": weather_text,
                "cost_data": cost_text,
                "driver_preferences": preferences_text
            })

            return result

        except Exception as e:
            return f"Error generating journey plan: {str(e)}"

    @staticmethod
    def _format_cost_data(data: Dict) -> str:
        """Format cost data for prompt"""
        if not data:
            return "No cost data"

        lines = []

        if 'total_cost_inr' in data:
            lines.append(f"- Total trip cost: ₹{data['total_cost_inr']:,.2f}")

        if 'idle_fuel_waste_inr' in data:
            lines.append(f"- Idle fuel waste: ₹{data['idle_fuel_waste_inr']:,.2f} ⚠️")

        if 'cost_per_km' in data:
            lines.append(f"- Cost per km: ₹{data['cost_per_km']:.2f}")

        if 'fuel_consumed_liters' in data:
            lines.append(f"- Fuel consumed: {data['fuel_consumed_liters']:.1f}L")

        return "\n".join(lines) if lines else "Cost data incomplete"

    def analyze_route_risks(
            self,
            route_data: Dict,
            weather_data: Dict = None,
            time_of_travel: str = None
    ) -> str:
        """
        Analyze potential risks on a planned route

        Args:
            route_data: Route information
            weather_data: Weather conditions
            time_of_travel: Planned travel time

        Returns:
            Risk analysis text
        """
        if not self.enabled:
            return "AI Risk Analysis unavailable"

        try:
            prompt = ChatPromptTemplate.from_template(
                """As a safety analyst for commercial driving, analyze the following route for potential risks:

**Route Information:**
{route_data}

**Weather Conditions:**
{weather_data}

**Planned Travel Time:**
{time_of_travel}

Provide:

1. **High-Risk Segments**
   - Identify dangerous or challenging route sections
   - Risk level (Low/Medium/High)

2. **Weather-Related Risks**
   - How weather might impact the journey
   - Specific precautions needed

3. **Time-of-Day Risks**
   - Traffic congestion periods
   - Visibility concerns (night driving, fog)
   - Fatigue risk periods

4. **Mitigation Strategies**
   - Specific actions to reduce identified risks
   - Alternative timing suggestions

5. **Emergency Preparedness**
   - What to carry/prepare for this route
   - Emergency contact information needs

Be specific and actionable in your recommendations.
"""
            )

            route_text = str(route_data)
            weather_text = self._format_weather_data(weather_data) if weather_data else "No weather data"

            chain = prompt | self.llm | StrOutputParser()

            result = chain.invoke({
                "route_data": route_text,
                "weather_data": weather_text,
                "time_of_travel": time_of_travel or "Not specified"
            })

            return result

        except Exception as e:
            return f"Error analyzing route risks: {str(e)}"

    def suggest_optimizations(
            self,
            historical_routes: List[Dict],
            target_metrics: Dict = None
    ) -> str:
        """
        Suggest route optimizations based on historical data

        Args:
            historical_routes: List of past journey dictionaries
            target_metrics: Target metrics (e.g., reduce time by 10%)

        Returns:
            Optimization suggestions
        """
        if not self.enabled:
            return "AI Optimization unavailable"

        try:
            prompt = ChatPromptTemplate.from_template(
                """Analyze these historical journeys and suggest optimizations:

**Historical Routes:**
{historical_routes}

**Target Improvements:**
{target_metrics}

Provide specific, data-driven recommendations:

1. **Time Optimization**
   - Identify time-wasting patterns
   - Suggest scheduling changes

2. **Fuel Efficiency**
   - Speed optimization recommendations
   - Route selection for fuel savings

3. **Break Management**
   - Optimal break timing and duration
   - Impact on overall efficiency

4. **Consistency Improvements**
   - Reduce variability in journey times
   - Standardize best practices

5. **Cost Savings**
   - Quantify potential savings
   - Implementation priorities

Focus on actionable, measurable improvements.
"""
            )

            routes_text = "\n\n".join([f"Route {i + 1}: {route}" for i, route in enumerate(historical_routes)])
            metrics_text = str(target_metrics) if target_metrics else "General optimization"

            chain = prompt | self.llm | StrOutputParser()

            result = chain.invoke({
                "historical_routes": routes_text,
                "target_metrics": metrics_text
            })

            return result

        except Exception as e:
            return f"Error generating optimizations: {str(e)}"

    # Helper methods for formatting

    @staticmethod
    def _format_historical_data(data: Dict) -> str:
        """Format historical data for prompt"""
        lines = []

        if 'avg_time_hours' in data:
            lines.append(f"- Typical journey time: {data['avg_time_hours']:.1f} hours")

        if 'avg_speed_kmph' in data:
            lines.append(f"- Average speed: {data['avg_speed_kmph']:.1f} km/h")

        if 'traffic_segments' in data:
            lines.append(f"- Known traffic segments: {data['traffic_segments']}")

        if 'common_break_times' in data:
            lines.append(f"- Typical break times: {data['common_break_times']}")

        return "\n".join(lines) if lines else "Limited historical data"

    @staticmethod
    def _format_weather_data(data: Dict) -> str:
        """Format weather data for prompt"""
        if not data:
            return "No weather data"

        lines = []

        if 'temperature_c' in data:
            lines.append(f"- Temperature: {data['temperature_c']}°C")

        if 'conditions' in data:
            lines.append(f"- Conditions: {data['conditions']}")

        if 'precipitation_mm' in data:
            lines.append(f"- Precipitation: {data['precipitation_mm']} mm")

        if 'wind_speed_kmh' in data:
            lines.append(f"- Wind: {data['wind_speed_kmh']} km/h")

        return "\n".join(lines) if lines else "Weather data incomplete"

    @staticmethod
    def _format_preferences(prefs: Dict) -> str:
        """Format driver preferences for prompt"""
        if not prefs:
            return "Standard driver preferences"

        lines = []

        if 'break_frequency_hours' in prefs:
            lines.append(f"- Prefers breaks every {prefs['break_frequency_hours']} hours")

        if 'max_driving_hours' in prefs:
            lines.append(f"- Maximum continuous driving: {prefs['max_driving_hours']} hours")

        if 'preferred_departure_time' in prefs:
            lines.append(f"- Preferred departure: {prefs['preferred_departure_time']}")

        if 'avoid_night_driving' in prefs:
            lines.append(f"- Avoid night driving: {'Yes' if prefs['avoid_night_driving'] else 'No'}")

        return "\n".join(lines) if lines else "No specific preferences"


# Example usage
if __name__ == "__main__":
    planner = JourneyPlannerAgent()

    if planner.enabled:
        # Example journey plan
        plan = planner.plan_journey(
            start_location="Bara, Jharkhand",
            end_location="Kolkata, West Bengal",
            distance_km=250,
            historical_data={
                'avg_time_hours': 5.5,
                'avg_speed_kmph': 45,
                'traffic_segments': 'NH60 near Asansol',
                'common_break_times': '12:00-12:30, 15:00-15:15'
            },
            weather_forecast={
                'temperature_c': 28,
                'conditions': 'Partly cloudy',
                'precipitation_mm': 0,
                'wind_speed_kmh': 15
            }
        )

        print("Journey Plan:")
        print(plan)
    else:
        print("OpenAI API key not configured")