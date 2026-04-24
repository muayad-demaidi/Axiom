import os
import json
import re
import pandas as pd
from typing import Dict, Any, List, Optional, Iterable
from openai import OpenAI

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
)


SYSTEM_PROMPT = """You are the AI engine of AXIOM — an intelligent data analytics platform. You represent a full team of data scientists working as one: a data analyst, a data engineer, a statistician, and an ML scientist. Your role covers three functions: (1) AI Assistant — chat with the user about their data, (2) Smart Recommendations & Insights — proactively surface findings, (3) Proactive Questions — ask the right questions at the right time.

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


def _apply_mode_directive(system_prompt: str,
                          assistant_mode: Optional[str]) -> str:
    """Append an explicit-mode directive to the system prompt.

    When the UI passes a chosen mode (Expert / Simple), the assistant
    must skip Step 0's mode-detection question and immediately follow
    the matching response format on every reply.
    """
    if not assistant_mode:
        return system_prompt
    mode_norm = str(assistant_mode).strip().lower()
    if mode_norm == "expert":
        return (
            f"{system_prompt}\n\n"
            "## ACTIVE MODE — EXPERT (preselected by the user via UI)\n"
            "The user has already chosen Expert Mode in the interface. "
            "Do NOT ask the Step 0 mode question and do NOT offer to "
            "switch modes — the UI already exposes that control. "
            "Follow the Expert Mode behavior and response format "
            "(full technical language, code, reasoning, warnings, "
            "next-step question) on every reply.")
    if mode_norm == "simple":
        return (
            f"{system_prompt}\n\n"
            "## ACTIVE MODE — SIMPLE (preselected by the user via UI)\n"
            "The user has already chosen Simple Mode in the interface. "
            "Do NOT ask the Step 0 mode question and do NOT offer to "
            "switch modes — the UI already exposes that control. "
            "Follow the Simple Mode behavior and response format "
            "(plain language, 3-line quick summary, max 2–3 choices, "
            "exactly one clear next step) on every reply.")
    return system_prompt


# Map common locale identifiers / aliases to a human-readable language name
# we can drop straight into the model prompt ("Respond in <X>.").
_LANGUAGE_NAMES = {
    "ar": "Arabic",
    "ar-sa": "Arabic",
    "ar-eg": "Arabic",
    "arabic": "Arabic",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "english": "English",
    "fr": "French",
    "french": "French",
    "es": "Spanish",
    "spanish": "Spanish",
    "de": "German",
    "german": "German",
}


def _normalize_language(user_language: Optional[str]) -> Optional[str]:
    """Turn a locale-ish string into a human-readable language name.

    Returns ``None`` when no usable hint is provided so callers can fall back
    to the persona's "match the user's language" rule.
    """
    if not user_language:
        return None
    key = str(user_language).strip().lower()
    if not key:
        return None
    if key in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES[key]
    # Strip region suffix ("ar-MA" -> "ar") and try again.
    base = key.split("-", 1)[0].split("_", 1)[0]
    if base in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES[base]
    # Otherwise, trust the caller — capitalise it for the prompt.
    return user_language.strip()


def _language_instruction(user_language: Optional[str]) -> str:
    """Render the 'reply in language X' line for a user prompt."""
    name = _normalize_language(user_language)
    if name:
        return f"Respond in {name}."
    return (
        "Respond in the same language the user has been using in this "
        "conversation; if you cannot tell, default to English.")


# Tiny stop-word lists used for cheap European-language disambiguation when
# the text is in Latin script. Tuned to be small but distinctive — we only
# need to tip the balance between five candidates, not run a full NLP model.
_STOPWORDS = {
    "English": {
        "the", "and", "you", "for", "with", "this", "that", "what",
        "have", "are", "is", "of", "in", "to", "on", "it", "be", "from",
        "please", "thanks", "show", "make", "can", "do", "how",
    },
    "French": {
        "le", "la", "les", "des", "une", "un", "et", "est", "que", "qui",
        "pour", "avec", "dans", "sur", "vous", "nous", "je", "ne", "pas",
        "ce", "cette", "ces", "merci", "bonjour", "comment", "quel",
    },
    "Spanish": {
        "el", "la", "los", "las", "un", "una", "y", "es", "que", "de",
        "para", "con", "por", "en", "del", "al", "yo", "tú", "muy",
        "gracias", "hola", "como", "qué", "cuál",
    },
    "German": {
        "der", "die", "das", "und", "ist", "ein", "eine", "mit", "für",
        "nicht", "von", "zu", "den", "dem", "des", "ich", "du", "wir",
        "ihr", "sie", "bitte", "danke", "wie", "was",
    },
}

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ\u0600-\u06FF]+", re.UNICODE)
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def detect_language(text: Optional[str]) -> Optional[str]:
    """Best-effort language detection from a free-form string.

    Returns one of the canonical names used by ``_LANGUAGE_NAMES``
    ("Arabic", "English", "French", "Spanish", "German") when a guess is
    confident enough, otherwise ``None``. The implementation is intentionally
    tiny and dependency-free — we only need to tip the balance between the
    handful of languages this app has localized strings for. Anything
    outside that set falls through to the model's own judgement.
    """
    if not text:
        return None
    sample = str(text).strip()
    if not sample:
        return None

    # Arabic is unambiguous via script: any meaningful share of Arabic
    # letters wins, regardless of interspersed Latin words.
    arabic_chars = len(_ARABIC_CHAR_RE.findall(sample))
    letter_count = sum(1 for ch in sample if ch.isalpha())
    if letter_count and arabic_chars / letter_count >= 0.2:
        return "Arabic"

    # Latin script — score against a small set of stopwords per language.
    tokens = [t.lower() for t in _TOKEN_RE.findall(sample)]
    if not tokens:
        return None
    scores = {
        lang: sum(1 for t in tokens if t in words)
        for lang, words in _STOPWORDS.items()
    }
    best_lang, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return None
    # Require a clear winner — if two languages tie, we don't pick.
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) > 1 and sorted_scores[0] == sorted_scores[1]:
        return None
    return best_lang


def detect_language_from_history(
        messages: Optional[Iterable[Dict[str, Any]]],
        fallback: Optional[str] = None) -> Optional[str]:
    """Infer language by scanning the most recent user messages.

    ``messages`` is the chat history as stored in session state — a list of
    ``{"role": ..., "content": ...}`` dicts (or the legacy
    ``{"user": ..., "assistant": ...}`` shape used by ``chat_about_data``).
    The newest user-authored entries are inspected first; the first
    confident detection wins. ``fallback`` is returned when nothing can be
    determined (e.g. empty history or only short emoji replies).
    """
    if not messages:
        return fallback
    msg_list = list(messages)
    for msg in reversed(msg_list[-10:]):
        if not isinstance(msg, dict):
            continue
        text: Optional[str] = None
        role = msg.get("role")
        if role == "user":
            text = msg.get("content")
        elif "user" in msg:
            text = msg.get("user")
        guess = detect_language(text)
        if guess:
            return guess
    return fallback


# Localized error messages for the report-generating helpers. Keyed by the
# normalized language name; falls back to English for anything else.
_ERROR_MESSAGES = {
    "comparison": {
        "English": "Sorry, an error occurred while generating the comparison insights: {error}",
        "Arabic": "عذراً، حدث خطأ أثناء توليد رؤى المقارنة: {error}",
    },
    "prediction": {
        "English": "Sorry, an error occurred while generating the prediction insights: {error}",
        "Arabic": "عذراً، حدث خطأ أثناء توليد رؤى التنبؤ: {error}",
    },
    "cleaning": {
        "English": "Sorry, an error occurred while generating the cleaning report: {error}",
        "Arabic": "عذراً، حدث خطأ أثناء توليد تقرير التنظيف: {error}",
    },
    "insights": {
        "English": "Sorry, an error occurred while generating analysis: {error}",
        "Arabic": "عذراً، حدث خطأ أثناء توليد التحليل: {error}",
    },
    "chat": {
        "English": "Sorry, an error occurred: {error}",
        "Arabic": "عذراً، حدث خطأ: {error}",
    },
}


def _localized_error(kind: str, user_language: Optional[str], error: str) -> str:
    """Pick an error message in the user's language, falling back to English."""
    name = _normalize_language(user_language) or "English"
    template = _ERROR_MESSAGES[kind].get(name) or _ERROR_MESSAGES[kind]["English"]
    return template.format(error=error)


def generate_data_insights(df_summary: Dict, analysis_results: Dict,
                           project_context=None,
                           assistant_mode: Optional[str] = None,
                           user_language: Optional[str] = None) -> str:
    """Generate AI-powered insights from data analysis.

    ``assistant_mode`` is the UI-selected response mode ("expert" or
    "simple") and is injected into the system prompt so insights match
    the same voice the chat assistant uses.

    See :func:`generate_comparison_insights` for the meaning of
    ``user_language``.
    """

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

Write the response in a clear and organized manner.

{_language_instruction(user_language)}"""

    system_prompt = _apply_mode_directive(
        _augment_system(SYSTEM_PROMPT, project_context), assistant_mode)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        result = response.choices[0].message.content
        return result if result else "Unable to generate insights. Please try again."
    except Exception as e:
        return _localized_error("insights", user_language, str(e))


def chat_about_data(user_question: str, df_info: Dict, 
                    chat_history: List[Dict] = None,
                    project_context=None,
                    assistant_mode: Optional[str] = None,
                    user_language: Optional[str] = None) -> str:
    """Interactive chat about the data.

    ``assistant_mode`` is the UI-selected response mode ("expert" or
    "simple"). When provided it's injected into the system prompt so
    the model skips the Step 0 mode question and immediately follows
    the matching response format.

    ``user_language`` is an optional locale or language name (e.g.
    ``"ar"``, ``"en"``, ``"Arabic"``). When provided, the model is told
    to reply in that language as a system-level directive — overriding
    the persona's implicit "match the user's language" rule. When the
    caller leaves it ``None``, we fall back to a cheap heuristic that
    inspects the current question (and recent history) so even helpers
    that get a JSON-only prompt land on the right language.
    """
    
    context = f"""Available data information:
- Rows: {df_info.get('row_count', 'Unknown')}
- Columns: {df_info.get('column_count', 'Unknown')}
- Column names: {', '.join(df_info.get('columns', []))}
- Data types: {json.dumps(df_info.get('dtypes', {}), ensure_ascii=False)}
- Statistical summary: {json.dumps(df_info.get('numeric_summary', {}), ensure_ascii=False, default=str)[:1500]}"""

    # Resolve the effective language: explicit caller value wins, else
    # detect from the question itself, else fall back to the most recent
    # user message in chat history.
    effective_language = user_language
    if not effective_language:
        effective_language = (
            detect_language(user_question)
            or detect_language_from_history(chat_history))

    base_system = _augment_system(SYSTEM_PROMPT, project_context)
    base_system = _apply_mode_directive(base_system, assistant_mode)
    base_system = f"{base_system}\n\n{_language_instruction(effective_language)}"

    messages = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": context},
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
        return _localized_error("chat", effective_language, error_msg)


def generate_comparison_insights(comparison_data: Dict,
                                 project_context=None,
                                 user_language: Optional[str] = None,
                                 assistant_mode: Optional[str] = None) -> str:
    """Generate insights from period comparison.

    ``user_language`` is an optional locale or language name (e.g. ``"ar"``,
    ``"en"``, ``"Arabic"``). When provided, the model is told to reply in that
    language and error messages are localized accordingly. When omitted, the
    persona's default "match the user's language" rule is used.

    ``assistant_mode`` mirrors the chat helper: when supplied it routes
    through ``_apply_mode_directive`` so the comparison summary follows
    the same Expert/Simple voice the user picked in the UI.
    """

    prompt = f"""You are a professional data analyst. Analyze the following comparison of data between two different periods and provide useful insights.

Comparison data:
{json.dumps(comparison_data, ensure_ascii=False, indent=2, default=str)[:3000]}

Provide:
1. The most important changes between the two periods
2. Notable trends
3. Recommendations based on the changes
4. Warnings if there are any significant negative changes

{_language_instruction(user_language)}"""

    system_prompt = _apply_mode_directive(
        _augment_system(SYSTEM_PROMPT, project_context), assistant_mode)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return _localized_error("comparison", user_language, str(e))


def generate_prediction_insights(prediction_data: Dict, historical_context: str = "",
                                 project_context=None,
                                 user_language: Optional[str] = None,
                                 assistant_mode: Optional[str] = None) -> str:
    """Generate insights about predictions.

    See :func:`generate_comparison_insights` for the meaning of
    ``user_language`` and ``assistant_mode``.
    """

    prompt = f"""You are a data analyst specializing in forecasting. Analyze the following prediction results:

Prediction results:
{json.dumps(prediction_data, ensure_ascii=False, indent=2, default=str)}

{f"Historical context: {historical_context}" if historical_context else ""}

Provide:
1. An interpretation of the predictions
2. How reliable the prediction is
3. The contributing factors
4. Recommendations for the future
5. Important warnings or notes

{_language_instruction(user_language)}"""

    system_prompt = _apply_mode_directive(
        _augment_system(SYSTEM_PROMPT, project_context), assistant_mode)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return _localized_error("prediction", user_language, str(e))


def generate_cleaning_report(cleaning_report: Dict,
                             project_context=None,
                             user_language: Optional[str] = None,
                             assistant_mode: Optional[str] = None) -> str:
    """Generate a user-friendly cleaning report.

    See :func:`generate_comparison_insights` for the meaning of
    ``user_language`` and ``assistant_mode``.
    """

    prompt = f"""Turn the following data cleaning report into a clear, user-friendly summary for a non-technical reader:

Cleaning report:
{json.dumps(cleaning_report, ensure_ascii=False, indent=2)}

Write the summary in a simple, easy-to-understand style, and cover:
1. What was cleaned
2. The data quality after cleaning
3. Any important notes

{_language_instruction(user_language)}"""

    system_prompt = _apply_mode_directive(
        _augment_system(SYSTEM_PROMPT, project_context), assistant_mode)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return _localized_error("cleaning", user_language, str(e))
