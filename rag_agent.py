import os
import logging
from datetime import datetime
import google.generativeai as genai
import json

from weather_fetcher import get_city_weather, get_all_cities, fetch_and_prepare_weather_data

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_API_KEY = "GEMINI_API_KEY"
genai.configure(api_key=GEMINI_API_KEY)

# System prompt for the RAG agent
SYSTEM_PROMPT = """
你是一個專業的露營顧問機器人，名字叫「露營天氣達人」。你的專長是根據台灣各地的天氣預報，為使用者提供露營建議。

請根據以下天氣資料作答，禁止自行推測、杜撰或添加未提供的資訊。若資料中找不到使用者提問的地區或時間，請直接告知查無資料。

回答規則：
1. 保持友善、專業，回答內容控制在2~4句。
2. 必須根據天氣資料，指出是否適合露營與主要原因（如降雨、雷雨、晴朗等）。
3. 禁止冗長開場或結尾，如「很高興為您服務」等。
4. 若不適合露營，請簡單建議改期或提醒注意安全。
5. 僅能參考提供的天氣資料，不得自行推測天氣或日期資訊。
6. 資料來源日：{current_date}；資料最後更新時間：{last_updated}

今天日期是：{current_date}

最後更新的天氣資料時間：{last_updated}
"""

def get_weather_context(city_name=None):
    """
    Generate context information about weather based on user query.
    
    Args:
        city_name: Optional specific city to get weather for
        
    Returns:
        String with formatted weather context
    """
    try:
        # If no specific city, get overview of all cities
        if not city_name:
            all_data = fetch_and_prepare_weather_data()
            context = "目前有以下縣市的天氣資料：\n"
            
            suitable_cities = []
            for city, data in all_data.items():
                # Check if any days in the next 3 days are suitable
                next_3_days = data['forecasts'][:3] if len(data['forecasts']) >= 3 else data['forecasts']
                if any(day['is_suitable_for_camping'] for day in next_3_days):
                    suitable_cities.append(city)
            
            if suitable_cities:
                context += f"\n近三天適合露營的縣市有：{', '.join(suitable_cities)}\n"
            else:
                context += "\n近三天所有縣市的天氣狀況都不太適合露營。\n"
                
            # Add a sample of detailed data for one city
            sample_city = "臺北市" if "臺北市" in all_data else list(all_data.keys())[0]
            context += f"\n以下是{sample_city}的天氣資料範例：\n"
            context += format_city_weather(all_data[sample_city])
            
            return context
        
        # Get specific city data
        city_data = get_city_weather(city_name)
        if not city_data:
            # Try to find a similar city name
            all_cities = get_all_cities()
            for city in all_cities:
                if city_name in city or city in city_name:
                    city_data = get_city_weather(city)
                    city_name = city
                    break
        
        if not city_data:
            return f"找不到 '{city_name}' 的天氣資料。可用的縣市有：{', '.join(get_all_cities())}"
        
        return format_city_weather(city_data, city_name)
        
    except Exception as e:
        logging.error(f"Error getting weather context: {e}")
        return "抱歉，無法獲取天氣資料。系統可能暫時發生錯誤。"

def format_city_weather(city_data, city_name=None):
    """
    Format city weather data in a readable format.
    
    Args:
        city_data: Weather data for a city
        city_name: Optional city name
        
    Returns:
        String with formatted weather data
    """
    if not city_name:
        city_name = city_data.get('name', "該地區")
    
    result = f"{city_name}未來一週天氣預報：\n\n"
    
    for day in city_data['forecasts']:
        date = day['display_date']
        suitable = "適合" if day['is_suitable_for_camping'] else "不適合"
        reason = day['suitability_reasons']
        
        result += f"📅 {date}：{suitable}露營\n"
        result += f"📝 {reason}\n"
        
        # Add detailed weather for this day
        for period in day['periods']:
            time_period = period['time_period']
            temp_range = f"{period['min_temp']}°C - {period['max_temp']}°C"
            precip = f"{period['precipitation_prob']}%" if period['precipitation_prob'] != '-' else "N/A"
            weather = period['weather']
            
            result += f"🕒 {time_period}：{weather}，溫度 {temp_range}，降雨機率 {precip}\n"
        
        result += "\n"
    
    return result

def query_llm(user_message, city_context=None):
    try:
        # Prepare system prompt
        current_date = datetime.now().strftime("%Y-%m-%d")
        weather_data = fetch_and_prepare_weather_data()
        last_updated = "未知" if weather_data.get("last_updated") is None else weather_data.get("last_updated").strftime("%Y-%m-%d %H:%M:%S")

        system_prompt = SYSTEM_PROMPT.format(
            current_date=current_date,
            last_updated=last_updated
        )

        # Create model
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Build full prompt
        full_prompt = f"{system_prompt}\n"
        if city_context:
            full_prompt += f"\n以下是相關的天氣資料，請根據這些資料回答使用者：\n\n{city_context}\n"
        full_prompt += f"\n使用者提問：{user_message}\n"

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,  
                max_output_tokens=300,  
            )
)

        return response.text

    except Exception as e:
        logging.error(f"Error querying LLM: {e}")
        return "抱歉，我暫時無法處理您的請求。請稍後再試。"
def process_query(user_query):
    """
    Process a user query and return a response.
    
    Args:
        user_query: User's question
        
    Returns:
        Response from the LLM
    """
    # Extract potential location from query
    cities = get_all_cities()
    
    mentioned_city = None
    for city in cities:
        if city in user_query:
            mentioned_city = city
            break
    
    # Get weather context if a city is mentioned
    context = None
    if mentioned_city:
        context = get_weather_context(mentioned_city)
    else:
        # Check for general weather queries
        weather_keywords = ["天氣", "氣象", "溫度", "下雨", "降雨", "露營", "適合", "哪裡", "何處", "推薦"]
        if any(keyword in user_query for keyword in weather_keywords):
            context = get_weather_context()
    
    # Get response from LLM
    response = query_llm(user_query, context)
    
    return response

# For backwards compatibility with your existing code
def answer_question_with_weather_info(question):
    """
    Alias for process_query to maintain compatibility with your existing app.py
    """
    return process_query(question)

if __name__ == "__main__":
    # Test the module
    test_query = "台北市這週末適合露營嗎？"
    response = process_query(test_query)
    print(f"Query: {test_query}")
    print(f"Response: {response}")