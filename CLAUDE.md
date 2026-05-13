# CLAUDE.md — AXIOM
> هاد الملف هو دليلك الكامل للمشروع. اقرأه قبل أي تعديل.

---

## 🧠 ما هو المشروع؟

**AXIOM** — Intelligent data analytics platform, no code required.

## 🏗️ Architecture
*   **Backend:** FastAPI + SQLAlchemy (SQLite for local dev).
*   **Frontend:** Next.js 14 + TailwindCSS (Glassmorphism theme).
*   **AI Engine:** Mode-aware GPT-4o integration with guided flows.

---

## 🗂️ هيكل الملفات — ما وظيفة كل ملف

### الملفات الأساسية (Core App)
| الملف | الوظيفة |
|-------|---------|
| `main.py` | نقطة الدخول — routing بين الصفحات |
| `app.py` | الـ Streamlit app الرئيسية — UI والـ session state |
| `models.py` | SQLAlchemy models: User, Dataset, Project, Subscription |
| `data_analyzer.py` | تحليل البيانات الإحصائي — EDA, statistics |
| `data_cleaner.py` | تنظيف البيانات — missing values, duplicates, outliers |
| `data_modelling.py` | ML pipeline — RandomForest, LinearRegression, K-Means |
| `predictions.py` | التوقعات والـ trend analysis |
| `transforms.py` | تحويلات البيانات — encoding, normalization |
| `visualizations.py` | كل الرسومات Plotly/Seaborn/Matplotlib |
| `ai_assistant.py` | الشات مع GPT-4o — AI Assistant للمستخدم |
| `proactive_questions.py` | الأسئلة الاستباقية عند رفع البيانات |
| `knowledge_base.py` | قاعدة المعرفة للـ AI |
| `email_service.py` | إرسال الإيميلات عبر Resend |

### Context Layer
| الملف | الوظيفة |
|-------|---------|
| `context/business_memory.py` | ذاكرة الـ session والـ business context |
| `context/date_intelligence.py` | كشف الأعمدة الزمنية وتحليلها |
| `context/step_history.py` | تتبع خطوات التحليل |
| `context/type_inference.py` | كشف نوع البيانات تلقائياً |

### SEO Agent (`seo_agent/`)
| الملف | الوظيفة |
|-------|---------|
| `runner.py` | المشغّل الرئيسي للـ agent |
| `generator.py` | توليد المحتوى عبر GPT-4o |
| `selector.py` | اختيار المواضيع من Trending Sources |
| `sources.py` | Reddit, HN, Google Trends |
| `geo_check.py` | Brand mention checks |
| `refresh.py` | تحديث المحتوى القديم |
| `build_queue.py` | قائمة انتظار نشر المحتوى المعتمد |
| `review.py` | واجهة المراجعة في Admin Panel |

### Marketing Site (`marketing-site/`)
- Astro static site — **لا تعدّل `dist/` يدوياً**
- التعديلات تصير في `src/` ثم `npm run build`
- المحتوى في `src/content/` (markdown files)

### Scripts (`scripts/`)
| الملف | الوظيفة |
|-------|---------|
| `run_seo_agent.py` | تشغيل SEO agent يدوياً |
| `build_summary_pdf.py` | توليد تقرير PDF |
| `ping-search-engines.mjs` | إشعار محركات البحث بعد البناء |
| `post-merge.sh` | يُشغَّل بعد كل merge |

### Tests (`tests/`)
```
test_data_modelling.py       → اختبارات ML models
test_proactive_questions.py  → اختبارات الأسئلة الاستباقية
test_step_history_persistence.py → اختبارات الـ step history
test_transforms.py           → اختبارات التحويلات
```
**شغّل الاختبارات بعد أي تعديل على الملفات المرتبطة.**

---

## 🤖 الـ AI Stack — من يعمل ماذا؟

```
المستخدم
    ↕
GPT-4o (OpenAI)
    ├── AI Assistant (ai_assistant.py)     → الشات مع البيانات
    ├── Recommendations & Insights         → توصيات ذكية
    ├── Proactive Questions                → أسئلة استباقية
    └── SEO/GEO Content (seo_agent/)       → توليد محتوى تسويقي

scikit-learn (محلي — مش LLM)
    ├── RandomForest / LinearRegression    → predictions.py
    ├── K-Means Clustering                 → data_modelling.py
    └── Outlier Detection                  → data_cleaner.py
```

> ⚠️ **مهم:** الـ ML models (scikit-learn) تشتغل محلياً بدون API calls.
> GPT-4o دوره الشرح والشات والتوصيات فقط — مش التحليل الرقمي.

---

## 👤 نظام المستخدمين — وضعين للتحليل

### Expert Mode (محلل البيانات)
- المستخدم يقود — الموديل ينفذ ويقترح
- لغة تقنية كاملة
- كود قابل للتعديل يُعرض
- تحكم كامل بكل خطوة

### Simple Mode (المستخدم العادي)
- الموديل يقود — المستخدم يختار من خيارات
- لا مصطلحات تقنية، لا كود
- 2-3 خيارات فقط في كل نقطة قرار
- ملخص جاهز دائماً

**التبديل بين المودين:** في أي وقت بدون إعادة رفع البيانات.

---

## 🗄️ قاعدة البيانات (PostgreSQL)

```
Users          → بيانات المستخدمين والـ authentication
Projects       → المشاريع لكل مستخدم
Datasets       → الملفات المرفوعة مع metadata
Subscriptions  → نظام الـ tiers (60 يوم trial كامل)
SupportMessages → رسائل الدعم
```

> الـ ORM: SQLAlchemy — **لا تكتب SQL مباشر، استخدم الـ models.**
> إذا واجهت `DetachedInstanceError` → استخدم `session.refresh()` أو `expire_on_commit=False`

---

## 🎨 Design System — "Data Noir"

```css
Colors:
  Primary:    Deep Navy (#0A0E1A)
  Accent:     Teal (#00D4AA)
  Surface:    Glassmorphism cards
  Background: Matrix rain animation (subtle)

Typography:
  Headings:   Syne
  Body:       DM Sans
  Monospace:  JetBrains Mono

Layout:
  Max width:  1320px (desktop-first)
  Sidebar:    9 sections في 3 clusters
              DATA · ANALYSIS · INSIGHT
              (مع 2-digit index prefixes)
```

**لا تغيّر الـ Design System بدون سبب وجيه.**

---

## 📋 قواعد العمل — لا تُكسر

### ✅ افعل دائماً
- شغّل الاختبارات بعد أي تعديل على `data_modelling.py`, `transforms.py`, `proactive_questions.py`, `context/step_history.py`
- استخدم Plotly للرسومات التفاعلية (مش Matplotlib إلا للـ static فقط)
- أي تغيير على DB schema → عدّل `models.py` أولاً
- اللغة مع المستخدم: عربي (لهجة شامية)
- أعمدة البيانات تُعرض بالإنجليزي دائماً

### ❌ لا تفعل أبداً
- لا تعدّل `marketing-site/dist/` مباشرة — هاي ملفات مولّدة
- لا تضيف payment integration — كل الـ tiers مجانية حالياً
- لا تغيّر GPT model string بدون إذن صريح
- لا تحذف أي ملف من `seo_agent/` بدون فهم كامل للـ build queue
- لا تبني assumptions على نوع البيانات — استخدم `context/type_inference.py`
- لا تنظف البيانات بصمت — كل تغيير يُعرض على المستخدم

---

## 🔧 كيف تشغّل المشروع

```bash
# تشغيل التطبيق
streamlit run main.py

# تشغيل SEO agent يدوياً
python scripts/run_seo_agent.py

# بناء Marketing site
cd marketing-site && npm run build

# تشغيل الاختبارات
python -m pytest tests/
```

---

## ⚡ أخطاء شائعة وحلولها

| الخطأ | السبب | الحل |
|-------|-------|------|
| `DetachedInstanceError` | SQLAlchemy session expired | `session.refresh(obj)` أو `expire_on_commit=False` |
| GPT timeout | طلب طويل جداً | قسّم الـ prompt أو استخدم streaming |
| Marketing site قديم | `dist/` مش محدّث | `cd marketing-site && npm run build` |
| ML model خطأ | بيانات مش منظّفة | شغّل `data_cleaner.py` أولاً |

---

## 📁 ملفات لا تلمسها

```
uv.lock                    → dependency lock file
marketing-site/dist/       → auto-generated
marketing-site/package-lock.json
project.zip                → backup archive
attached_assets/           → reference files فقط
```

---

*آخر تحديث: بناءً على هيكل المشروع الفعلي على Replit*
