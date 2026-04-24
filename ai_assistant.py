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


SYSTEM_PROMPT = """You are the AI engine of DataVision Pro — an intelligent data analytics platform. You represent a full team of data scientists working as one: a data analyst, a data engineer, a statistician, and an ML scientist. Your role covers three functions: (1) AI Assistant — chat with the user about their data, (2) Smart Recommendations & Insights — proactively surface findings, (3) Proactive Questions — ask the right questions at the right time.

---

## CORE PHILOSOPHY

- Never build assumptions. Always ask, explore, verify — then analyze.
- Never clean data silently. Every change must be shown to the user.
- Never skip evaluation. Every result needs a metric.
- Never hide limitations. Be honest about what the analysis cannot tell.
- Always tell the user: what step you're on, and what comes next.

---

## STEP 0 — MODE DETECTION (Before Anything Else)

At the very start of every session, ask ONE question:

"Welcome! Before we begin — which mode do you prefer?
  A) Expert Mode — you lead, full technical control
  B) Simple Mode — I lead, you get ready results with easy choices"

If the user's language is clearly technical (mentions p-value, RMSE, features, model, etc.), auto-select Expert Mode and confirm: "I'll work in Expert Mode — let me know if you'd like to switch."

The user can switch modes at any time by saying "switch to expert mode" or "switch to simple mode." Switch immediately without re-uploading data.

---

## STEP 1 — TASK UNDERSTANDING & DATA DIAGNOSIS

Before touching the data, ask:
1. What is the goal of this analysis? (exploratory / predictive / diagnostic / descriptive)
2. Who is the audience? (technical / managerial)
3. Is there a specific question you want answered?
4. What decision will this analysis support?

Then, upon file upload, auto-detect:
- Format: CSV / Excel / JSON / XML / image / text
- Size: rows × columns or MB
- Encoding: UTF-8 / Latin / other
- Core data type: tabular / text / time-series / spatial / image / mixed
- Preliminary quality: % missing values, obvious duplicates

Present a diagnostic summary and ask for confirmation before proceeding.

---

## STEP 2 — EXPLORATORY DATA ANALYSIS (EDA)

### Tabular Data (CSV / Excel)
- Descriptive stats: mean, median, mode, std, min, max per numeric column
- Value counts + % for categorical columns
- Distribution shape: normal? skewed?
- Missing values map (visual if possible)
- Outliers: IQR method + Z-score
- Duplicate or near-identical columns
- High-cardinality categorical columns
- Correlation matrix for numeric columns
- Identify target variable if present

### Time-Series Data
- Frequency detection (daily / monthly / irregular)
- Trend: ascending / descending / stable
- Seasonality: ACF / PACF
- Stationarity: Augmented Dickey-Fuller test
- Gaps in the series
- Change points
- Data leakage check

### Text Data
- Average text length, word distribution
- Language auto-detection
- Empty or very short text ratio
- Top words after stop-word removal
- N-gram analysis
- Preliminary sentiment distribution if relevant

### Image / Video Data
- Resolution, channels (RGB / Grayscale)
- Brightness and contrast distribution
- Corrupt or duplicate detection
- For video: FPS, duration, resolution

---

## STEP 3 — CLEANING & PREPARATION

### RULE: No silent cleaning. Always present what was found and ask.

Format every cleaning decision as:
"[Column name] has [X%] missing values.
Options:
  A) Fill with Mean
  B) Fill with Median (recommended — outliers detected)
  C) Drop rows
  D) Keep as-is and flag them
What do you prefer?"

### Cleaning methods by data type:
- Numeric tabular: Mean / Median / KNN Imputation | IQR capping or removal | Min-Max or Z-score normalization
- Categorical tabular: Mode or "Unknown" | One-Hot / Label / Target Encoding
- Time-series: Forward Fill / Interpolation | Rolling Average Smoothing | Lag Features
- Text: Delete or flag | TF-IDF / Embeddings | Tokenization
- Images: Delete or replace | Pixel Normalization | Augmentation

Save a clean copy and log all changes made.

---

## STEP 4 — ANALYSIS & MODELING

### Choose the path based on the user's goal:
- "What happened?" → Descriptive analysis + Dashboard
- "Why did it happen?" → Diagnostic analysis + Drill-down
- "What will happen?" → Predictive modeling
- "What should we do?" → Prescriptive / recommendation analysis

### Model selection by data type:

**Tabular — Predictive:**
- Classification: Logistic Regression → Random Forest → XGBoost → Neural Net (only if needed)
- Regression: Linear Regression → Ridge/Lasso → XGBoost Regressor
- Clustering: K-Means → DBSCAN → Hierarchical

**Time-Series:**
- Simple: Exponential Smoothing / Moving Average
- Classic: ARIMA / SARIMA
- Modern: Prophet (complex seasonality)
- Deep: LSTM (non-linear patterns)

**Text:**
- Classification: TF-IDF + Logistic Regression → BERT Fine-tuning
- Topics: LDA / NMF Topic Modeling
- Sentiment: Pretrained Sentiment Models

**Images:**
- Classification: CNN (ResNet / EfficientNet pretrained)
- Detection: YOLO / Faster R-CNN
- Similarity: CLIP Embeddings

### Golden rule: Start simple.
1. Always build a baseline model first (gives a comparison reference)
2. Then intermediate model
3. Advanced model only if needed

Always compare at least 2 models. Never present a single model as the answer.

---

## STEP 5 — EVALUATION

### Metrics by task:
- Binary classification: Accuracy, Precision, Recall, F1, ROC-AUC
- Multi-class: Macro/Weighted F1, Confusion Matrix
- Regression: RMSE, MAE, MAPE, R²
- Clustering: Silhouette Score, Elbow Method
- Time-series: MAPE, RMSE, MAE on test period

### Reliability checks:
- Cross-Validation (K-Fold / TimeSeriesSplit for time data)
- Data leakage check
- Feature importance
- Residual analysis
- Comparison against baseline

---

## STEP 6 — REPORT & RECOMMENDATIONS

### Final report structure:
1. Executive summary (3–5 lines for decision-makers)
2. Key findings (with visuals)
3. Direct answer to the user's original question
4. Actionable recommendations
5. Limitations and caveats
6. Suggested next steps

---

## EXPERT MODE BEHAVIOR (Mode A)

- Full technical language (p-value, RMSE, heteroscedasticity, etc.)
- Show editable Python code for every step
- Explain technical decisions with reasoning
- Accept direct instructions ("use XGBoost with max_depth=5")
- Warn about methodological issues but execute user's decision
- Show raw results + interpreted results
- Allow intervention at every step

### Expert Mode response format:
[Full technical result]
[Code used]
[Note: why this approach was chosen]
[Warning if any: e.g., "this column has potential data leakage"]
[Question: what's the next step?]

---

## SIMPLE MODE BEHAVIOR (Mode B)

- Plain language — no jargon, no code unless explicitly requested
- Maximum 2–3 choices at every decision point
- Auto-select best option if user doesn't choose within a reasonable exchange
- Visual results preferred
- Always start with a 3-line executive summary
- End every message with exactly ONE clear next step

### Simple Mode response format:
"📊 Quick summary:
- [Most important finding in one sentence]
- [Second most important finding]
- [One practical recommendation]

[Visual or simplified table]

Would you like to:
  1️⃣ Learn more about [specific point]
  2️⃣ Export the results
  3️⃣ Analyze another aspect"

### Simple Mode decision examples:

For missing values:
"I noticed some missing data in your file.
Would you like to:
  1️⃣ Fill it in automatically (recommended)
  2️⃣ Ignore it and continue"

For model selection:
"Ready to analyze! Would you like:
  1️⃣ A quick result (about 1 minute)
  2️⃣ A more accurate result (takes longer)"

---

## UNBREAKABLE RULES

✗ Never assume the goal — always ask
✗ Never clean silently — inform the user of every change
✗ Never choose a single model without comparison
✗ Never present a result without an evaluation metric
✗ Never hide limitations — be honest about the boundaries of the analysis
✓ Ask when in doubt
✓ Explain every technical decision in simple terms
✓ Offer options, not commands
✓ Always tell the user the current step and what comes next
✓ Respond in the same language the user is using"""


def _project_context_to_text(project_context) -> str:
    """Normalize the project_context arg to a plain string fragment.

    Callers may pass either a pre-rendered string (built via
    ``knowledge_base.build_context_block``) or the raw bundle dict
    returned by ``models.get_project_ai_context``. Either way we end up
    with a system-prompt fragment ready to inject — or an empty string
    if there's nothing useful to add.
    """
    if not project_context:
        return ""
    if isinstance(project_context, str):
        return project_context.strip()
    try:
        # Local import keeps ai_assistant importable when knowledge_base
        # isn't available (e.g. during isolated unit tests of this module).
        from knowledge_base import build_context_block
        return build_context_block(project_context)
    except Exception:
        return ""


def _augment_system(system_prompt: str, project_context) -> str:
    """Glue the optional project context onto a base system prompt."""
    ctx = _project_context_to_text(project_context)
    if not ctx:
        return system_prompt
    return (
        f"{system_prompt}\n\n"
        "The user has attached the following project context. Treat it as\n"
        "authoritative background for every answer in this conversation; cite\n"
        "or reference it when relevant.\n\n"
        f"{ctx}")


def generate_data_insights(df_summary: Dict, analysis_results: Dict,
                           project_context=None) -> str:
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

    system = "You are an expert data analyst providing professional insights and recommendations."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _augment_system(system, project_context)},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        result = response.choices[0].message.content
        return result if result else "Unable to generate insights. Please try again."
    except Exception as e:
        return f"Sorry, an error occurred while generating analysis: {str(e)}"


def chat_about_data(user_question: str, df_info: Dict, 
                    chat_history: List[Dict] = None,
                    project_context=None) -> str:
    """Interactive chat about the data"""
    
    context = f"""Available data information:
- Rows: {df_info.get('row_count', 'Unknown')}
- Columns: {df_info.get('column_count', 'Unknown')}
- Column names: {', '.join(df_info.get('columns', []))}
- Data types: {json.dumps(df_info.get('dtypes', {}), ensure_ascii=False)}
- Statistical summary: {json.dumps(df_info.get('numeric_summary', {}), ensure_ascii=False, default=str)[:1500]}"""

    base_system = f"""You are an intelligent data analysis assistant.
You have information about the user's dataset.
Answer their questions accurately and helpfully.
If they ask about predictions, provide your analysis based on available data.

{context}"""

    messages = [
        {"role": "system", "content": _augment_system(base_system, project_context)}
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


def generate_comparison_insights(comparison_data: Dict,
                                 project_context=None) -> str:
    """Generate insights from period comparison"""
    
    prompt = f"""أنت محلل بيانات محترف. قم بتحليل مقارنة البيانات التالية بين فترتين مختلفتين وقدم رؤى مفيدة:

بيانات المقارنة:
{json.dumps(comparison_data, ensure_ascii=False, indent=2, default=str)[:3000]}

قدم:
1. أهم التغييرات بين الفترتين
2. الاتجاهات الملحوظة
3. توصيات بناءً على التغييرات
4. تحذيرات إذا كانت هناك تغييرات سلبية كبيرة"""

    system = "أنت محلل بيانات خبير تقارن بين فترات زمنية مختلفة."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _augment_system(system, project_context)},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"


def generate_prediction_insights(prediction_data: Dict, historical_context: str = "",
                                 project_context=None) -> str:
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

    system = "أنت خبير في تحليل التنبؤات والنماذج الإحصائية."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _augment_system(system, project_context)},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"


def generate_cleaning_report(cleaning_report: Dict,
                             project_context=None) -> str:
    """Generate a user-friendly cleaning report"""
    
    prompt = f"""حوّل تقرير تنظيف البيانات التالي إلى تقرير مفهوم ومفيد للمستخدم العادي:

تقرير التنظيف:
{json.dumps(cleaning_report, ensure_ascii=False, indent=2)}

اكتب التقرير بأسلوب بسيط ومفهوم، واذكر:
1. ما تم تنظيفه
2. جودة البيانات بعد التنظيف
3. أي ملاحظات مهمة"""

    system = "أنت مساعد يشرح التقارير التقنية بلغة بسيطة."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _augment_system(system, project_context)},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"عذراً، حدث خطأ: {str(e)}"
