import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
)

pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

NAVY = colors.HexColor("#07101f")
TEAL = colors.HexColor("#2dd4bf")
SLATE = colors.HexColor("#94a3b8")
WHITE = colors.HexColor("#e2e8f0")


def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


title_style = ParagraphStyle("title", fontName="DejaVu-Bold", fontSize=26,
                             textColor=TEAL, alignment=TA_CENTER, leading=32)
subtitle_style = ParagraphStyle("sub", fontName="DejaVu", fontSize=12,
                                textColor=SLATE, alignment=TA_CENTER, leading=18)
section_style = ParagraphStyle("sec", fontName="DejaVu-Bold", fontSize=18,
                               textColor=TEAL, alignment=TA_RIGHT, leading=26,
                               spaceBefore=14, spaceAfter=10)
item_title_style = ParagraphStyle("it", fontName="DejaVu-Bold", fontSize=12,
                                  textColor=NAVY, alignment=TA_RIGHT, leading=18,
                                  spaceBefore=8, spaceAfter=2)
body_style = ParagraphStyle("body", fontName="DejaVu", fontSize=10.5,
                            textColor=colors.HexColor("#1f2937"),
                            alignment=TA_RIGHT, leading=17, spaceAfter=6)


sections = [
    {
        "title": "أولاً: التسويق وموقع الـ Marketing",
        "items": [
            ("نقل محتوى الموقع التسويقي إلى Markdown (CMS)",
             "صار محتوى المعجم والمقارنات والأدلة بملفات Markdown منفصلة فيها YAML بالأعلى، "
             "بدل ملفات TypeScript واحدة طويلة. يعني أي شخص (حتى لو مش مبرمج) يقدر يضيف "
             "أو يعدّل صفحة جديدة بدون ما يلمس الكود، والـ build بيرفض أي حقل ناقص أو "
             "غلط بشكل واضح."),
            ("ربط الموافقة بإعادة بناء ونشر تلقائي",
             "لما توافق على مسودة من لوحة الأدمن، صار في طابور Build Jobs بيشتغل "
             "بالخلفية وبيعمل rebuild و redeploy للموقع، مع إعادة محاولة (1د/5د/20د) إذا "
             "فشل، وحالة `success` ما بتنزل إلا لما النشر الفعلي يصير. في تبويب جديد "
             "(🚀 Build & deploy) بيعرض السجلات وزر Retry يدوي."),
            ("تتبّع أي صفحات بتجيب زيارات حقيقية",
             "أضفنا جدول `seo_agent_page_metrics` و موصلين مجانيين لـ Plausible و "
             "Google Search Console. وكيل الـ SEO صار يرفع وزن المواضيع القريبة من "
             "صفحات ناجحة، وينزّل وزن المواضيع القريبة من صفحات بدون زيارات لأكتر من "
             "60 يوم، يعني التركيز يصير على اللي بيشتغل فعلاً."),
            ("روابط داخلية بين المعجم والأدلة والمقارنات",
             "كل صفحة فيها قسم 'See also' أعلى المحتوى + بطاقات روابط ذات صلة بأسفل "
             "الصفحة. هاد بيقوي الـ SEO الداخلي وبيخلي الزائر يتنقل بين المحتوى "
             "بسلاسة وبيزيد وقت الجلسة."),
            ("تحديث المحتوى ربع السنة",
             "حلّينا كل علامات [verify] في صفحات المقارنة بأرقام أسعار محدّثة (Tableau، "
             "Power BI، Looker، Metabase). أضفنا checklist `CONTENT_REFRESH.md` "
             "وسكربت `check:freshness` بيرفع علم على أي صفحة محتواها أقدم من 6 شهور."),
            ("تعبئة رابط المراجعة العام تلقائياً",
             "زر المراجعة بالإيميل الأسبوعي صار يشتغل من أول مرة بعد النشر بدون ما "
             "يدوياً تضبط متغير بيئة. الترتيب: متغير البيئة، ثم الإعدادات، ثم اكتشاف "
             "تلقائي للدومين من Replit."),
            ("تنبيه على الجوال عند جاهزية مسودات جديدة",
             "خيار اختياري بيرسل إيميل قصير فيه عدد المسودات وأول 10 عناوين وزر مراجعة، "
             "بعد كل دورة تنتج drafts. هيك ما تستنى التقرير الأسبوعي."),
            ("معرفة مين وافق على كل مسودة ومن وين",
             "أضفنا عمود `review_source` (admin / public_link / auto) و'tokens "
             "مسماة' لكل مراجع. صار جدول 'Draft decisions' بكل run يعرض المصدر "
             "والمراجع ووقت القرار - audit trail واضح."),
            ("Auto-ping لـ Google و Bing بعد كل نشر",
             "سكربت postbuild بيقرأ sitemap ويرسل تلقائياً للـ IndexNow (Bing/Yandex) "
             "و Google Indexing API الصفحات الجديدة أو المعدّلة فقط، مع state.json "
             "يمنع التكرار. النتيجة: الفهرسة بتصير بساعات بدل أسابيع."),
            ("إصلاح workflow معاينة الموقع التسويقي",
             "كان `npx astro dev` يجيب Astro 5 اللي بدها Node 22، فيفشل محلياً. "
             "صار الـ workflow يشغل `npm ci` أولاً بحيث يستخدم Astro 4.x المثبّت. "
             "النشر ما تأثر، بس الآن المعاينة المحلية شغّالة."),
        ],
    },
    {
        "title": "ثانياً: تحليل البيانات والتجربة الذكية",
        "items": [
            ("شريط الأسئلة الاستباقية (Proactive Question Bar)",
             "النظام صار يلاحظ بنفسه الأعمدة المختلطة الأنواع، التواريخ الغامضة "
             "(DD/MM مقابل MM/DD)، أعمدة بعملات متعددة، تواريخ هجرية مُعلَّمة، "
             "والصفوف المكررة شبه الكاملة (≥95%). وبيسأل المستخدم بشكل ودود وكل "
             "إجابة بتتسجل تلقائياً كخطوة قابلة للترتيب وإلغاء بـ Applied Steps."),
            ("نقل تبويب 'Data Modeling' وإدارة عدة ملفات",
             "تبويب النمذجة انتقل من المرتبة 7 إلى 3 (مباشرة بعد Cleaning) "
             "وصار اسمه 'Data Modeling'. أضفنا رفع ملفات إضافية CSV/Excel من نفس "
             "التبويب لإضافة جداول للمشروع نفسه، مع زر × Remove (تأكيد خطوتين) "
             "لحذف الـ dataset والعلاقات المرتبطة فيه."),
            ("تطبيق المرحلة الأولى تلقائياً مع مراجعة وشات الشكوك",
             "خطوات التنظيف الأساسية بتنطبق تلقائياً (Phase 1) مع لوحة مراجعة "
             "تخليك تلغي خطوة أو تعدلها، و'doubt chat' دائم بيخليك تسأل عن أي "
             "خطوة بعينها وتفهم سبب القرار."),
        ],
    },
    {
        "title": "ثالثاً: الباك-إند والبنية التحتية",
        "items": [
            ("صفحة Help Center داخل التطبيق",
             "صفحة كاملة (`?help=1`) فيها 8 أقسام شرح + جداول أسئلة شائعة + "
             "نموذج تواصل. الفوتر بكل الصفحات صار يحتوي على روابط Help Center "
             "و Documentation و Report an Issue موحّدة."),
            ("تهدئة طلبات إعادة تعيين كلمة المرور",
             "صارت دالة `create_password_reset_token` ترفض أي طلب جديد قبل ما "
             "يعدّي 60 ثانية على الأخير لنفس الإيميل (silent no-op)، وأي token "
             "قديم يصير marked used تلقائياً. يمنع spam بدون ما يكشف إذا "
             "الإيميل مسجّل أو لا."),
            ("إيميل تأكيد عند تغيير كلمة المرور",
             "بعد أي reset ناجح، صاحب الحساب يستلم إيميل بنفس ستايل الـ"
             " welcome (داكن/تيل) فيه زر 'Wasn't me' بيفتح إيميل دعم جاهز - "
             "إشارة خارجية لو حدا حاول يخترق الحساب."),
            ("جدول Build Jobs و worker thread",
             "بنية تحتية جديدة: جدول `seo_agent_build_jobs` + daemon thread "
             "بيلتقط المهام، بيحترم backoff عبر `next_attempt_at`، وبيدعم 3 "
             "أوضاع نشر: Webhook، Build-only للـ Reserved VM، أو وقفة على "
             "`needs_publish` لتأكيد الأوبريتر."),
            ("جدول page metrics + جدول build jobs + عمود review_source",
             "ثلاث إضافات للقاعدة (additive ALTER TABLE، بدون migration "
             "يدوي): قياس أداء الصفحات، تتبع البناء والنشر، وعمود يخزّن مصدر "
             "الموافقة. كلها تدعم لوحات إدارية جديدة بدون كسر التوافق."),
            ("نظام Tokens مسماة للمراجعين",
             "بدل token عام واحد، صار في `admin_review_tokens: List[{name, "
             "token}]` بحيث كل مراجع له رابطه الخاص، واسمه يطلع في الـ audit. "
             "الإيميل الأسبوعي بيرجع لأول token مسمى لو الـ legacy فاضي."),
        ],
    },
]


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 18, A4[0], 18, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.setFont("DejaVu-Bold", 9)
    canvas.drawString(36, A4[1] - 13, "DataVision Pro")
    canvas.setFillColor(WHITE)
    canvas.setFont("DejaVu", 8)
    canvas.drawRightString(A4[0] - 36, A4[1] - 13, ar("ملخص التحديثات - أبريل 2026"))
    canvas.setFillColor(SLATE)
    canvas.setFont("DejaVu", 8)
    canvas.drawCentredString(A4[0] / 2, 18, f"{doc.page}")
    canvas.restoreState()


def build():
    out = "ملخص_تحديثات_DataVisionPro.pdf"
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=48, bottomMargin=36,
                            leftMargin=42, rightMargin=42)
    story = []
    story.append(Spacer(1, 60))
    story.append(Paragraph(ar("ملخص تحديثات DataVision Pro"), title_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(ar("أبريل 2026 — التسويق، تحليل البيانات، البنية التحتية"),
                           subtitle_style))
    story.append(Spacer(1, 18))

    intro = ("هذا ملخص لكل التعديلات اللي صارت على المنصة بآخر دورة عمل، مقسّمة على "
             "ثلاثة محاور: ما يخدم النمو والتسويق، ما يخدم تجربة تحليل البيانات نفسها، "
             "وما يخدم الباك-إند والبنية التحتية للتطبيق. لكل بند شرح موجز عن الفائدة "
             "العملية على المنتج.")
    story.append(Paragraph(ar(intro), body_style))
    story.append(PageBreak())

    for sec in sections:
        story.append(Paragraph(ar(sec["title"]), section_style))
        rule = Table([[""]], colWidths=[A4[0] - 84], rowHeights=[1.2])
        rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)]))
        story.append(rule)
        story.append(Spacer(1, 6))
        for idx, (t, body) in enumerate(sec["items"], 1):
            story.append(Paragraph(ar(f"{idx}. {t}"), item_title_style))
            story.append(Paragraph(ar(body), body_style))
        story.append(PageBreak())

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(out)


if __name__ == "__main__":
    build()
