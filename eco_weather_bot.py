"""
Eco-Friendly Weather & Health Assistant Bot
Uses LangChain with a local open-source LLM and Open-Meteo APIs for real-time weather and air quality data.
"""

import json
import requests
from typing import Optional
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, BaseMessage
from langchain_ollama import ChatOllama


@tool
def fetch_weather_and_air_quality(latitude: float, longitude: float) -> str:
    """
    Fetch real-time weather and air quality data for a given location.
    
    Retrieves current temperature, UV index, PM2.5, and US AQI from Open-Meteo APIs.
    Merges responses into a single JSON structure for analysis.
    
    Args:
        latitude: Geographic latitude coordinate (e.g., 33.57)
        longitude: Geographic longitude coordinate (e.g., -7.58)
    
    Returns:
        JSON string containing merged weather and air quality data
    """
    try:
        # Fetch weather data
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,uv_index",
            "timezone": "auto"
        }
        weather_response = requests.get(weather_url, params=weather_params, timeout=10)
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        
        # Fetch air quality data
        aq_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        aq_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "pm2_5,us_aqi",
            "timezone": "auto"
        }
        aq_response = requests.get(aq_url, params=aq_params, timeout=10)
        aq_response.raise_for_status()
        aq_data = aq_response.json()
        
        # Merge both API responses
        merged_data = {
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "timezone": weather_data.get("timezone", "Unknown")
            },
            "weather": {
                "temperature_celsius": weather_data.get("current", {}).get("temperature_2m"),
                "uv_index": weather_data.get("current", {}).get("uv_index")
            },
            "air_quality": {
                "pm2_5_µg_m3": aq_data.get("current", {}).get("pm2_5"),
                "us_aqi": aq_data.get("current", {}).get("us_aqi")
            }
        }
        
        return json.dumps(merged_data, indent=2)
    
    except requests.exceptions.Timeout:
        return json.dumps({"error": "API request timeout. Please try again."})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Failed to fetch data: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


def initialize_eco_bot() -> ChatOllama:
    """
    Initialize the eco-weather bot with LangChain ChatOllama.
    
    Sets up the LLM with tool binding capabilities.
    
    Returns:
        ChatOllama instance bound with weather/air quality tool
    """
    llm = ChatOllama(model="phi4:mini", temperature=0.7)
    tools = [fetch_weather_and_air_quality]
    llm_with_tools = llm.bind_tools(tools)
    return llm_with_tools


def process_tool_calls(llm_with_tools: ChatOllama, messages: list[BaseMessage], 
                       response: BaseMessage) -> str:
    """
    Process tool calls from LLM response and generate final answer.
    
    Executes any tool calls requested by the model, collects results,
    and calls the model again with tool outputs for synthesis.
    
    Args:
        llm_with_tools: ChatOllama instance with bound tools
        messages: Current message history
        response: Response from LLM containing potential tool calls
    
    Returns:
        Final synthesized response from the model
    """
    if not hasattr(response, 'tool_calls') or not response.tool_calls:
        return response.content
    
    # Add the assistant's response to message history
    messages.append(response)
    
    # Execute each tool call
    for tool_call in response.tool_calls:
        if tool_call["name"] == "fetch_weather_and_air_quality":
            tool_result = fetch_weather_and_air_quality(
                latitude=tool_call["args"]["latitude"],
                longitude=tool_call["args"]["longitude"]
            )
            
            # Add tool result to message history
            messages.append(ToolMessage(
                content=tool_result,
                tool_call_id=tool_call["id"]
            ))
    
    # Get final response from model with tool results
    final_response = llm_with_tools.invoke(messages)
    return final_response.content


def run_eco_weather_chat(user_query: str, latitude: Optional[float] = None, 
                        longitude: Optional[float] = None) -> str:
    """
    Run a complete conversation turn with the eco-weather assistant.
    
    Handles message history, tool calls, and intelligent routing to determine
    if a tool call is necessary or if the query can be answered directly.
    
    Args:
        user_query: User's question or request
        latitude: Optional latitude for location-based queries
        longitude: Optional longitude for location-based queries
    
    Returns:
        Assistant's response string
    """
    
    # System message with eco-friendly persona and guidelines
    system_message = SystemMessage(
        content="""You are an Eco-Friendly Health & Weather Assistant. You provide weather and air quality insights 
with a focus on environmental health and sustainable living recommendations.

IMPORTANT GUIDELINES:
1. When analyzing air quality data:
   - If US AQI > 100: WARN the user about respiratory impacts, advise staying indoors, and suggest wearing masks if going out.
   - If US AQI ≤ 100: Encourage eco-friendly outdoor activities like walking or cycling instead of driving, and mention how this preserves local air quality.
2. Provide temperature and UV index context for activity safety.
3. Be concise, friendly, and health-conscious.
4. If the user asks something not requiring weather data, answer directly without using tools."""
    )
    
    # Initialize bot
    llm_with_tools = initialize_eco_bot()
    
    # Build message history
    messages: list[BaseMessage] = [system_message]
    
    # Prepare user query with optional coordinates
    if latitude is not None and longitude is not None:
        full_query = f"{user_query}\n\nLocation: Latitude {latitude}, Longitude {longitude}"
    else:
        full_query = user_query
    
    messages.append(HumanMessage(content=full_query))
    
    # Get initial response
    response = llm_with_tools.invoke(messages)
    
    # Check if tool calls are needed
    if hasattr(response, 'tool_calls') and response.tool_calls:
        return process_tool_calls(llm_with_tools, messages, response)
    else:
        return response.content


if __name__ == "__main__":
    print("=" * 80)
    print("ECO-FRIENDLY WEATHER & HEALTH ASSISTANT - TEST RUN")
    print("=" * 80)
    
    # Test 1: Location-based query requiring tool call (jogging with coordinates)
    print("\n" + "─" * 80)
    print("TEST 1: Location-Based Jogging Query (Requires Tool Call)")
    print("─" * 80)
    print("\nUser Query: Should I go out for a jog this morning?")
    print("Location: Latitude 33.57, Longitude -7.58 (Fez, Morocco)")
    
    response1 = run_eco_weather_chat(
        user_query="Should I go out for a jog this morning? What conditions do you recommend?",
        latitude=33.57,
        longitude=-7.58
    )
    print(f"\nAssistant Response:\n{response1}")
    
    # Test 2: General question NOT requiring tool call (intelligent routing)
    print("\n" + "─" * 80)
    print("TEST 2: General Environmental Question (No Tool Call Needed)")
    print("─" * 80)
    print("\nUser Query: What are the environmental benefits of cycling compared to driving?")
    
    response2 = run_eco_weather_chat(
        user_query="What are the environmental benefits of cycling compared to driving?"
    )
    print(f"\nAssistant Response:\n{response2}")
    
    print("\n" + "=" * 80)
    print("TEST EXECUTION COMPLETED")
    print("=" * 80)
