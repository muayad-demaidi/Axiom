#!/usr/bin/env python3
"""Re-translate the 6 files corrupted by short-word substitutions in
strip_arabic.py. Reads pristine originals from /tmp (already extracted
from git HEAD) and applies a curated dictionary of *full* phrases only —
no single-word entries that can collide inside other phrases.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/home/runner/workspace/frontend/src")

# ---- File: join/page.tsx ----
JOIN_MAP = {
    "الصفوف المتطابقة في الجانبين فقط": "Rows that match on both sides only",
    "استبعد أي صف لا يجد مطابقة على الجانب الآخر.": "Exclude any row that doesn't find a match on the other side.",
    "كل الصفوف من البيانات الأولى": "All rows from the first dataset",
    "احتفظ بكل صفوف البيانات اليسرى حتى لو لم توجد مطابقة.": "Keep every row from the left dataset even when no match exists.",
    "كل الصفوف من البيانات الثانية": "All rows from the second dataset",
    "احتفظ بكل صفوف البيانات اليمنى حتى لو لم توجد مطابقة.": "Keep every row from the right dataset even when no match exists.",
    "كل شيء من الجانبين": "Everything from both sides",
    "احتفظ بكل صف من أي جانب؛ القيم المفقودة تصبح فارغة.": "Keep every row from either side; missing values become blank.",
    "تقاطع المفاتيح.": "Intersection of keys.",
    "كل صفوف اليسار؛ يكون اليمين NULL عند الغياب.": "All left rows; right side is NULL when absent.",
    "كل صفوف اليمين؛ يكون اليسار NULL عند الغياب.": "All right rows; left side is NULL when absent.",
    "اتحاد كل المفاتيح؛ NULL عند غياب أي جانب.": "Union of all keys; NULL when either side is absent.",
    "اختر مجموعتي بيانات أولًا.": "Pick two datasets first.",
    "اختر العمود المشترك للدمج.": "Pick the common column for the join.",
    "الخطوة 1 · البيانات اليسرى": "Step 1 · Left dataset",
    "الخطوة 2 · البيانات اليمنى": "Step 2 · Right dataset",
    "الخطوة 3 · العمود المشترك": "Step 3 · Common column",
    "الخطوة 4 · ما الذي تريد الاحتفاظ به؟": "Step 4 · What do you want to keep?",
    "الخطوة 5 · معاينة": "Step 5 · Preview",
    "الخطوة 6 · التسمية والحفظ": "Step 6 · Name and save",
    "{d.dataset_name} · {d.rows} صف": "{d.dataset_name} · {d.rows} rows",
    "{leftCols.length} عمود": "{leftCols.length} columns",
    "{rightCols.length} عمود": "{rightCols.length} columns",
    "جارٍ تقييم الأعمدة المشتركة وفق القيم الفعلية…": "Evaluating common columns against actual values…",
    "دمج مقترح": "Suggested join",
    "{Math.round(topSuggestion.overlap_score * 100)}% تطابق ·": "{Math.round(topSuggestion.overlap_score * 100)}% match ·",
    "<strong>لا توجد قيم متطابقة</strong> — اختر عمودًا": "<strong>No matching values</strong> — pick another",
    "آخر أو تأكد من أن هذا مقصود.": "column or confirm that this is intentional.",
    "استخدم هذا": "Use this",
    "لم يتم العثور على مرشح قوي للدمج بالقيم. اختر عمودًا يدويًا أدناه.": "No strong join candidate found by values. Pick a column manually below.",
    "تعذّر تقييم مرشّحي الدمج: {suggestError}": "Failed to evaluate join candidates: {suggestError}",
    "لا يوجد تطابق دقيق في أسماء الأعمدة. اختر عمودًا من كل جانب أدناه.": "No exact match in column names. Pick a column from each side below.",
    "مفتاح اليسار (تخصيص)": "Left key (custom)",
    "(استخدم المشترك)": "(use common)",
    "مفتاح اليمين (تخصيص)": "Right key (custom)",
    "جارٍ الحساب…": "Calculating…",
    "معاينة الدمج": "Preview join",
    "النتيجة: <strong>{preview.summary.result_rows}</strong> صف ·": "Result: <strong>{preview.summary.result_rows}</strong> rows ·",
    "<strong>{preview.summary.result_cols}</strong> عمود.": "<strong>{preview.summary.result_cols}</strong> cols.",
    "{preview.summary.result_rows} صف × {preview.summary.result_cols} عمود": "{preview.summary.result_rows} rows × {preview.summary.result_cols} cols",
    "هذه التركيبة كبيرة بشكل غير معتاد.": "This combination is unusually large.",
    "تحذير تضخّم (${preview.summary.cardinality ?? \"N:N\"} join)": "Cardinality warning (${preview.summary.cardinality ?? \"N:N\"} join)",
    "نعم، احفظ هذا الدمج الكبير على أي حال.": "Yes, save this large join anyway.",
    "عدد القيم الفارغة لكل عمود": "Null count per column",
    "جارٍ الحفظ…": "Saving…",
    "احفظ كمجموعة جديدة": "Save as new dataset",
    "ضع علامة التأكيد أعلاه لحفظ هذا الدمج الكبير.": "Tick the confirmation above to save this large join.",
    "تم الحفظ بنجاح ✓ باسم": "Saved ✓ as",
    "({saved.rows} صف ·": "({saved.rows} rows ·",
    "{saved.cols} عمود).": "{saved.cols} cols).",
    "فتح في الملفات": "Open in Files",
    "حذف البيانات المدموجة وإلغاء اختيارها.": "Delete the joined dataset and deselect it.",
    "تراجع عن الدمج": "Undo join",
    "البيانات المدموجة في هذا المشروع": "Joined datasets in this project",
    "دمج من <strong>{left}</strong> ⋈": "Join from <strong>{left}</strong> ⋈",
    "<strong>{right}</strong> على": "<strong>{right}</strong> on",
}

# ---- File: report/page.tsx ----
REPORT_MAP = {
    "صفحة الغلاف": "Cover page",
    "العنوان واسم البيانات وعدد الصفوف/الأعمدة والملاحظات.": "Title, dataset name, row/column count and notes.",
    "جدول الأعمدة": "Columns table",
    "نوع كل عمود وعدد القيم الموجودة والمفقودة.": "Each column's type and count of present/missing values.",
    "ملخّص رقمي": "Numeric summary",
    "جدول الإحصاءات الوصفية للأعمدة الرقمية.": "Descriptive statistics for numeric columns.",
    "مخطّط التوزيع": "Distribution chart",
    "مدرّج تكراري لعمود رقمي واحد.": "Histogram for a single numeric column.",
    "ملاحظات الذكاء الاصطناعي": "AI insights",
    "ملخّص سردي مولَّد آليًا.": "Auto-generated narrative summary.",
    "تعذّر تحميل التقارير الأخيرة": "Failed to load recent reports",
    "تعذّر إنشاء التقرير": "Failed to generate report",
    "لا توجد بيانات نشِطة — يرجى رفع ملف أولًا.": "No active dataset — please upload a file first.",
    "اختر قسمًا واحدًا على الأقل ليُضاف إلى التقرير.": "Pick at least one section to include in the report.",
    "جاري إعداد التقرير…": "Preparing report…",
    "تم الحفظ بنجاح ✓": "Saved ✓",
    "لم تعد بيانات هذا التقرير متاحة.": "This report's data is no longer available.",
    "تعذّر إعادة التنزيل": "Failed to re-download",
    "الأقسام التي ستُضمَّن": "Sections to include",
    "ارفع ملف CSV أو Excel وسنُعدّ لك ملخّصًا في صفحة واحدة.": "Upload a CSV or Excel file and we'll produce a one-page summary.",
    "أعطِ تقريرك عنوانًا (اختياري)": "Give your report a title (optional)",
    "عنوان التقرير (اختياري)": "Report title (optional)",
    "تقرير بيانات AXIOM": "AXIOM data report",
    "هل ثمّة ما تريد ذكره في المقدّمة؟ (اختياري)": "Anything to mention in the intro? (optional)",
    "ملاحظات (اختياري)": "Notes (optional)",
    "مثال: تغطّي هذه البيانات مبيعات الربع الثالث في منطقة EMEA…": "Example: this data covers Q3 sales in the EMEA region…",
    "سياق للقارئ…": "Context for the reader…",
    "ما الذي ستحصل عليه": "What you'll get",
    "صفحة غلاف باسم البيانات وملاحظاتك.": "Cover page with the dataset name and your notes.",
    "ملخّص سردي لأهم النتائج.": "Narrative summary of the key findings.",
    "مخطّط بارز لأهم عمود رقمي.": "Highlighted chart for the top numeric column.",
    "افتح العرض المتقدّم إن أردت أيضًا جدول الأعمدة الخام والملخّص الرقمي.": "Open the advanced view if you also want the raw columns table and numeric summary.",
    "اختر بدقّة الأقسام التي ستُضمَّن": "Pick precisely which sections to include",
    "عمود المخطّط (رقمي)": "Chart column (numeric)",
    "لا توجد أعمدة رقمية": "No numeric columns",
    "أول عمود رقمي (افتراضي)": "First numeric column (default)",
    "جاري التوليد…": "Generating…",
    "اكتب تقريري": "Write my report",
    "أنشئ التقرير": "Generate report",
    "التقارير الأخيرة": "Recent reports",
    "جاري التحديث…": "Refreshing…",
    "تحديث": "Refresh",
    "التقارير التي أنشأتها للمشروع النشط.": "Reports you created for the active project.",
    "التقارير التي أنشأتها مؤخرًا.": "Reports you've created recently.",
    "لا توجد تقارير بعد. أنشئ واحدًا أعلاه وسيظهر هنا.": "No reports yet. Create one above and it will show here.",
    "بيانات #${r.dataset_id ?? \"؟\"}": "Dataset #${r.dataset_id ?? \"?\"}",
    "إعادة إنشاء وتنزيل التقرير": "Regenerate and download report",
    "لم تعد بيانات هذا التقرير متاحة": "This report's data is no longer available",
    "جاري التحضير…": "Preparing…",
    "تنزيل": "Download",
}

# ---- File: transform/page.tsx ----
TRANSFORM_MAP = {
    "العملية": "Operation",
    "العمود": "Column",
    "الاسم الجديد": "New name",
    "القيمة": "Value",
    "أضف خطوة": "Add step",
    "حذف الخطوة ${i + 1}": "Delete step ${i + 1}",
    "حذف": "Delete",
    "جاري التطبيق…": "Applying…",
    "طبّق الخطوات": "Apply steps",
    "ارفع ملف CSV أو Excel وسنعرض أعمدته لتحويلها.": "Upload a CSV or Excel file and we'll show its columns to transform.",
    "تحويل القيم إلى حروف صغيرة": "Lowercase values",
    "اجعل كل قيم العمود بحروف صغيرة لمطابقة المسمّيات بثبات.": "Lowercase every value in this column for consistent label matching.",
    "طبّق": "Apply",
    "تحويل القيم إلى حروف كبيرة": "Uppercase values",
    "اجعل كل قيم العمود بحروف كبيرة — مناسب لرموز المنتجات وأسماء الدول.": "Uppercase every value in this column — useful for product codes and country names.",
    "حذف هذا العمود": "Delete this column",
    "إزالة العمود نهائيًا. مناسب لمعرّفات الصفوف والحقول المزعجة.": "Remove the column permanently. Useful for row IDs and noisy fields.",
    "احذف العمود": "Delete column",
    "ملء الخلايا الفارغة بـ 0": "Fill empty cells with 0",
    "استبدال القيم الناقصة بصفر حتى لا تنقطع الحسابات.": "Replace missing values with zero so calculations don't break.",
    "املأ الفراغات": "Fill blanks",
    "تم تحويل العمود بنجاح ✓": "Column transformed ✓",
}

# ---- File: predict/page.tsx ----
PREDICT_MAP = {
    "أهم تفسيرات المتغيّرات (SHAP)": "Top feature explanations (SHAP)",
    "إسهامات المتغيّرات في توقّعات النموذج {expert.model_used ?? \"المختار\"}.": "Feature contributions to predictions of the {expert.model_used ?? \"chosen\"} model.",
    "كلما زاد الشريط زاد تأثير المتغيّر على التوقّعات في المتوسّط.": "The longer the bar, the more this feature affects predictions on average.",
    "خلال الـ <strong>{flat.length}</strong> فترة القادمة يبلغ متوسّط التوقّع لـ": "Across the next <strong>{flat.length}</strong> periods, the average forecast for",
    "مع ذروة في الفترة {peakIdx + 1} ({flat[peakIdx].toLocaleString(undefined, { maximumFractionDigits: 2 })}).": "with a peak at period {peakIdx + 1} ({flat[peakIdx].toLocaleString(undefined, { maximumFractionDigits: 2 })}).",
    "الفترة": "Period",
    "التوقّع": "Forecast",
    "العمود": "Column",
    "عدد الفترات المتوقَّعة": "Number of forecast periods",
    "جاري التنبّؤ…": "Forecasting…",
    "ابدأ التنبّؤ": "Start forecasting",
    "ارفع ملف CSV أو Excel يحتوي عمودًا رقميًا وسنتنبّأ به.": "Upload a CSV or Excel file with a numeric column and we'll forecast it.",
    "ماذا تريد أن نتنبّأ به؟": "What do you want to forecast?",
    "تنبّأ بـ 3 فترات قادمة": "Forecast next 3 periods",
    "6 فترات قادمة": "Next 6 periods",
    "12 فترة قادمة": "Next 12 periods",
    "اختر الأفق الزمني والعمود بدقّة": "Choose the time horizon and column precisely",
    "عرض مخرجات النموذج": "Show model outputs",
}

# ---- File: project/[id]/report/page.tsx ----
PROJREPORT_MAP = {
    "No chat session selected. / لم تُحدَّد جلسة محادثة.": "No chat session selected.",
    "Final report · التقرير النهائي": "Final report",
    "📌 {pinnedCount} pinned · مثبَّت": "📌 {pinnedCount} pinned",
    "of {totalArtifacts} total · من {totalArtifacts} الكلّي": "of {totalArtifacts} total",
    "Pinned only · المثبَّت فقط": "Pinned only",
    "Back to chat · رجوع للمحادثة": "Back to chat",
    "Building… · جاري التحضير": "Building…",
    "Download PDF · تنزيل التقرير": "Download PDF",
    "Loading report… · جاري تحميل التقرير…": "Loading report…",
    "Cover · الغلاف": "Cover",
    "Generated · أنشئ بتاريخ": "Generated on",
    "Insights synthesis · خلاصة الجلسة": "Insights synthesis",
    "Key findings · أبرز النتائج": "Key findings",
    "Recommendations · التوصيات": "Recommendations",
    "Surprise insights · رؤى مفاجئة": "Surprise insights",
    "Data profile · تعريف البيانات": "Data profile",
    "Charts · المخططات": "Charts",
    "Predictions · التنبؤات": "Predictions",
    "What-if recommendations · توصيات افتراضية": "What-if recommendations",
    "Clusters · المجموعات": "Clusters",
    "Conversation · نص المحادثة": "Conversation",
    "You · أنت": "You",
    "Nothing pinned to this report yet · لا يوجد شي مثبَّت بهالتقرير لساتو.": "Nothing pinned to this report yet.",
    "PDF preview · معاينة PDF": "PDF preview",
    "building… · يحضّر…": "building…",
    "target · الهدف": "target",
}

# ---- File: statistics/page.tsx ----
STATS_MAP = {
    "عدد الصفوف": "Row count",
    "عدد الأعمدة": "Column count",
    "أعمدة رقمية": "Numeric columns",
    "أعمدة بها قيم ناقصة": "Columns with missing values",
    "{(n as number).toLocaleString()} قيمة ناقصة": "{(n as number).toLocaleString()} missing",
    "لا توجد قيم ناقصة.": "No missing values.",
    "أعمدة رقمية جاهزة للتحليل: {numericCols.join(\"، \")}.": "Numeric columns ready for analysis: {numericCols.join(\", \")}.",
    "ارفع ملف CSV أو Excel وسنلخّص محتواه.": "Upload a CSV or Excel file and we'll summarize it.",
    "جاري الحساب…": "Calculating…",
}


def apply(orig_path: str, target_relpath: str, mapping: dict[str, str]) -> None:
    text = Path(orig_path).read_text(encoding="utf-8")
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) for k in keys))
    new = pat.sub(lambda m: mapping[m.group(0)], text)
    out = ROOT / target_relpath
    out.write_text(new, encoding="utf-8")
    # report any leftover Arabic
    leftovers = [
        (i, line) for i, line in enumerate(new.splitlines(), 1)
        if re.search(r"[\u0600-\u06FF]", line)
    ]
    if leftovers:
        print(f"  [WARN] {target_relpath} leftover Arabic on {len(leftovers)} lines:")
        for i, line in leftovers[:10]:
            print(f"    {i}: {line.strip()[:120]}")
    else:
        print(f"  [OK]   {target_relpath} clean")


def main() -> int:
    apply("/tmp/join_orig.tsx", "app/[locale]/app/join/page.tsx", JOIN_MAP)
    apply("/tmp/report_orig.tsx", "app/[locale]/app/report/page.tsx", REPORT_MAP)
    apply("/tmp/transform_orig.tsx", "app/[locale]/app/transform/page.tsx", TRANSFORM_MAP)
    apply("/tmp/predict_orig.tsx", "app/[locale]/app/predict/page.tsx", PREDICT_MAP)
    apply("/tmp/projreport_orig.tsx", "app/[locale]/app/project/[id]/report/page.tsx", PROJREPORT_MAP)
    apply("/tmp/stats_orig.tsx", "app/[locale]/app/statistics/page.tsx", STATS_MAP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
