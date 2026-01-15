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
    
    prompt = f"""أنت محلل بيانات محترف. قم بتحليل البيانات التالية وتقديم رؤى وتوصيات مفيدة باللغة العربية.

ملخص البيانات:
- عدد الصفوف: {df_summary.get('row_count', 'غير محدد')}
- عدد الأعمدة: {df_summary.get('column_count', 'غير محدد')}
- الأعمدة: {', '.join(df_summary.get('columns', [])[:10])}

نتائج التحليل:
{json.dumps(analysis_results, ensure_ascii=False, indent=2, default=str)[:3000]}

قدم:
1. أهم 5 ملاحظات من البيانات
2. 3 توصيات عملية
3. نقاط القوة والضعف في البيانات
4. اقتراحات للتحسين

اكتب الرد بشكل منظم ومختصر."""

    try:
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "أنت محلل بيانات خبير تقدم رؤى وتوصيات احترافية باللغة العربية."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ في توليد التحليل: {str(e)}"


def chat_about_data(user_question: str, df_info: Dict, 
                    chat_history: List[Dict] = None) -> str:
    """Interactive chat about the data"""
    
    context = f"""معلومات عن البيانات المتاحة:
- عدد الصفوف: {df_info.get('row_count', 'غير محدد')}
- عدد الأعمدة: {df_info.get('column_count', 'غير محدد')}
- أسماء الأعمدة: {', '.join(df_info.get('columns', []))}
- أنواع البيانات: {json.dumps(df_info.get('dtypes', {}), ensure_ascii=False)}
- ملخص إحصائي: {json.dumps(df_info.get('numeric_summary', {}), ensure_ascii=False, default=str)[:1500]}"""

    messages = [
        {"role": "system", "content": f"""أنت مساعد ذكي متخصص في تحليل البيانات. 
لديك معلومات عن مجموعة البيانات التي يتعامل معها المستخدم.
أجب على أسئلته بشكل دقيق ومفيد باللغة العربية.
إذا سأل عن تنبؤات، قدم تحليلك بناءً على البيانات المتاحة.

{context}"""}
    ]
    
    if chat_history:
        for msg in chat_history[-5:]:
            messages.append({"role": "user", "content": msg.get('user', '')})
            messages.append({"role": "assistant", "content": msg.get('assistant', '')})
    
    messages.append({"role": "user", "content": user_question})
    
    try:
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            max_completion_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"


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
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "أنت محلل بيانات خبير تقارن بين فترات زمنية مختلفة."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=1500
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
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "أنت خبير في تحليل التنبؤات والنماذج الإحصائية."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=1500
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
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "أنت مساعد يشرح التقارير التقنية بلغة بسيطة."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"
