import os
import json
import pandas as pd
from typing import Dict, Any, List, Optional
from openai import OpenAI

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
)


def generate_data_insights(df_summary: Dict, analysis_results: Dict) -> str:
    """Generate AI-powered insights from data analysis"""
    
    prompt = f"""You are a professional data analyst. Analyze the following data and provide useful insights and recommendations.

Data Summary:
- Row Count: {df_summary.get('row_count', 'Unknown')}
- Column Count: {df_summary.get('column_count', 'Unknown')}
- Columns: {', '.join(df_summary.get('columns', [])[:10])}

Analysis Results:
{json.dumps(analysis_results, ensure_ascii=False, indent=2, default=str)[:3000]}

Please provide:
1. Top 5 key observations from the data
2. 3 actionable recommendations
3. Data strengths and weaknesses
4. Suggestions for improvement

Format your response in a clear, organized manner with bullet points."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert data analyst providing professional insights and recommendations. Be concise but thorough."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        result = response.choices[0].message.content
        if result:
            return result
        return "No insights generated. Please try again."
    except Exception as e:
        return f"Error generating analysis: {str(e)}"


def chat_about_data(user_question: str, df_info: Dict, 
                    chat_history: List[Dict] = None) -> str:
    """Interactive chat about the data"""
    
    context = f"""Available Data Information:
- Row Count: {df_info.get('row_count', 'Unknown')}
- Column Count: {df_info.get('column_count', 'Unknown')}
- Column Names: {', '.join(df_info.get('columns', []))}
- Data Types: {json.dumps(df_info.get('dtypes', {}), ensure_ascii=False)}
- Statistical Summary: {json.dumps(df_info.get('numeric_summary', {}), ensure_ascii=False, default=str)[:1500]}"""

    messages = [
        {"role": "system", "content": f"""You are an intelligent assistant specialized in data analysis. 
You have information about the user's dataset.
Answer their questions accurately and helpfully.
If asked about predictions, provide your analysis based on the available data.
Be concise but informative.

{context}"""}
    ]
    
    if chat_history:
        for msg in chat_history[-5:]:
            messages.append({"role": "user", "content": msg.get('user', '')})
            messages.append({"role": "assistant", "content": msg.get('assistant', '')})
    
    messages.append({"role": "user", "content": user_question})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500
        )
        result = response.choices[0].message.content
        if result:
            return result
        return "I couldn't generate a response. Please try rephrasing your question."
    except Exception as e:
        return f"Error: {str(e)}"


def generate_comparison_insights(comparison_data: Dict) -> str:
    """Generate insights from period comparison"""
    
    prompt = f"""You are a professional data analyst. Analyze the following data comparison between two different periods and provide useful insights:

Comparison Data:
{json.dumps(comparison_data, ensure_ascii=False, indent=2, default=str)[:3000]}

Please provide:
1. Key changes between the two periods
2. Notable trends observed
3. Recommendations based on the changes
4. Warnings if there are significant negative changes"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert data analyst comparing different time periods. Be clear and actionable."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        result = response.choices[0].message.content
        if result:
            return result
        return "No comparison insights generated. Please try again."
    except Exception as e:
        return f"Error: {str(e)}"


def generate_prediction_insights(prediction_data: Dict, historical_context: str = "") -> str:
    """Generate insights about predictions"""
    
    prompt = f"""You are a professional data analyst. Analyze the following prediction results and provide insights:

Prediction Data:
{json.dumps(prediction_data, ensure_ascii=False, indent=2, default=str)[:2000]}

Historical Context:
{historical_context[:1000] if historical_context else 'No historical context available'}

Please provide:
1. Prediction accuracy assessment
2. Expected trends
3. Risk factors to consider
4. Recommendations for decision making"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert data analyst providing prediction insights. Be practical and clear."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        result = response.choices[0].message.content
        if result:
            return result
        return "No prediction insights generated. Please try again."
    except Exception as e:
        return f"Error: {str(e)}"


def analyze_data_quality(df_info: Dict) -> str:
    """Analyze data quality and provide recommendations"""
    
    prompt = f"""You are a data quality expert. Analyze the following dataset information and provide a quality assessment:

Dataset Info:
{json.dumps(df_info, ensure_ascii=False, indent=2, default=str)[:3000]}

Please provide:
1. Overall data quality score (estimate)
2. Potential data quality issues
3. Recommendations for data cleaning
4. Best practices for this type of data"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a data quality expert. Provide actionable insights."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        result = response.choices[0].message.content
        if result:
            return result
        return "No quality assessment generated. Please try again."
    except Exception as e:
        return f"Error: {str(e)}"
