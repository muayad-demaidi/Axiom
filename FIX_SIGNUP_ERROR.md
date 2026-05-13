# 🔧 AXIOM Sign In / Sign Up Error 404 - Complete Fix Instructions

## 🎯 المشكلة (Problem)
Frontend بتطلب على `/signup` و `/api/signup` لكن Backend معرّف الـ endpoints بـ `/api/auth/register` و `/api/auth/login`

**النتيجة:** Error 404 عند محاولة Sign Up أو Sign In

---

## ✅ الحل الكامل

### **الخطوة 1: فحص الـ Backend (لا يحتاج تعديل)**
الـ Backend endpoints موجودة بالفعل في `backend/auth_routes.py`:
- ✅ `POST /api/auth/register` → للتسجيل الجديد
- ✅ `POST /api/auth/login` → للدخول

### **الخطوة 2: تعديل الـ Frontend API calls**

ابحث عن أي ملف في Frontend يحتوي على:
- `POST /signup`
- `POST /api/signup`
- `POST /signin`
- `POST /api/signin`

وغيّره إلى:
- `POST /api/auth/register` (للتسجيل)
- `POST /api/auth/login` (للدخول)

### **الخطوة 3: تأكد من Request Body**

**للتسجيل (Sign Up):**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "password123",
  "full_name": "User Name"
}
```

**للدخول (Sign In):**
```json
{
  "email_or_username": "user@example.com",
  "password": "password123"
}
```

### **الخطوة 4: تأكد من Token Handling**

الـ Response سيكون:
```json
{
  "token": "JWT_TOKEN_HERE",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "username",
    "subscription_type": null,
    "trial_end": null,
    "assistant_mode": "guided",
    "locale": "en",
    "is_admin": false
  }
}
```

**احفظ الـ token في localStorage:**
```javascript
const response = await fetch('/api/auth/register', { ... });
const data = await response.json();
localStorage.setItem('authToken', data.token);
```

**استخدمه في الـ requests التالية:**
```javascript
fetch('/api/protected-endpoint', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('authToken')}`
  }
})
```

---

## 🔍 ملفات Frontend يجب تعديلها

ابحث عن هذه الملفات وحدثها:
- `frontend/src/app/[locale]/signup/page.tsx` أو `page.jsx`
- `frontend/src/app/[locale]/login/page.tsx` أو `page.jsx`
- أي ملف يحتوي على `fetch`, `axios`, أو `api` calls للـ authentication
- ملفات الـ `lib/api.ts` أو `services/auth.ts` إن وجدت

---

## 📋 Checklist عند انتهاء التعديل

- [ ] جميع sign up requests تطلب على `/api/auth/register`
- [ ] جميع sign in requests تطلب على `/api/auth/login`
- [ ] الـ request body يحتوي على الحقول الصحيحة
- [ ] الـ token يتم حفظه بشكل صحيح
- [ ] الـ Authorization header يستخدم الـ token في الـ protected routes
- [ ] جرّب Sign Up مع email و password صحيحة
- [ ] جرّب Sign In بنفس الـ credentials

---

## 🚀 أوامر Git للتطبيق

```bash
# 1. اذهب للـ Frontend directory
cd frontend

# 2. بحث سريع عن جميع axios/fetch calls للـ signup/signin
grep -r "signup\|signin" src/ --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx"

# 3. بعد التعديل، commit التغييرات
git add .
git commit -m "fix: update auth endpoints from /signup to /api/auth/register and /signin to /api/auth/login"

# 4. push
git push origin main
```

---

## ⚠️ ملاحظات مهمة

1. **CORS يجب يكون مفعّل** - تحقق من `backend/main.py` سطر 92-109
   - يجب أن يشمل `http://localhost:5000` أو URL الـ Frontend الفعلي

2. **Database يجب تكون initialized** - تأكد من:
   ```bash
   python backend/main.py  # يجب تعمل بدون أخطاء
   ```

3. **JWT Secret** - تأكد من وجود:
   ```bash
   export JWT_SECRET="your-secret-key-here"
   ```

4. **Test مع curl قبل الـ Frontend:**
   ```bash
   curl -X POST http://localhost:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "username": "testuser",
       "password": "password123",
       "full_name": "Test User"
     }'
   ```

---

## 📞 إذا استمرت المشكلة

تحقق من:
1. Network tab في الـ Browser DevTools - شنو الـ URL اللي بتطلب عليه بالضبط؟
2. الـ Response status - 404 أم 422 أم حاجة تانية؟
3. الـ Response body - شنو الـ error message؟
