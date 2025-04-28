import requests
import json
from datetime import datetime, timedelta
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Central Weather Bureau API configuration
API_KEY = "API_KEY"
API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"

# Cache to store weather info and camping suitability
# Will store data with a timestamp to handle refreshes
weather_data_cache = {
    "last_updated": None,
    "data": {}
}

def is_number(value):
    """Check if a value can be converted to a number"""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False

def fetch_and_prepare_weather_data(force_refresh=False):
    """
    Fetch weather data from CWB and calculate camping suitability.
    
    Args:
        force_refresh: If True, force a refresh even if cache is recent
        
    Returns:
        Dictionary of processed weather data by location
    """
    global weather_data_cache
    
    # Check if we need to refresh the cache (older than 3 hours or forced)
    current_time = datetime.now()
    needs_refresh = (
        force_refresh or 
        weather_data_cache["last_updated"] is None or
        (current_time - weather_data_cache["last_updated"]).total_seconds() > 10800
    )
    
    if not needs_refresh and weather_data_cache["data"]:
        logging.info("Using cached weather data")
        return weather_data_cache["data"]
    
    logging.info("Fetching fresh weather data from CWB API")
    
    params = {
        "Authorization": API_KEY,
        "format": "JSON",
    }
    
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()  # Raise an exception for 4XX/5XX responses
        data = response.json()
        
        if data.get("success") != "true":
            raise Exception(f"API returned unsuccessful response: {data}")
            
        # Process the received data
        processed_data = process_weather_data(data)
        
        # Add location name to each entry
        for location_name, location_data in processed_data.items():
            location_data['name'] = location_name
        
        # Update cache with new data and timestamp
        weather_data_cache["data"] = processed_data
        weather_data_cache["last_updated"] = current_time
        
        return processed_data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching weather data: {e}")
        # Return cached data if available, otherwise empty dict
        return weather_data_cache["data"] if weather_data_cache["data"] else {}
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        logging.error(traceback.format_exc())
        return weather_data_cache["data"] if weather_data_cache["data"] else {}

def process_weather_data(data):
    """
    Process raw weather API data into a more useful format and calculate camping suitability.
    
    Args:
        data: Raw JSON data from the weather API
        
    Returns:
        Dictionary with processed weather information by location
    """
    processed_data = {}
    
    try:
        # Try to identify the data structure
        locations = []
        
        # Try different known structure paths
        if "records" in data:
            records = data["records"]
            
            # First structure type: records -> Locations -> Location
            if "Locations" in records and isinstance(records["Locations"], list) and len(records["Locations"]) > 0:
                if "Location" in records["Locations"][0] and isinstance(records["Locations"][0]["Location"], list):
                    locations = records["Locations"][0]["Location"]
                    logging.info("Using Locations[0].Location structure")
            
            # Second structure type: records -> location
            elif "location" in records and isinstance(records["location"], list):
                locations = records["location"]
                logging.info("Using location structure")
            
            # Third structure type: records -> Location
            elif "Location" in records and isinstance(records["Location"], list):
                locations = records["Location"]
                logging.info("Using Location structure")
        
        if not locations:
            logging.error("Could not find location data in API response")
            return {}
        
        for location in locations:
            # Extract location name, with fallbacks
            city_name = None
            if "LocationName" in location:
                city_name = location["LocationName"]
            elif "locationName" in location:
                city_name = location["locationName"]
            elif "name" in location:
                city_name = location["name"]
            
            if not city_name:
                logging.warning(f"Could not find location name in {json.dumps(location)[:100]}...")
                continue
            
            # Extract weather elements
            weather_elements = {}
            
            # Try to find weather elements array with different possible names
            elements_array = None
            if "WeatherElement" in location:
                elements_array = location["WeatherElement"]
            elif "weatherElement" in location:
                elements_array = location["weatherElement"]
            
            if not elements_array or not isinstance(elements_array, list):
                logging.warning(f"Could not find weather elements for {city_name}")
                continue
            
            # Map element names to standardized names
            element_mapping = {
                # Standard API names
                "平均溫度": "平均溫度",
                "最高溫度": "最高溫度",
                "最低溫度": "最低溫度",
                "平均相對濕度": "平均相對濕度",
                "12小時降雨機率": "12小時降雨機率",
                "天氣現象": "天氣現象",
                "天氣預報綜合描述": "天氣預報綜合描述",
                "風向": "風向",
                "風速": "風速",
                
                # Alternative names sometimes used
                "T": "平均溫度",
                "Tx": "最高溫度",
                "Tn": "最低溫度",
                "RH": "平均相對濕度",
                "PoP12h": "12小時降雨機率",
                "Wx": "天氣現象",
                "WeatherDescription": "天氣預報綜合描述",
                "WD": "風向",
                "WS": "風速"
            }
            
            # Process elements
            for element in elements_array:
                element_name = None
                if "ElementName" in element:
                    element_name = element["ElementName"]
                elif "elementName" in element:
                    element_name = element["elementName"]
                
                if not element_name:
                    continue
                
                # Get standardized name
                std_name = element_mapping.get(element_name, element_name)
                
                # Get time data with different possible field names
                time_data = None
                if "Time" in element:
                    time_data = element["Time"]
                elif "time" in element:
                    time_data = element["time"]
                
                if not time_data or not isinstance(time_data, list):
                    continue
                
                weather_elements[std_name] = time_data
            
            # Get forecast data for next few days
            forecasts = []
            
            # Use startTime to group data by day (up to 7 days)
            forecast_days = set()
            
            # Try to find start times in either 平均溫度 or T element
            temp_element = weather_elements.get("平均溫度", [])
            if not temp_element:
                # Try alternative name
                temp_element = weather_elements.get("T", [])
            
            if not temp_element:
                logging.warning(f"Could not find temperature data for {city_name}")
                continue
            
            for time_slot in temp_element:
                # Extract start time with different possible field names
                start_time_str = None
                if "StartTime" in time_slot:
                    start_time_str = time_slot["StartTime"]
                elif "startTime" in time_slot:
                    start_time_str = time_slot["startTime"]
                
                if not start_time_str:
                    continue
                
                # Handle timezone in the timestamp
                start_time_str = start_time_str.replace("+08:00", "")
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                    day_key = start_time.strftime("%Y-%m-%d")
                    forecast_days.add(day_key)
                except ValueError:
                    logging.warning(f"Invalid datetime format: {start_time_str}")
                    continue
                
                if len(forecast_days) > 7:  # Limit to 7 days
                    break
                    
            # Process each day
            for day_key in sorted(forecast_days):
                day_forecasts = []
                
                # Process each 12-hour period
                for i, time_slot in enumerate(temp_element):
                    # Extract start and end times
                    start_time_str = time_slot.get("StartTime", time_slot.get("startTime"))
                    end_time_str = time_slot.get("EndTime", time_slot.get("endTime"))
                    
                    if not start_time_str or not end_time_str:
                        continue
                    
                    # Clean up timezone info
                    start_time_str = start_time_str.replace("+08:00", "")
                    end_time_str = end_time_str.replace("+08:00", "")
                    
                    try:
                        start_time = datetime.fromisoformat(start_time_str)
                        end_time = datetime.fromisoformat(end_time_str)
                    except ValueError:
                        continue
                    
                    if start_time.strftime("%Y-%m-%d") != day_key:
                        continue
                    
                    # Format times for display
                    time_period = f"{start_time.strftime('%m/%d %H:%M')} - {end_time.strftime('%H:%M')}"
                    
                    # Create forecast object with safe extraction
                    forecast = {
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "time_period": time_period,
                        "avg_temp": extract_value(weather_elements, "平均溫度", i, ["Temperature", "value"], "N/A"),
                        "max_temp": extract_value(weather_elements, "最高溫度", i, ["MaxTemperature", "value"], "N/A"),
                        "min_temp": extract_value(weather_elements, "最低溫度", i, ["MinTemperature", "value"], "N/A"),
                        "relative_humidity": extract_value(weather_elements, "平均相對濕度", i, ["RelativeHumidity", "value"], "N/A"),
                        "weather": extract_value(weather_elements, "天氣現象", i, ["Weather", "value"], "N/A"),
                        "weather_code": extract_value(weather_elements, "天氣現象", i, ["WeatherCode", "measures"], "N/A"),
                        "description": extract_value(weather_elements, "天氣預報綜合描述", i, ["WeatherDescription", "value"], "N/A"),
                    }
                    
                    # Handle precipitation probability
                    precip = extract_value(weather_elements, "12小時降雨機率", i, ["ProbabilityOfPrecipitation", "value"], "0")
                    forecast["precipitation_prob"] = 0 if precip == "-" else int(precip)
                    
                    # Extract wind data
                    forecast["wind_direction"] = extract_value(weather_elements, "風向", i, ["WindDirection", "value"], "N/A")
                    forecast["wind_speed"] = extract_value(weather_elements, "風速", i, ["WindSpeed", "value"], "0")
                    
                    day_forecasts.append(forecast)
                
                # Calculate camping suitability for this day
                if day_forecasts:
                    is_suitable = judge_camping_suitability(day_forecasts)
                    
                    forecasts.append({
                        "date": day_key,
                        "display_date": datetime.fromisoformat(day_key).strftime("%m/%d (%a)"),
                        "periods": day_forecasts,
                        "is_suitable_for_camping": is_suitable,
                        "suitability_reasons": get_suitability_reasons(day_forecasts, is_suitable)
                    })
            
            # Get location metadata
            geocode = location.get("Geocode", location.get("geocode", "N/A"))
            latitude = location.get("Latitude", location.get("lat", "N/A"))
            longitude = location.get("Longitude", location.get("lon", "N/A"))
            
            processed_data[city_name] = {
                "geocode": geocode,
                "latitude": latitude,
                "longitude": longitude,
                "forecasts": forecasts
            }
    
    except KeyError as e:
        logging.error(f"Error processing weather data (missing key): {e}")
        logging.error(traceback.format_exc())
    except Exception as e:
        logging.error(f"Unexpected error processing weather data: {e}")
        logging.error(traceback.format_exc())
    
    return processed_data

def extract_value(weather_elements, element_name, index, possible_keys, default):
    """
    Safely extract a value from weather elements with multiple possible keys.
    
    Args:
        weather_elements: Dictionary of weather elements
        element_name: Name of the element to extract from
        index: Index in the time array
        possible_keys: List of possible keys for the value
        default: Default value if not found
        
    Returns:
        Extracted value or default
    """
    if element_name not in weather_elements:
        return default
    
    if index >= len(weather_elements[element_name]):
        return default
    
    time_slot = weather_elements[element_name][index]
    
    # Check for ElementValue or elementValue
    element_value = None
    if "ElementValue" in time_slot and isinstance(time_slot["ElementValue"], list):
        element_value = time_slot["ElementValue"]
    elif "elementValue" in time_slot and isinstance(time_slot["elementValue"], list):
        element_value = time_slot["elementValue"]
    
    if not element_value or not len(element_value) > 0:
        return default
    
    # Try each possible key
    for key in possible_keys:
        if key in element_value[0]:
            return element_value[0][key]
    
    return default

def judge_camping_suitability(forecasts):
    """
    Determine if weather conditions are suitable for camping.
    
    Args:
        forecasts: List of forecast periods for a day
        
    Returns:
        Boolean indicating suitability for camping
    """
    # Check precipitation probability
    if any(forecast["precipitation_prob"] > 40 for forecast in forecasts):
        return False
    
    # Check temperature range (too cold or too hot is bad for camping)
    if any(is_number(forecast["min_temp"]) and float(forecast["min_temp"]) < 15 for forecast in forecasts):
        return False
    
    if any(is_number(forecast["max_temp"]) and float(forecast["max_temp"]) > 32 for forecast in forecasts):
        return False
    
    # Check for extreme weather conditions
    bad_weather_keywords = ["雷雨", "豪雨", "大雨", "暴風", "強風"]
    if any(any(keyword in str(forecast["weather"]) for keyword in bad_weather_keywords) for forecast in forecasts):
        return False
    
    # Check wind conditions
    if any(is_number(forecast["wind_speed"]) and float(forecast["wind_speed"]) > 8 for forecast in forecasts):
        return False
    
    # If no rejection criteria are met, it's suitable
    return True

def get_suitability_reasons(forecasts, is_suitable):
    """
    Generate human-readable reasons for the camping suitability judgment.
    
    Args:
        forecasts: List of forecast periods for a day
        is_suitable: Boolean indicating if the day is suitable for camping
        
    Returns:
        String explaining why the day is suitable or unsuitable for camping
    """
    if is_suitable:
        return "天氣條件適合露營：溫度適宜，降雨機率低，無極端天氣。"
    
    reasons = []
    
    # Check precipitation probability
    max_precip = max((forecast["precipitation_prob"] for forecast in forecasts), default=0)
    if max_precip > 40:
        reasons.append(f"降雨機率高 ({max_precip}%)")
    
    # Check temperature range
    min_temps = [float(forecast["min_temp"]) for forecast in forecasts if is_number(forecast["min_temp"])]
    max_temps = [float(forecast["max_temp"]) for forecast in forecasts if is_number(forecast["max_temp"])]
    
    if min_temps and min(min_temps) < 15:
        reasons.append(f"溫度過低 (最低 {min(min_temps)}°C)")
    
    if max_temps and max(max_temps) > 32:
        reasons.append(f"溫度過高 (最高 {max(max_temps)}°C)")
    
    # Check for extreme weather conditions
    bad_weather_keywords = ["雷雨", "豪雨", "大雨", "暴風", "強風"]
    for forecast in forecasts:
        for keyword in bad_weather_keywords:
            if keyword in str(forecast["weather"]):
                reasons.append(f"有{keyword}天氣")
                break
    
    # Check wind conditions
    wind_speeds = [float(forecast["wind_speed"]) for forecast in forecasts if is_number(forecast["wind_speed"])]
    if wind_speeds and max(wind_speeds) > 8:
        reasons.append(f"風速過大 ({max(wind_speeds)} m/s)")
    
    return "不適合露營：" + "，".join(reasons) if reasons else "不適合露營：綜合天氣條件不佳"

def get_city_weather(city_name):
    """
    Get weather and camping suitability info for a specific city.
    
    Args:
        city_name: Name of the city/county to get weather for
        
    Returns:
        Dictionary with weather data for the city, or None if not found
    """
    data = fetch_and_prepare_weather_data()
    return data.get(city_name)

def get_all_cities():
    """
    Get a list of all available cities/counties.
    
    Returns:
        List of city/county names
    """
    data = fetch_and_prepare_weather_data()
    return sorted(list(data.keys()))

if __name__ == "__main__":
    # Test the module
    data = fetch_and_prepare_weather_data(force_refresh=True)
    print(f"Found data for {len(data)} locations")
    
    # Check if 連江縣 is in the data
    if "連江縣" in data:
        print("\n連江縣資料存在！")
    else:
        print("\n找不到連江縣資料")
        print(f"可用的地區: {', '.join(data.keys())}")
    
    # Print a sample
    if data:
        sample_city = "連江縣" if "連江縣" in data else list(data.keys())[0]
        print(f"\n{sample_city}的資料範例:")
        print(json.dumps(data[sample_city], ensure_ascii=False, indent=2))