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
- Rows: {df_summary.get('row_count', 'Unknown')}
- Columns: {df_summary.get('column_count', 'Unknown')}
- Column names: {', '.join(df_summary.get('columns', [])[:10])}

Analysis Results:
{json.dumps(analysis_results, ensure_ascii=False, indent=2, default=str)[:3000]}

Provide:
1. Top 5 key observations from the data
2. 3 actionable recommendations
3. Strengths and weaknesses of the data
4. Suggestions for improvement

Write the response in a clear and organized manner."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert data analyst providing professional insights and recommendations."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        result = response.choices[0].message.content
        return result if result else "Unable to generate insights. Please try again."
    except Exception as e:
        return f"Sorry, an error occurred while generating analysis: {str(e)}"


def chat_about_data(user_question: str, df_info: Dict, 
                    chat_history: List[Dict] = None) -> str:
    """Interactive chat about the data"""
    
    context = f"""Available data information:
- Rows: {df_info.get('row_count', 'Unknown')}
- Columns: {df_info.get('column_count', 'Unknown')}
- Column names: {', '.join(df_info.get('columns', []))}
- Data types: {json.dumps(df_info.get('dtypes', {}), ensure_ascii=False)}
- Statistical summary: {json.dumps(df_info.get('numeric_summary', {}), ensure_ascii=False, default=str)[:1500]}"""

    messages = [
        {"role": "system", "content": f"""You are an intelligent data analysis assistant.
You have information about the user's dataset.
Answer their questions accurately and helpfully.
If they ask about predictions, provide your analysis based on available data.

{context}"""}
    ]
    
    if chat_history:
        for msg in chat_history[-5:]:
            messages.append({"role": "user", "content": msg.get('user', '')})
            messages.append({"role": "assistant", "content": msg.get('assistant', '')})
    
    messages.append({"role": "user", "content": user_question})
    
    try:
        if not AI_INTEGRATIONS_OPENAI_API_KEY or not AI_INTEGRATIONS_OPENAI_BASE_URL:
            return "AI service is not configured. Please contact support."
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500
        )
        result = response.choices[0].message.content
        return result if result else "I apologize, but I couldn't generate a response. Please try again."
    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            return f"Connection error. Please try again later. Details: {error_msg}"
        return f"Sorry, an error occurred: {error_msg}"


def generate_comparison_insights(comparison_data: Dict) -> str:
    """Generate insights from period comparison"""
    
    prompt = f"""أنت محلل بيانات محترف. قم بتحليل مقارنة البيانات التالية بين فترتين مختلفتين وقدم رؤى مفيدة:

بيانات المقارنة:
{json.dumps(comparison_data, ensure_ascii=False, indent=2, default=str)[:3000]}

قدم:
1. أهم التغييرات بين الفترتين
2. الاتجاهات الملحوظة
3. توصيات بناءً على التغييرات
4. تحذيرات إذا كانت هناك تغييرات سلبية كبيرة"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت محلل بيانات خبير تقارن بين فترات زمنية مختلفة."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"


def generate_prediction_insights(prediction_data: Dict, historical_context: str = "") -> str:
    """Generate insights about predictions"""
    
    prompt = f"""أنت محلل بيانات متخصص في التنبؤات. حلل نتائج التنبؤ التالية:

نتائج التنبؤ:
{json.dumps(prediction_data, ensure_ascii=False, indent=2, default=str)}

{f"السياق التاريخي: {historical_context}" if historical_context else ""}

قدم:
1. تفسير للتنبؤات
2. مدى موثوقية التنبؤ
3. العوامل المؤثرة
4. توصيات للمستقبل
5. تحذيرات أو ملاحظات مهمة"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت خبير في تحليل التنبؤات والنماذج الإحصائية."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"


def generate_cleaning_report(cleaning_report: Dict) -> str:
    """Generate a user-friendly cleaning report"""
    
    prompt = f"""حوّل تقرير تنظيف البيانات التالي إلى تقرير مفهوم ومفيد للمستخدم العادي:

تقرير التنظيف:
{json.dumps(cleaning_report, ensure_ascii=False, indent=2)}

اكتب التقرير بأسلوب بسيط ومفهوم، واذكر:
1. ما تم تنظيفه
2. جودة البيانات بعد التنظيف
3. أي ملاحظات مهمة"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت مساعد يشرح التقارير التقنية بلغة بسيطة."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"
