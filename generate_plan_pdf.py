"""Generate the comprehensive Arabic PDF plan for DataVision Pro."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether
)
import arabic_reshaper
from bidi.algorithm import get_display

pdfmetrics.registerFont(TTFont("Amiri", "/tmp/Amiri-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Amiri-Bold", "/tmp/Amiri-Bold.ttf"))

TEAL = colors.HexColor("#0d7377")
TEAL_DARK = colors.HexColor("#0a4f52")
EMERALD = colors.HexColor("#14a085")
LIGHT_BG = colors.HexColor("#e8f5f4")
GREY = colors.HexColor("#4a4a4a")
RED_ACCENT = colors.HexColor("#c0392b")
ORANGE = colors.HexColor("#e67e22")


def ar(text):
    """Reshape and apply BiDi to Arabic text."""
    return get_display(arabic_reshaper.reshape(text))


def styles():
    s = getSampleStyleSheet()
    base = dict(fontName="Amiri", alignment=TA_RIGHT, wordWrap="RTL", leading=20)
    return {
        "title": ParagraphStyle("title", parent=s["Title"], fontName="Amiri-Bold",
                                fontSize=28, textColor=TEAL_DARK, alignment=TA_CENTER,
                                leading=36, spaceAfter=10),
        "subtitle": ParagraphStyle("subtitle", parent=s["Normal"], fontName="Amiri",
                                   fontSize=14, textColor=GREY, alignment=TA_CENTER,
                                   leading=20, spaceAfter=20),
        "h1": ParagraphStyle("h1", parent=s["Heading1"], fontName="Amiri-Bold",
                             fontSize=22, textColor=colors.white, backColor=TEAL,
                             alignment=TA_RIGHT, leading=32, spaceBefore=20,
                             spaceAfter=12, borderPadding=10, wordWrap="RTL"),
        "h2": ParagraphStyle("h2", parent=s["Heading2"], fontName="Amiri-Bold",
                             fontSize=17, textColor=TEAL_DARK, alignment=TA_RIGHT,
                             leading=24, spaceBefore=14, spaceAfter=8, wordWrap="RTL"),
        "h3": ParagraphStyle("h3", parent=s["Heading3"], fontName="Amiri-Bold",
                             fontSize=14, textColor=EMERALD, alignment=TA_RIGHT,
                             leading=20, spaceBefore=8, spaceAfter=4, wordWrap="RTL"),
        "body": ParagraphStyle("body", parent=s["Normal"], **base, fontSize=11,
                               spaceAfter=6, textColor=colors.black),
        "bullet": ParagraphStyle("bullet", parent=s["Normal"], **{**base, "leading": 18},
                                 fontSize=11, leftIndent=0, rightIndent=15,
                                 spaceAfter=4, textColor=colors.black),
        "note": ParagraphStyle("note", parent=s["Normal"], **base, fontSize=10,
                               textColor=GREY, spaceAfter=4),
        "day_title": ParagraphStyle("dayt", parent=s["Heading1"], fontName="Amiri-Bold",
                                    fontSize=20, textColor=colors.white, backColor=EMERALD,
                                    alignment=TA_CENTER, leading=30, spaceBefore=10,
                                    spaceAfter=10, borderPadding=8, wordWrap="RTL"),
        "section_box": ParagraphStyle("box", parent=s["Normal"], fontName="Amiri-Bold",
                                      fontSize=13, textColor=TEAL_DARK, alignment=TA_RIGHT,
                                      leading=22, backColor=LIGHT_BG, borderPadding=8,
                                      spaceBefore=8, spaceAfter=8, wordWrap="RTL"),
    }


S = styles()


def P(text, style="body"):
    return Paragraph(ar(text), S[style])


def bullet_list(items):
    return [P("•  " + item, "bullet") for item in items]


def table_data(rows, col_widths=None, header_color=TEAL):
    """Create RTL table - reverse columns for RTL display."""
    rtl_rows = [list(reversed(row)) for row in rows]
    reshaped = [[ar(str(cell)) for cell in row] for row in rtl_rows]
    if col_widths:
        col_widths = list(reversed(col_widths))
    t = Table(reshaped, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Amiri-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Amiri"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build():
    out = "DataVision_Pro_Execution_Plan.pdf"
    doc = SimpleDocTemplate(out, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title="DataVision Pro - Execution Plan")
    story = []

    # ===== COVER =====
    story.append(Spacer(1, 4*cm))
    story.append(P("DataVision Pro", "title"))
    story.append(P("خطة التطوير التنفيذية الشاملة", "title"))
    story.append(Spacer(1, 0.5*cm))
    story.append(P("ثلاثة محاور . ثلاثة أيام . رؤية متكاملة", "subtitle"))
    story.append(Spacer(1, 2*cm))
    cover_tbl = Table([
        [ar("تطوير البنية الهندسية")],
        [ar("استراتيجية SEO ذكية")],
        [ar("تطوير المنتج وتغطية السوق")],
    ], colWidths=[12*cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEAL_DARK),
        ("FONTNAME", (0, 0), (-1, -1), "Amiri-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 16),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("LINEBELOW", (0, 0), (-1, -1), 2, EMERALD),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 3*cm))
    story.append(P("وثيقة مشاركة الفريق  |  أبريل 2026", "subtitle"))
    story.append(PageBreak())

    # ===== TABLE OF CONTENTS =====
    story.append(P("جدول المحتويات", "h1"))
    toc = [
        "الجزء الأول: ملخص تنفيذي",
        "الجزء الثاني: المحور الأول - تطوير البنية الهندسية",
        "الجزء الثالث: المحور الثاني - استراتيجية SEO الذكية",
        "الجزء الرابع: المحور الثالث - تطوير المنتج وتغطية السوق",
        "الجزء الخامس: الخطة التنفيذية على 3 أيام",
        "الجزء السادس: مقترحات إضافية",
        "الجزء السابع: مؤشرات النجاح والخلاصة",
    ]
    for i, t in enumerate(toc, 1):
        story.append(P(f"{i}.  {t}", "body"))
    story.append(PageBreak())

    # ===== PART 1: EXECUTIVE SUMMARY =====
    story.append(P("الجزء الأول: ملخص تنفيذي", "h1"))
    story.append(P(
        "هذه الوثيقة تجمع خلاصة 3 محاور رئيسية لتطوير منصة DataVision Pro وتحويلها "
        "من أداة تحليل بيانات إلى منتج SaaS متكامل قادر على المنافسة في السوق. "
        "تم تنظيم العمل على شكل خطة تنفيذية مدتها 3 أيام مكثفة، يليها خارطة طريق طويلة المدى.",
        "body"))
    story.append(Spacer(1, 0.3*cm))
    story.append(P("التقييم الحالي للمشروع: 7.5 / 10", "h2"))
    story.append(P("• نقاط القوة: بنية وظيفية متكاملة، نظام مستخدمين، تكامل AI، نظام إيميلات", "bullet"))
    story.append(P("• نقاط الضعف الجوهرية: ملف app.py ضخم (2178 سطر)، ضعف الأمان، غياب الاختبارات", "bullet"))
    story.append(P("• الفجوة الأكبر: المنتج ينافس في سوق مزدحم بدون ميزة فريدة واضحة", "bullet"))
    story.append(Spacer(1, 0.3*cm))
    story.append(P("الهدف من الخطة", "h2"))
    story.append(P(
        "نقل المشروع من مرحلة \"النموذج الأولي العامل\" إلى مرحلة \"المنتج الجاهز للسوق\" "
        "عبر معالجة الديون التقنية، بناء قنوات اكتساب مستخدمين، وإضافة ميزات تخلق قيمة حقيقية ومميزة.",
        "body"))
    story.append(PageBreak())

    # ===== PART 2: ENGINEERING =====
    story.append(P("المحور الأول: تطوير البنية الهندسية", "h1"))

    story.append(P("1. إعادة هيكلة الكود (الأولوية القصوى)", "h2"))
    story.append(P("ملف app.py يحتوي على 2178 سطر = دين تقني خطير. التقسيم المقترح:", "body"))
    for item in [
        "pages/auth.py — تسجيل الدخول والتسجيل",
        "pages/dashboard.py — الواجهة الرئيسية للتحليل",
        "pages/admin.py — لوحة المدير",
        "pages/tiers.py — صفحة الباقات",
        "pages/support.py — نموذج الدعم الفني",
        "components/ui.py — العناصر المشتركة (الشريط العلوي، البطاقات)",
        "utils/session.py — إدارة حالة الجلسة",
        "utils/auth_helpers.py — دوال المصادقة المساعدة",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("2. تحسينات الأمان", "h2"))
    for item in [
        "إضافة Email Verification عند التسجيل",
        "إضافة Password Reset (نسيت كلمة السر)",
        "Rate Limiting على محاولات تسجيل الدخول (حد أقصى 5 محاولات / 15 دقيقة)",
        "تشفير الـ session tokens بشكل آمن",
        "حماية CSRF للنماذج الحساسة",
        "تسجيل محاولات الدخول الفاشلة (Audit Log)",
        "إضافة Two-Factor Authentication (2FA) - اختياري للمستخدمين",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("3. الأداء (Performance)", "h2"))
    for item in [
        "استخدام @st.cache_data للتحليلات المتكررة",
        "معالجة الملفات الكبيرة بشكل تدريجي (Chunked processing)",
        "إضافة Redis للـ caching",
        "نقل المهام الطويلة إلى Background Workers (Celery)",
        "إضافة progress bars للعمليات الطويلة",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("4. قاعدة البيانات", "h2"))
    for item in [
        "إضافة Database Indexes على الحقول كثيرة الاستخدام (email, user_id)",
        "تطبيق نظام Migrations باستخدام Alembic",
        "وضع استراتيجية Archiving لجدول ChatHistory الذي سيكبر بسرعة",
        "Backup تلقائي يومي لقاعدة البيانات",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("5. الجودة والاختبارات", "h2"))
    for item in [
        "إضافة Unit Tests للموديولات الأساسية (pytest)",
        "اختبارات لمنطق التنظيف، التحليلات، والـ Tier",
        "إضافة Logging احترافي بدلاً من print",
        "إعداد CI/CD للنشر التلقائي",
        "إضافة Error Tracking (مثل Sentry)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("6. تحويل المعمارية لـ Scalable", "h2"))
    story.append(P("الانتقال التدريجي من Monolith إلى Microservices:", "body"))
    for item in [
        "نقل المنطق الحسابي إلى FastAPI Backend",
        "Frontend منفصل بـ Next.js للأداء والـ SEO",
        "تخزين الملفات على Object Storage (S3)",
        "Worker Queue للمعالجة غير المتزامنة",
        "إضافة Load Balancer لدعم مستخدمين متزامنين",
    ]:
        story.append(P("•  " + item, "bullet"))
    story.append(PageBreak())

    # ===== PART 3: SEO =====
    story.append(P("المحور الثاني: استراتيجية SEO الذكية", "h1"))

    story.append(P("التحدي الأساسي", "h2"))
    story.append(P(
        "Streamlit بطبيعته ضعيف جداً في SEO لأنه Single Page App بمحتوى ديناميكي، "
        "ولا يدعم Server-Side Rendering ولا Meta Tags ديناميكية. الحل: استراتيجية هجينة من 3 طبقات.",
        "body"))

    story.append(P("الطبقة 1: فصل الموقع التسويقي عن التطبيق", "h2"))
    for item in [
        "datavisionpro.com — موقع تسويقي بـ Astro/Next.js (SEO ممتاز)",
        "app.datavisionpro.com — تطبيق Streamlit الفعلي (لا يحتاج SEO)",
        "blog.datavisionpro.com — مدونة لمحتوى مستمر",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الطبقة 2: Programmatic SEO", "h2"))
    story.append(P("توليد آلاف الصفحات تلقائياً مستهدفة كلمات بحث طويلة:", "body"))
    seo_table = [
        ["نوع القالب", "العدد المستهدف", "مثال"],
        ["كيف أحلل بيانات [نوع]", "100+", "كيف أحلل بيانات المبيعات"],
        ["مقارنات", "20+", "Excel vs DataVision Pro"],
        ["قوالب صناعية", "50+", "تحليل بيانات المطاعم"],
        ["حلول مشاكل", "100+", "كيف تكتشف الـ Outliers"],
        ["دروس تعليمية", "30+", "شرح K-Means بالعربي"],
    ]
    story.append(table_data(seo_table, col_widths=[5*cm, 3*cm, 7*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("الطبقة 3: Content Engine المستمر", "h2"))
    for item in [
        "AI Content Generator يولّد مقال مدونة أسبوعياً تلقائياً",
        "User-Generated Content من تحليلات المستخدمين (بإذنهم)",
        "Public Reports — كل تحليل عام = صفحة SEO جديدة",
        "Newsletter أسبوعي يبني الجمهور",
        "قناة YouTube لكل ميزة (كل فيديو = backlink)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الميزات الذكية المقترحة", "h2"))
    for item in [
        "أدوات مجانية بدون تسجيل (CSV Cleaner, Outlier Detector) — كل أداة صفحة SEO",
        "Calculators صغيرة (Standard Deviation, Correlation, Mean) لكل واحدة keyword",
        "Comparison Pages — مقارنات مع Tableau و Power BI و Excel",
        "AI-Powered Internal Linking تلقائي بين المقالات",
        "دعم متعدد اللغات (عربي + إنجليزي) مع hreflang من البداية",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الأساسيات التقنية", "h2"))
    for item in [
        "Sitemap.xml + Robots.txt محدّثان تلقائياً",
        "Schema.org Markup (SoftwareApplication, Organization, FAQPage)",
        "Open Graph + Twitter Cards لكل صفحة",
        "Google Search Console + Bing Webmaster",
        "Core Web Vitals optimization (سرعة الموقع)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("النتائج المتوقعة", "h2"))
    seo_results = [
        ["الفترة", "الترافيك المتوقع شهرياً"],
        ["الشهر 1-3", "100 - 500 زيارة"],
        ["الشهر 4-6", "1,000 - 5,000 زيارة"],
        ["الشهر 7-12", "10,000 - 50,000 زيارة"],
        ["السنة الثانية", "100,000+ زيارة"],
    ]
    story.append(table_data(seo_results, col_widths=[6*cm, 9*cm]))
    story.append(PageBreak())

    # ===== PART 4: PRODUCT =====
    story.append(P("المحور الثالث: تطوير المنتج وتغطية السوق", "h1"))

    story.append(P("التشخيص", "h2"))
    story.append(P(
        "DataVision Pro حالياً = أداة EDA ذكية في سوق مزدحم (Tableau, Power BI, Julius AI, Akkio). "
        "السؤال الجوهري: لماذا يستخدم العميل DataVision بدلاً من المنافسين؟ "
        "الحل: التخصص في niche محدد بدلاً من المنافسة العامة.",
        "body"))

    story.append(P("3 اتجاهات استراتيجية - اختر واحداً", "h2"))

    story.append(P("الاتجاه 1: محلل البيانات للسوق العربي", "h3"))
    for item in [
        "واجهة عربية كاملة + دعم RTL",
        "فهم البيانات العربية (أسماء، عناوين، أرقام هواتف)",
        "تقارير AI بالعربي بأسلوب احترافي",
        "قوالب جاهزة لقطاعات عربية (متاجر خليجية، عيادات، مطاعم)",
        "تكامل مع أنظمة محلية (مدى، STC Pay، تمارا)",
        "السوق المستهدف: 400 مليون عربي + شركات SMB في الخليج",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الاتجاه 2: AI Data Analyst للشركات الصغيرة", "h3"))
    for item in [
        "اسأل بياناتك: المستخدم يكتب سؤالاً طبيعياً، AI يجيب ببيانات و chart",
        "Auto-Insights Engine يكتشف الـ insights لوحده",
        "Anomaly Alerts تلقائية لما يحدث شيء غير طبيعي",
        "Weekly Auto-Reports بالإيميل تلقائياً",
        "Connectors لمصادر البيانات (Shopify, Stripe, Google Sheets, QuickBooks)",
        "Action Recommendations: اعمل كذا بناءً على البيانات",
        "السوق المستهدف: مليون+ شركة صغيرة في المنطقة العربية",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الاتجاه 3: Vertical SaaS - تخصص بقطاع واحد", "h3"))
    for item in [
        "DataVision Health — تحليل بيانات العيادات",
        "DataVision Retail — تحليل بيانات المتاجر",
        "DataVision F&B — تحليل بيانات المطاعم",
        "DataVision EDU — تحليل بيانات المدارس",
        "ميزة: منافسة أقل + أسعار أعلى + ROI واضح + word of mouth قوي",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("ميزات تطوير المنتج (لأي اتجاه تختاره)", "h2"))

    story.append(P("1. Conversational Analytics (الميزة الأهم)", "h3"))
    for item in [
        "المستخدم يكتب أسئلة طبيعية: لماذا قلّت مبيعات مارس؟",
        "AI يفهم، يحلل، ويعرض النتيجة + الـ chart المناسب",
        "تقنية: LLM + Function Calling + RAG على البيانات",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("2. Auto-Discovery Engine", "h3"))
    for item in [
        "لما يرفع المستخدم ملف، النظام يكتشف لوحده الـ insights",
        "Correlations قوية، Outliers، Seasonality، Data quality issues",
        "بدون أي تدخل من المستخدم",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("3. Smart Data Cleaning بـ AI", "h3"))
    for item in [
        "AI يفهم السياق ويقترح التنظيف",
        "توحيد الأسماء العربية المكتوبة بأشكال مختلفة",
        "إصلاح التواريخ بصيغ متعددة",
        "كشف الأخطاء المنطقية (أعمار سلبية مثلاً)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("4. Data Pipeline حقيقي", "h3"))
    for item in [
        "Connectors مباشرة (Shopify, Google Sheets, MySQL, Salesforce)",
        "Auto-Sync كل ساعة/يوم",
        "Data Warehouse صغير لكل مستخدم (لا يرفع نفس الملف مرتين)",
        "Versioning ومقارنات زمنية حقيقية",
        "Collaboration: مشاركة، تعليقات، صلاحيات",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("5. ML/AI متقدم", "h3"))
    for item in [
        "AutoML: المستخدم يقول توقع المبيعات، النظام يجرب 10 نماذج",
        "Time Series Forecasting (Prophet, ARIMA, LSTM)",
        "Customer Segmentation (RFM Analysis تلقائي)",
        "Churn Prediction للعملاء",
        "Sentiment Analysis للنصوص العربية",
        "Causal Analysis: سبب ونتيجة وليس فقط correlation",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("6. Output احترافي", "h3"))
    for item in [
        "Interactive Dashboards قابلة للمشاركة بـ link public",
        "PDF Reports احترافية مع Branding المستخدم",
        "Executive Summary موجز للإدارة (صفحة واحدة)",
        "Embedded Analytics (المستخدم يضمّن chart في موقعه)",
        "Scheduled Reports بالإيميل/Slack/WhatsApp",
        "Voice Reports بالعربي",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("الميزة القاتلة: DataVision Agent", "h2"))
    story.append(P(
        "وكيل ذكي شخصي للبيانات يعمل لوحده بشكل مستمر: يحلل البيانات يومياً، "
        "يرسل تنبيهات للأنوماليز، تقارير دورية، اقتراحات استراتيجية شهرية، "
        "ويتعلم من تفضيلات المستخدم. هذا الفرق بين \"أداة\" و\"موظف ذكي\".",
        "section_box"))
    story.append(PageBreak())

    # ===== PART 5: 3-DAY PLAN =====
    story.append(P("الجزء الخامس: الخطة التنفيذية على 3 أيام", "h1"))
    story.append(P(
        "خطة مكثفة لتغطية المحاور الثلاثة بشكل متوازي. كل يوم يعمل على جزء من كل محور "
        "بحيث ينتهي اليوم الثالث بأساس قوي للانطلاق.",
        "body"))
    story.append(Spacer(1, 0.4*cm))

    # DAY 1
    story.append(P("اليوم الأول: الأساس والتنظيف", "day_title"))
    story.append(P("الهدف: معالجة الديون التقنية الجوهرية وبناء أساس قابل للتطوير", "h3"))

    story.append(P("الصباح (4 ساعات) - البنية الهندسية", "h2"))
    day1_morning = [
        ["المهمة", "الوقت", "المسؤول"],
        ["تقسيم app.py إلى pages/ و components/", "ساعتان", "Backend Dev"],
        ["إعداد Logging احترافي + Error Tracking", "ساعة", "Backend Dev"],
        ["إضافة Database Indexes الأساسية", "30 دقيقة", "Backend Dev"],
        ["إعداد Alembic Migrations", "30 دقيقة", "Backend Dev"],
    ]
    story.append(table_data(day1_morning, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("بعد الظهر (4 ساعات) - الأمان", "h2"))
    day1_pm = [
        ["المهمة", "الوقت", "المسؤول"],
        ["Email Verification + Password Reset", "ساعتان", "Backend Dev"],
        ["Rate Limiting على تسجيل الدخول", "ساعة", "Backend Dev"],
        ["Audit Log لمحاولات الدخول", "ساعة", "Backend Dev"],
    ]
    story.append(table_data(day1_pm, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("المساء (2-3 ساعات) - تخطيط استراتيجي", "h2"))
    for item in [
        "اجتماع فريق: اختيار 1 من 3 الاتجاهات الاستراتيجية",
        "تحديد Persona المستخدم المستهدف بدقة",
        "تجهيز قائمة 5 مستخدمين محتملين للمقابلات",
        "كتابة أسئلة المقابلات (5 أسئلة محورية)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("مخرجات اليوم الأول", "h3"))
    for item in [
        "كود نظيف ومنظم في ملفات منفصلة",
        "نظام مصادقة آمن وكامل",
        "اتجاه استراتيجي واضح للمشروع",
    ]:
        story.append(P("✓  " + item, "bullet"))
    story.append(PageBreak())

    # DAY 2
    story.append(P("اليوم الثاني: SEO وأساس النمو", "day_title"))
    story.append(P("الهدف: بناء قنوات اكتساب المستخدمين وتجهيز موقع تسويقي", "h3"))

    story.append(P("الصباح (4 ساعات) - الموقع التسويقي", "h2"))
    day2_morning = [
        ["المهمة", "الوقت", "المسؤول"],
        ["إنشاء Landing Page بـ Astro/Next.js", "ساعتان", "Frontend Dev"],
        ["تصميم Hero + Features + Pricing + Testimonials", "ساعة", "Designer + Dev"],
        ["إعداد Sitemap + Robots.txt + Schema markup", "30 دقيقة", "Frontend Dev"],
        ["Open Graph + Twitter Cards", "30 دقيقة", "Frontend Dev"],
    ]
    story.append(table_data(day2_morning, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("بعد الظهر (4 ساعات) - Programmatic SEO", "h2"))
    day2_pm = [
        ["المهمة", "الوقت", "المسؤول"],
        ["بحث keywords (Ahrefs/Ubersuggest)", "ساعة", "Marketing"],
        ["بناء templates للصفحات البرمجية", "ساعتان", "Frontend Dev"],
        ["توليد أول 30 صفحة (مزيج يدوي + AI)", "ساعة", "Content + Dev"],
    ]
    story.append(table_data(day2_pm, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("المساء (3 ساعات) - الأدوات المجانية و المحتوى", "h2"))
    for item in [
        "بناء 3 أدوات مجانية بسيطة (CSV Cleaner، Outlier Detector، Correlation Calculator)",
        "كتابة 5 مقالات أساسية للمدونة",
        "إعداد Google Search Console + Analytics",
        "إجراء أول 2-3 مقابلات مع مستخدمين محتملين",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("مخرجات اليوم الثاني", "h3"))
    for item in [
        "Landing Page احترافي مفهرس بـ Google",
        "30 صفحة برمجية + 3 أدوات مجانية + 5 مقالات",
        "بيانات حقيقية من مستخدمين محتملين توجّه التطوير",
    ]:
        story.append(P("✓  " + item, "bullet"))
    story.append(PageBreak())

    # DAY 3
    story.append(P("اليوم الثالث: المنتج والميزة الفريدة", "day_title"))
    story.append(P("الهدف: بناء MVP لميزة قاتلة تميّز المنتج", "h3"))

    story.append(P("الصباح (4 ساعات) - Conversational Analytics", "h2"))
    day3_morning = [
        ["المهمة", "الوقت", "المسؤول"],
        ["تصميم Schema للأسئلة الطبيعية", "ساعة", "AI Engineer"],
        ["دمج OpenAI Function Calling مع pandas", "ساعتان", "AI Engineer"],
        ["واجهة نصية للأسئلة + عرض النتائج", "ساعة", "Frontend"],
    ]
    story.append(table_data(day3_morning, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("بعد الظهر (4 ساعات) - Auto-Insights و Smart Cleaning", "h2"))
    day3_pm = [
        ["المهمة", "الوقت", "المسؤول"],
        ["محرّك Auto-Insights عند رفع الملف", "ساعتان", "Data Scientist"],
        ["Smart Cleaning بـ AI (للنصوص العربية)", "ساعتان", "AI Engineer"],
    ]
    story.append(table_data(day3_pm, col_widths=[8*cm, 3*cm, 4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("المساء (3 ساعات) - Output واختبار", "h2"))
    for item in [
        "PDF Reports احترافية بالعربي مع branding المستخدم",
        "Executive Summary تلقائي (صفحة واحدة)",
        "اختبار شامل مع 5-10 مستخدمين فعليين",
        "جمع التغذية الراجعة وتوثيق التحسينات المطلوبة",
        "تحضير Demo Video لكل ميزة جديدة",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("مخرجات اليوم الثالث", "h3"))
    for item in [
        "ميزة Conversational Analytics تعمل (الفرق التنافسي الأول)",
        "Auto-Insights عند كل رفع ملف",
        "تقارير PDF احترافية للمشاركة",
        "تغذية راجعة من مستخدمين فعليين",
    ]:
        story.append(P("✓  " + item, "bullet"))
    story.append(PageBreak())

    # SUMMARY TABLE
    story.append(P("ملخص الخطة على 3 أيام", "h1"))
    summary = [
        ["اليوم", "البنية الهندسية", "SEO", "المنتج"],
        ["اليوم 1", "تقسيم الكود + الأمان", "تخطيط استراتيجي", "اختيار الاتجاه"],
        ["اليوم 2", "Logging + Migrations", "Landing + 30 صفحة + أدوات", "مقابلات مستخدمين"],
        ["اليوم 3", "اختبارات + تحسين", "نشر + متابعة", "Conversational + Auto-Insights"],
    ]
    story.append(table_data(summary, col_widths=[2.5*cm, 4*cm, 4.5*cm, 4.5*cm]))
    story.append(PageBreak())

    # ===== PART 6: ADDITIONAL =====
    story.append(P("الجزء السادس: مقترحات إضافية", "h1"))

    story.append(P("1. مقترحات تشغيلية", "h2"))
    for item in [
        "إنشاء Roadmap عام للسنة على Notion/Linear يشاركه الفريق",
        "اجتماع أسبوعي 30 دقيقة لمراجعة المقاييس",
        "تخصيص قناة Slack لكل محور (Engineering / Marketing / Product)",
        "Daily Standup قصير (15 دقيقة) خلال أيام التطوير المكثفة",
        "ثقافة Documentation: كل ميزة جديدة لها صفحة شرح في Wiki داخلي",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("2. مقترحات تسويقية", "h2"))
    for item in [
        "Free Trial 14 يوم بدون credit card (للجمهور خارج المستخدمين الحاليين)",
        "Affiliate Program مع 30% عمولة لمدة 6 أشهر",
        "Case Studies حقيقية مع شركات استخدمت المنتج",
        "Webinars شهرية بالعربي عن تحليل البيانات",
        "Discord/Telegram Community لجمهور تحليل البيانات بالعربي",
        "LinkedIn Content Strategy: منشور احترافي يومي من الـ Founder",
        "شراكات مع جامعات ومعاهد تدريبية",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("3. مقترحات منتج إضافية", "h2"))
    for item in [
        "Mobile App (React Native) لعرض الـ Dashboards على الموبايل",
        "Browser Extension لاستخراج بيانات من أي صفحة وتحليلها",
        "Slack/Teams Bot للأسئلة السريعة عن البيانات",
        "WhatsApp Bot لتلقي تنبيهات الأنوماليز",
        "API Public للمطورين (Tier 4 للشركات)",
        "Marketplace لقوالب التحليل (يصنعها المجتمع)",
        "ميزة Data Storytelling تلقائية (تحويل البيانات لقصة سردية)",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("4. مقترحات بيانات وذكاء اصطناعي متقدم", "h2"))
    for item in [
        "Multi-Modal Analysis (تحليل صور + جداول + نصوص معاً)",
        "Predictive Maintenance للقطاع الصناعي",
        "Fine-tuned LLM خاص بالبيانات العربية",
        "Embeddings قاعدة بيانات لاستعلامات شبيهة (Semantic Search)",
        "RAG على وثائق الشركة (دمج البيانات مع المعرفة الداخلية)",
        "Synthetic Data Generation للتدريب والاختبار",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("5. مقترحات نمو واستدامة", "h2"))
    for item in [
        "نموذج Freemium واضح بحدود استخدام عادلة",
        "Annual Plans بخصم 20% لتثبيت الإيرادات",
        "Enterprise Tier للشركات الكبيرة (custom pricing)",
        "Data Marketplace: بيع تقارير صناعية جاهزة",
        "تدريب وشهادات DataVision Certified Analyst",
        "صندوق استثمار صغير لـ Data startups تستخدم المنصة",
    ]:
        story.append(P("•  " + item, "bullet"))

    story.append(P("6. مقترحات قانونية وتنظيمية", "h2"))
    for item in [
        "سياسة خصوصية واضحة (متوافقة مع GDPR و قانون حماية البيانات السعودي)",
        "شروط الاستخدام معتمدة قانونياً",
        "DPA (Data Processing Agreement) للعملاء الـ Enterprise",
        "ISO 27001 Certification (هدف بعيد المدى)",
        "تأمين تجاري للمنصة (Cyber Insurance)",
    ]:
        story.append(P("•  " + item, "bullet"))
    story.append(PageBreak())

    # ===== PART 7: KPIs =====
    story.append(P("الجزء السابع: مؤشرات النجاح والخلاصة", "h1"))

    story.append(P("KPIs بعد 30 يوم من تنفيذ الخطة", "h2"))
    kpis = [
        ["المؤشر", "الهدف"],
        ["زمن استجابة التطبيق", "< ثانيتين"],
        ["تقليل حجم app.py", "< 500 سطر لكل ملف"],
        ["صفحات SEO منشورة", "100+ صفحة"],
        ["زيارات الموقع شهرياً", "500+ زيارة"],
        ["مستخدمين جدد مسجلين", "50+ مستخدم"],
        ["استخدام ميزة Conversational", "30%+ من الجلسات"],
        ["معدل الـ Activation", "60%+ خلال 7 أيام"],
        ["Tickets دعم محلولة في 24 ساعة", "90%+"],
    ]
    story.append(table_data(kpis, col_widths=[10*cm, 5*cm]))

    story.append(P("KPIs بعد 90 يوم", "h2"))
    kpis2 = [
        ["المؤشر", "الهدف"],
        ["زيارات الموقع شهرياً", "5,000+ زيارة"],
        ["مستخدمين نشطين أسبوعياً (WAU)", "200+ مستخدم"],
        ["معدل تحويل من Trial إلى Paid", "10%+"],
        ["NPS (Net Promoter Score)", "40+"],
        ["MRR (Monthly Recurring Revenue)", "هدف يحدده الفريق"],
    ]
    story.append(table_data(kpis2, col_widths=[10*cm, 5*cm]))

    story.append(P("الخلاصة النهائية", "h2"))
    story.append(P(
        "DataVision Pro لديه أساس قوي وميزات وظيفية متكاملة. المرحلة القادمة هي الانتقال من "
        "\"أداة عاملة\" إلى \"منتج تنافسي في السوق\". الخطة المقترحة على 3 أيام تضع الأساس "
        "في 3 محاور متكاملة: بنية هندسية قوية، قنوات نمو ذكية، ومنتج بميزة قاتلة فريدة.",
        "body"))
    story.append(P(
        "النجاح يتطلب التركيز على نيش محدد بدلاً من محاولة خدمة الجميع، والاستثمار في الميزة "
        "القاتلة (Conversational Analytics + Auto-Insights + DataVision Agent) التي تخلق "
        "فرقاً حقيقياً عن المنافسين.",
        "body"))
    story.append(Spacer(1, 0.5*cm))
    story.append(P(
        "\"كن الأفضل في شيء محدد، بدلاً من أن تكون متوسطاً في كل شيء\"",
        "section_box"))

    story.append(Spacer(1, 1*cm))
    story.append(P("— نهاية الوثيقة —", "subtitle"))

    doc.build(story)
    print(f"PDF generated: {out}")
    print(f"Size: {os.path.getsize(out)/1024:.1f} KB")


if __name__ == "__main__":
    build()
